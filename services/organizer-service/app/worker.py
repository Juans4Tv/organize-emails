import logging
import re
from datetime import datetime

from sqlalchemy import select

from shared.config import QUEUE_ORGANIZE
from shared.db import Document, Email, Place, Setting, get_session_factory, init_db
from shared.files import move_document_file
from shared.money import normalize_amount
from shared.names import name_matches_owner, pdf_sibling_match
from shared.parsing.amounts import extract_amount, extract_currency
from shared.parsing.cfdi import classify_flow, parse_cfdi
from shared.parsing.dates import extract_issue_date
from shared.parsing.ubl import parse_ubl
from shared.parsing.places import detect_place_from_text, normalize_place_name
from shared.queues import pop

log = logging.getLogger("organizer-service")


def _find_xml_sibling(session, doc) -> Document | None:
    """Find the XML sibling of a PDF by CUFE filename match."""
    from shared.parsing.ubl import cuche_key_from_filename
    key = cuche_key_from_filename(doc.original_name)
    if not key:
        return None
    return session.execute(
        select(Document).where(
            Document.ext == ".xml",
            Document.cuche_key == key,
            Document.id != doc.id,
            Document.status == "organized",
        )
    ).scalars().first()
logging.basicConfig(level=logging.INFO)

GANANCIA_RE = re.compile(
    r"nota\s+de\s+credito|devoluci[oó]n|reembolso|pago\s+recibido|abono", re.IGNORECASE
)
GASTO_RE = re.compile(
    r"factura|compra|nota\s+de\s+cargo|orden\s+de\s+compra|consumo|venta\s+de\s+mostrador",
    re.IGNORECASE,
)
GENERIC_SENDER_TOKENS = {
    "facturacion", "facturación", "notificaciones", "noreply", "no-reply",
    "no", "reply", "admin", "administracion", "sistema", "portal", "correo",
}


def get_or_create_place(session, raw_name: str, source: str) -> Place:
    normalized = normalize_place_name(raw_name) or "Sin lugar"
    place = session.execute(
        select(Place).where(Place.name == normalized)
    ).scalar_one_or_none()
    if place is None:
        place = Place(name=normalized, source=source)
        session.add(place)
        session.flush()
    return place


def _sender_candidates(email_row: Email | None) -> list[tuple[str, float]]:
    if email_row is None:
        return []
    out: list[tuple[str, float]] = []
    name = (email_row.sender_name or "").strip()
    if name and not any(tok in name.lower() for tok in GENERIC_SENDER_TOKENS):
        cleaned = re.sub(r"\b(facturaci[oó]n|notificaciones|atenci[oó]n)\b.*$", "",
                         name, flags=re.IGNORECASE).strip(" -–—|")
        if len(cleaned) >= 3:
            out.append((cleaned, 0.45))
    domain = ""
    if "@" in (email_row.sender_email or ""):
        domain = email_row.sender_email.split("@")[1].split(".")[0]
    if domain and domain not in ("gmail", "hotmail", "outlook", "yahoo", "live"):
        out.append((domain.replace("-", " "), 0.35))
    return out


def _owner_flow_guard(flow: str, flow_conf: float,
                      receptor_name: str, emisor_name: str,
                      owner_name: str) -> tuple[str, float]:
    """Regla de propiedad: si la factura va dirigida al dueño de la cuenta
    es un GASTO; si el dueño es quien emite, es GANANCIA. Tiene la última
    palabra sobre heurísticas."""
    owner = (owner_name or "").strip()
    if not owner:
        return flow, flow_conf
    receptor = (receptor_name or "").strip()
    emisor = (emisor_name or "").strip()
    if receptor and name_matches_owner(receptor, owner):
        return "gasto", max(flow_conf if flow == "gasto" else 0.0, 0.92)
    if emisor and name_matches_owner(emisor, owner):
        return "ganancia", max(flow_conf if flow == "ganancia" else 0.0, 0.92)
    return flow, flow_conf


