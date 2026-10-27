import os
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import select

from shared.db import Document, Email, Place, Setting, get_session_factory
from shared.files import move_document_file
from shared.money import normalize_amount, parse_user_amount
from shared.names import pdf_sibling_match
from shared.parsing.cfdi import parse_cfdi
from shared.parsing.ubl import parse_ubl

router = APIRouter()


# ---------- documentos ----------


@router.get("/api/documents")
def list_documents(
    place_id: int | None = None,
    flow: str | None = None,
    needs_review: bool | None = None,
    status: str | None = None,
    account: str | None = None,
    q: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
) -> dict:
    session = get_session_factory()()
    query = select(Document).join(Place, Document.place_id == Place.id, isouter=True)
    filters = []
    if place_id:
        filters.append(Document.place_id == place_id)
    if flow:
        filters.append(Document.flow == flow)
    if needs_review is not None:
        filters.append(Document.needs_review == needs_review)
    if status:
        filters.append(Document.status == status)
    if account:
        if account == "(sin cuenta)":
            filters.append(Document.account == "")
        else:
            filters.append(Document.account == account)
    if q:
        like = f"%{q}%"
        filters.append(
            Document.original_name.ilike(like)
            | Document.full_text.ilike(like)
            | Document.link_url.ilike(like)
            | Place.name.ilike(like)
        )
    for f in filters:
        query = query.where(f)

    total = session.execute(
        select(func.count()).select_from(query.subquery())
    ).scalar_one()

    docs = session.execute(
        query.order_by(Document.updated_at.desc(), Document.id.desc())
        .offset(offset).limit(limit)
    ).scalars().unique().all()

    items = []
    for d in docs:
        email = session.get(Email, d.email_id) if d.email_id else None
        place = session.get(Place, d.place_id) if d.place_id else None
        items.append({
            "id": d.id,
            "original_name": d.original_name,
            "source_type": d.source_type,
            "ext": d.ext,
            "status": d.status,
            "needs_review": d.needs_review,
            "verified": bool(d.verified),
            "place_id": d.place_id,
            "place_name": place.name if place else "",
            "doc_kind": d.doc_kind,
            "flow": d.flow,
            "amount": d.amount,
            "currency": d.currency,
            "doc_date": d.doc_date.isoformat() if d.doc_date else None,
            "confidence": d.confidence,
            "link_url": d.link_url,
            "account": d.account,
            "sender": f"{email.sender_name} <{email.sender_email}>" if email else "",
            "received": email.date_received.isoformat() if email and email.date_received else None,
            "error": d.error,
        })
    session.close()
    return {"total": total, "items": items}


@router.patch("/api/documents/{document_id}")
def patch_document(document_id: int, payload: dict) -> dict:
    session = get_session_factory()()
    try:
        doc = session.get(Document, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="documento no encontrado")

        settings = {r.key: r.value for r in session.execute(select(Setting)).scalars().all()}

        if "flow" in payload:
            if payload["flow"] not in ("gasto", "ganancia", "neutral"):
                raise HTTPException(status_code=400, detail="flujo inválido")
            doc.flow = payload["flow"]
            doc.confidence = max(doc.confidence, 0.9)

        amount_edited = False
        if "amount" in payload:
            raw = payload["amount"]
            if raw is None or str(raw).strip() == "":
                doc.amount = None
            else:
                try:
                    doc.amount = parse_user_amount(raw)
                    base_cur = (settings.get("base_currency") or "COP").upper()
                    fx_raw = settings.get("fx_usd_cop") or "4000"
                    doc.amount, doc.currency = normalize_amount(
                        doc.amount, doc.currency, base_cur, fx_raw
                    )
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Monto inválido: '{raw}'. Ejemplos válidos: 1234567.89 o 1.234.567,89",
                    )
            doc.confidence = max(doc.confidence, 0.9)
            amount_edited = True

        # editar el monto manualmente implica que el humano lo confirmó
        if "verified" in payload:
            doc.verified = bool(payload["verified"])
        elif amount_edited and doc.amount is not None:
            doc.verified = True

        if "doc_date" in payload and payload["doc_date"]:
            doc.doc_date = datetime.fromisoformat(payload["doc_date"])
            move_document_file(doc, _place_name(session, doc))

        if "doc_kind" in payload and payload["doc_kind"]:
            doc.doc_kind = payload["doc_kind"]

        place_changed = False
        if "place_name" in payload and payload["place_name"]:
            new_name = payload["place_name"].strip()
            if new_name:
                place = session.execute(
                    select(Place).where(Place.name == new_name)
                ).scalar_one_or_none()
                if place is None:
                    place = Place(name=new_name, source="manual")
                    session.add(place)
                    session.flush()
                doc.place_id = place.id
                doc.place_name_raw = new_name
                doc.confidence = max(doc.confidence, 0.95)
                place_changed = True

        if place_changed or "doc_date" in payload:
            place = session.get(Place, doc.place_id) if doc.place_id else None
            if place:
                move_document_file(doc, place.name)

        if "needs_review" in payload:
            doc.needs_review = bool(payload["needs_review"])
        else:
            doc.needs_review = False

        doc.error = ""
        if doc.status in ("needs_review", "failed"):
            doc.status = "organized" if not doc.needs_review else "needs_review"
        session.commit()
        session.close()
        return {"ok": True}
    except HTTPException:
        session.rollback()
        session.close()
        raise
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        session.close()
        raise HTTPException(status_code=500, detail=str(exc))


def _place_name(session, doc: Document) -> str:
    if doc.place_id:
        place = session.get(Place, doc.place_id)
        if place:
            return place.name
    return doc.place_name_raw or "Sin lugar"


@router.delete("/api/documents/{document_id}")
def delete_document(document_id: int) -> dict:
    session = get_session_factory()()
    doc = session.get(Document, document_id)
    if not doc:
        session.close()
        raise HTTPException(status_code=404, detail="documento no encontrado")
    if doc.stored_path and os.path.exists(doc.stored_path):
        os.remove(doc.stored_path)
    session.delete(doc)
    session.commit()
    session.close()
    return {"ok": True}


@router.post("/api/documents/delete-bulk")
def delete_documents_bulk(payload: dict) -> dict:
    ids = payload.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="Envía una lista de ids en 'ids'")
    session = get_session_factory()()
    deleted = 0
    try:
        for doc_id in ids:
            doc = session.get(Document, int(doc_id))
            if not doc:
                continue
            if doc.stored_path and os.path.exists(doc.stored_path):
                os.remove(doc.stored_path)
            session.delete(doc)
            deleted += 1
        session.commit()
    finally:
        session.close()
    return {"deleted": deleted}


@router.post("/api/documents/bulk-verify")
def verify_documents_bulk(payload: dict) -> dict:
    ids = payload.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="Envía una lista de ids en 'ids'")
    session = get_session_factory()()
    verified = 0
    try:
        for doc_id in ids:
            doc = session.get(Document, int(doc_id))
            if not doc:
                continue
            doc.verified = True
            doc.needs_review = False
            doc.status = "organized" if doc.status == "needs_review" else doc.status
            verified += 1
        session.commit()
    finally:
        session.close()
    return {"verified": verified}


@router.get("/api/files/{document_id}")
def get_file(document_id: int) -> FileResponse:
    session = get_session_factory()()
    doc = session.get(Document, document_id)
    session.close()
    if not doc or not doc.stored_path or not os.path.exists(doc.stored_path):
        raise HTTPException(status_code=404, detail="archivo no disponible")
    media = "application/pdf" if doc.ext == ".pdf" else "application/xml"
    return FileResponse(doc.stored_path, media_type=media, filename=doc.original_name,
                        content_disposition_type="inline")