def analyze(session_factory, document_id: int) -> None:
    session = session_factory()
    try:
        doc = session.get(Document, document_id)
        if doc is None:
            return

        email_row = session.get(Email, doc.email_id) if doc.email_id else None
        settings_rows = session.execute(select(Setting)).scalars().all()
        settings = {r.key: r.value for r in settings_rows}
        own_rfc = (settings.get("own_rfc") or "").strip()

        cfdi = None
        if doc.ext == ".xml":
            try:
                with open(doc.stored_path, "rb") as fh:
                    data = fh.read()
                cfdi = parse_cfdi(data) or parse_ubl(data)
            except OSError:
                cfdi = None

        if cfdi:
            doc.emisor_name = (cfdi.get("emisor_nombre") or "")[:300]
            doc.receptor_name = (cfdi.get("receptor_nombre") or "")[:300]
            doc.cuche_key = (cfdi.get("cuche_key") or "")[:64]

        # ---- Lugar ----
        candidates: list[tuple[str, float]] = []
        if cfdi and cfdi.get("emisor_nombre"):
            candidates.append((cfdi["emisor_nombre"], 0.9))
        text_detection, text_conf = detect_place_from_text(doc.full_text or "")
        if text_detection:
            candidates.append((text_detection, text_conf))
        candidates.extend(_sender_candidates(email_row))
        candidates.append(("Sin lugar", 0.1))

        best_raw, best_score = max(candidates, key=lambda c: c[1])
        doc.place_name_raw = best_raw[:300]

        # ---- Monto y moneda ----
        amount_conf = 0.0
        verified_by_source = False
        if cfdi and cfdi.get("total") is not None:
            doc.amount = cfdi["total"]
            doc.currency = cfdi.get("moneda") or "COP"
            amount_conf = 0.95
            verified_by_source = True  # datos exactos del XML
        else:
            doc.amount, amount_conf = extract_amount(doc.full_text or "")
            if doc.amount is not None:
                doc.currency = extract_currency(doc.full_text)
        doc.verified = bool(verified_by_source and doc.amount is not None)
        base_cur = (settings.get("base_currency") or "COP").upper()
        fx_raw = settings.get("fx_usd_cop") or "4000"
        doc.amount, doc.currency = normalize_amount(doc.amount, doc.currency, base_cur, fx_raw)

        # ---- Flujo gasto/ganancia ----
        if cfdi:
            flow, flow_conf = classify_flow(cfdi, own_rfc)
        elif GANANCIA_RE.search(doc.full_text or ""):
            flow, flow_conf = "ganancia", 0.6
        elif GASTO_RE.search(doc.full_text or ""):
            flow, flow_conf = "gasto", 0.55
        else:
            flow, flow_conf = "gasto", 0.25

        owner_name = (settings.get("owner_name") or "").strip()
        flow, flow_conf = _owner_flow_guard(flow, flow_conf,
                                            doc.receptor_name or (cfdi or {}).get("receptor_nombre", ""),
                                            doc.emisor_name or (cfdi or {}).get("emisor_nombre", ""),
                                            owner_name)
        doc.flow = flow

        # ---- Tipo de documento ----
        if cfdi:
            tipo = (cfdi.get("tipo") or "").upper()
            doc.doc_kind = {"I": "factura", "E": "nota_credito", "N": "nomina",
                            "P": "pago"}.get(tipo, "factura")
        else:
            doc.doc_kind = "documento"

        # ---- Fecha del documento ----
        fallback_date = None
        if email_row and email_row.date_received:
            fallback_date = email_row.date_received.replace(tzinfo=None)
        else:
            fallback_date = datetime.utcnow()

        if cfdi and cfdi.get("fecha"):
            doc.doc_date = cfdi["fecha"]
        elif doc.ext == ".pdf" and (doc.full_text or "").strip():
            extracted = extract_issue_date(doc.full_text)
            if extracted:
                doc.doc_date = extracted
            else:
                xml_sibling = _find_xml_sibling(session, doc)
                if xml_sibling and xml_sibling.doc_date:
                    doc.doc_date = xml_sibling.doc_date
                else:
                    doc.doc_date = fallback_date
        else:
            doc.doc_date = fallback_date

        # ---- Confianza global ----
        confidence = round(
            min(1.0, 0.5 * best_score + 0.3 * amount_conf + 0.2 * flow_conf), 2
        )
        doc.confidence = confidence
        needs_review = (
            best_score < 0.4
            or doc.amount is None
            or confidence < 0.55
            or bool(doc.error)
        )
        doc.needs_review = needs_review

        place = get_or_create_place(session, best_raw,
                                    source="cfdi" if (cfdi and cfdi.get("emisor_nombre")) else ("texto" if text_detection else "remitente"))
        doc.place_id = place.id
        move_document_file(doc, place.name)

        doc.status = "needs_review" if needs_review else "organized"
        session.commit()
        log.info("Doc %s organizado en '%s' (%s %s, conf %.2f)",
                 doc.id, place.name, doc.flow, doc.amount, confidence)
    except Exception:  # noqa: BLE001
        session.rollback()
        fresh = session.get(Document, document_id)
        if fresh:
            fresh.status = "failed"
            fresh.needs_review = True
            session.commit()
        log.exception("Error organizando documento %s", document_id)
    finally:
        session.close()


def main() -> None:
    init_db()
    session_factory = get_session_factory()
    log.info("organizer-service escuchando cola: %s", QUEUE_ORGANIZE)
    while True:
        payload = pop(QUEUE_ORGANIZE, timeout=5)
        if not payload:
            continue
        try:
            analyze(session_factory, int(payload["document_id"]))
        except Exception:  # noqa: BLE001
            log.exception("Fallo grave organizando: %s", payload)


if __name__ == "__main__":
    main()