@router.get("/api/documents/{document_id}/related")
def related_document(document_id: int) -> dict:
    """PDF visual asociado a un XML DIAN (adjunto del mismo correo)."""
    session = get_session_factory()()
    doc = session.get(Document, document_id)
    if not doc:
        session.close()
        raise HTTPException(status_code=404, detail="documento no existe")
    related_id = None
    if doc.ext == ".xml" and doc.email_id:
        pdfs = session.execute(
            select(Document).where(
                Document.email_id == doc.email_id, Document.ext == ".pdf"
            ).order_by(Document.id)
        ).scalars().all()
        siblings = [p for p in pdfs
                    if pdf_sibling_match(doc.original_name, p.original_name)]
        chosen = siblings[0] if siblings else (pdfs[0] if len(pdfs) == 1 else None)
        related_id = chosen.id if chosen else None
    session.close()
    return {"related_id": related_id}


def _render_invoice_html(cfdi: dict, doc) -> str:
    """Genera una vista HTML estilizada de la factura desde los datos parseados."""
    import html as html_mod

    def esc(v):
        return html_mod.escape(str(v)) if v is not None else ""

    tipo = (cfdi.get("tipo") or "I").upper()
    tipo_label = {
        "I": "Factura Electrónica de Venta", "E": "Nota de Crédito",
        "D": "Nota de Débito", "N": "Nómina", "P": "Pago",
    }.get(tipo, "Documento")
    fecha = cfdi.get("fecha")
    fecha_str = fecha.strftime("%d/%m/%Y") if fecha else ""
    moneda = (cfdi.get("moneda") or "COP").upper()
    total = cfdi.get("total")
    subtotal = cfdi.get("subtotal")
    lineas = cfdi.get("conceptos") or []

    def fmt(v):
        if v is None:
            return "—"
        return f"{float(v):,.2f}"

    filas = ""
    for ln in lineas:
        desc = ln.get("descripcion") or "—"
        cant = ln.get("cantidad")
        prec = ln.get("precio")
        sub = ln.get("subtotal")
        filas += f"""
        <tr>
          <td>{esc(desc)}</td>
          <td class="num">{fmt(cant)}</td>
          <td class="num">{fmt(prec)}</td>
          <td class="num">{fmt(sub)}</td>
        </tr>"""
    if not filas:
        filas = '<tr><td colspan="4" class="muted-td">Sin detalle de líneas</td></tr>'

    imp_filas = ""
    for imp in cfdi.get("impuestos") or []:
        imp_filas += f"""
        <tr>
          <td>{esc(imp.get('nombre') or 'Impuesto')}</td>
          <td class="num">{fmt(imp.get('base'))}</td>
          <td class="num">{fmt(imp.get('porcentaje'))}%</td>
          <td class="num">{fmt(imp.get('monto'))}</td>
        </tr>"""
    if not imp_filas:
        imp_filas = '<tr><td colspan="4" class="muted-td">Sin impuestos</td></tr>'

    pago = cfdi.get("pago") or ""
    cuche = cfdi.get("cuche_key") or ""

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>{esc(doc.original_name)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1c2733;
         margin: 0; background: #f0f2f5; padding: 24px; }}
  .sheet {{ max-width: 800px; margin: 0 auto; background: #fff;
           border-radius: 10px; box-shadow: 0 2px 12px rgba(0,0,0,.08);
           padding: 32px 36px; }}
  h1 {{ margin: 0 0 4px; font-size: 20px; color: #1a237e; }}
  .tipo {{ font-size: 13px; color: #5c6a7a; margin-bottom: 18px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 18px; }}
  .box {{ background: #f7f9fc; border: 1px solid #e3e8ef; border-radius: 8px; padding: 12px 14px; }}
  .box .lbl {{ font-size: 11px; color: #8a97a6; text-transform: uppercase; letter-spacing: .04em; }}
  .box .val {{ font-size: 14px; font-weight: 600; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 14px; }}
  th {{ background: #1a237e; color: #fff; text-align: left; padding: 8px 10px; font-size: 12px; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #edf0f4; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .muted-td {{ color: #9aa6b4; text-align: center; }}
  .totales {{ margin-left: auto; width: 300px; }}
  .totales .fila {{ display: flex; justify-content: space-between; padding: 5px 0; font-size: 13px; }}
  .totales .grande {{ font-weight: 700; font-size: 16px; border-top: 2px solid #1a237e;
                     padding-top: 8px; margin-top: 4px; }}
  .pie {{ margin-top: 18px; font-size: 11px; color: #8a97a6; border-top: 1px solid #edf0f4;
         padding-top: 10px; }}
  @media print {{ body {{ background: #fff; padding: 0; }} .sheet {{ box-shadow: none; }} }}
</style></head><body>
<div class="sheet">
  <h1>{tipo_label}</h1>
  <div class="tipo">{esc(doc.original_name)}</div>
  <div class="grid">
    <div class="box">
      <div class="lbl">Emisor</div>
      <div class="val">{esc(cfdi.get('emisor_nombre') or '—')}</div>
      {('<div class="lbl" style="margin-top:6px">NIT/RFC</div><div class="val">' + esc(cfdi.get('emisor_rfc') or '—') + '</div>') if cfdi.get('emisor_rfc') else ''}
    </div>
    <div class="box">
      <div class="lbl">Receptor</div>
      <div class="val">{esc(cfdi.get('receptor_nombre') or '—')}</div>
      {('<div class="lbl" style="margin-top:6px">NIT/RFC</div><div class="val">' + esc(cfdi.get('receptor_rfc') or '—') + '</div>') if cfdi.get('receptor_rfc') else ''}
    </div>
  </div>
  <div class="grid">
    <div class="box"><div class="lbl">Fecha de emisión</div><div class="val">{esc(fecha_str or '—')}</div></div>
    <div class="box"><div class="lbl">Folio / CUFE</div><div class="val">{esc(cuche or '—')}</div></div>
  </div>

  <table>
    <thead><tr><th>Descripción</th><th class="num">Cant.</th><th class="num">P. unitario</th><th class="num">Subtotal</th></tr></thead>
    <tbody>{filas}</tbody>
  </table>

  <table>
    <thead><tr><th>Impuesto</th><th class="num">Base</th><th class="num">%</th><th class="num">Monto</th></tr></thead>
    <tbody>{imp_filas}</tbody>
  </table>

  <div class="totales">
    <div class="fila"><span>Subtotal</span><span>{fmt(subtotal)} {esc(moneda)}</span></div>
    <div class="fila grande"><span>Total</span><span>{fmt(total)} {esc(moneda)}</span></div>
    {('<div class="fila"><span>Forma de pago</span><span>' + esc(pago) + '</span></div>') if pago else ''}
  </div>

  <div class="pie">Vista generada desde el XML de la factura. {('CUFE: ' + esc(cuche)) if cuche else ''}</div>
</div>
</body></html>"""


@router.get("/api/documents/{document_id}/preview-html")
def document_preview_html(document_id: int) -> Response:
    """Renderiza la factura desde el XML como HTML (cuando no hay PDF asociado)."""
    session = get_session_factory()()
    try:
        doc = session.get(Document, document_id)
        if not doc or not doc.stored_path or not os.path.exists(doc.stored_path):
            raise HTTPException(status_code=404, detail="documento no disponible")
        with open(doc.stored_path, "rb") as fh:
            data = fh.read()
        cfdi = parse_cfdi(data) or parse_ubl(data)
        if not cfdi:
            raise HTTPException(status_code=404, detail="no se pudo extraer la factura del XML")
        html = _render_invoice_html(cfdi, doc)
        return Response(html, media_type="text/html")
    finally:
        session.close()
