"""Parser para facturación electrónica colombiana (DIAN, UBL 2.x).

Soporta el sobre `AttachedDocument` (que trae la factura real embebida en
base64 o como texto en cbc:Description) y también `Invoice`, `CreditNote` y
`DebitNote` UBL directos. Devuelve el MISMO shape que
shared.parsing.cfdi.parse_cfdi para que organizer-service lo consuma igual.
"""
import base64
import os
import re
from datetime import datetime
from xml.etree import ElementTree

_TIPO_CODE_MAP = {
    "01": "I",   # Factura de venta
    "02": "E",   # Nota de crédito
    "03": "D",   # Nota de débito -> se trata como neutro
}

# Doc raíz -> tipo de comprobante
_ROOT_TIPO_MAP = {
    "invoice": "I",
    "creditnote": "E",
    "debitnote": "D",
}

_AD_FV_PREFIX_RE = re.compile(r"^(?:ad|fv)", re.IGNORECASE)


def cuche_key_from_filename(filename: str) -> str:
    """Extract CUFE from DIAN filename: ad0901...fb -> 0901...fb."""
    stem = os.path.splitext(os.path.basename(filename))[0].strip().lower()
    return _AD_FV_PREFIX_RE.sub("", stem, count=1)


def cuche_key_from_xml(root: ElementTree.Element) -> str:
    """Extract CUFE from XML ID element at root level."""
    for child in root:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "ID" and child.text and len(child.text.strip()) > 3:
            return child.text.strip()
    return ""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _find_text(root: ElementTree.Element, name: str) -> str:
    target = name.lower()
    for el in root.iter():
        if _local(el.tag) == target and (el.text or "").strip():
            return el.text.strip()
    return ""


def parse_ubl(xml_bytes: bytes) -> dict | None:
    """Devuelve dict compatible con parse_cfdi o None si no es UBL/DIAN."""
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return None

    root_name = _local(root.tag)

    if root_name == "attacheddocument":
        # 1) factura embebida en base64 (EmbeddedDocumentBinaryObject)
        embedded = _find_embedded(root)
        if embedded:
            try:
                inner = base64.b64decode(embedded)
                doc = ElementTree.fromstring(inner)
                if _local(doc.tag) in _ROOT_TIPO_MAP:
                    return _from_document(doc, root)
            except (ValueError, ElementTree.ParseError):
                pass
        # 2) factura embebida como texto XML dentro de cbc:Description
        doc = _find_description_doc(root)
        if doc is not None:
            return _from_document(doc, root)
        # 3) datos del propio sobre AttachedDocument
        return _from_envelope(root)

    if root_name in _ROOT_TIPO_MAP:
        return _from_document(root)

    return None


def _find_embedded(root: ElementTree.Element) -> str | None:
    for el in root.iter():
        if _local(el.tag) == "embeddeddocumentbinaryobject":
            text = (el.text or "").strip()
            if text:
                return text
    return None


def _find_description_doc(root: ElementTree.Element):
    """Busca un Invoice/CreditNote/DebitNote embebido como texto en Description."""
    for el in root.iter():
        if _local(el.tag) != "description":
            continue
        text = (el.text or "").strip()
        if "<?xml" not in text[:120] and not re.search(r"<(?:Invoice|CreditNote|DebitNote)\b", text[:1200]):
            continue
        try:
            candidate = ElementTree.fromstring(text.encode())
        except (ValueError, ElementTree.ParseError):
            continue
        if _local(candidate.tag) in _ROOT_TIPO_MAP:
            return candidate
    return None


def _from_envelope(root: ElementTree.Element) -> dict | None:
    def registration(party_tag: str) -> str:
        for el in root.iter():
            if _local(el.tag) != party_tag.lower():
                continue
            name = _party_name(el)
            if name:
                return name
        return ""

    emisor = registration("senderparty")
    receptor = registration("receiverparty")
    if not emisor and not receptor:
        return None

    return {
        "version": _find_text(root, "ublversionid") or "DIAN",
        "tipo": "I",
        "total": _to_float(_find_text(root, "payableamount")),
        "subtotal": _to_float(_find_text(root, "taxinclusiveamount")),
        "moneda": "COP",
        "fecha": _parse_date(_find_text(root, "issuedate")),
        "serie": "",
        "folio": _find_text(root, "parentdocumentid"),
        "emisor_nombre": emisor,
        "emisor_rfc": "",
        "receptor_nombre": receptor,
        "receptor_rfc": "",
        "conceptos": [],
        "impuestos": [],
        "pago": _find_text(root, "paymentmeanscode"),
        "cuche_key": cuche_key_from_xml(root),
    }


def _party_name(party_el: ElementTree.Element) -> str:
    """Extrae el nombre de la party: RegistrationName, PartyName/Name o Name."""
    for sub in party_el.iter():
        tag = _local(sub.tag)
        if tag in ("registrationname", "partyname") and (sub.text or "").strip():
            return sub.text.strip()
    # fallback: <cbc:Name> dentro de PartyName u otro elemento
    for sub in party_el.iter():
        if _local(sub.tag) == "name" and (sub.text or "").strip():
            return sub.text.strip()
    return ""


def _party_id(party_el: ElementTree.Element) -> str:
    for sub in party_el.iter():
        if _local(sub.tag) == "id" and (sub.text or "").strip():
            return sub.text.strip()
    return ""


def _find_party(doc: ElementTree.Element, party_tag: str) -> ElementTree.Element | None:
    target = party_tag.lower()
    for el in doc.iter():
        if _local(el.tag) == target:
            return el
    return None


def _extract_lines(doc: ElementTree.Element, line_tag: str) -> list[dict]:
    """Extrae líneas de detalle (InvoiceLine / CreditNoteLine)."""
    lines: list[dict] = []
    target = line_tag.lower()
    for el in doc.iter():
        if _local(el.tag) != target:
            continue
        desc = ""
        cantidad = None
        precio = None
        subtotal = None
        for sub in el.iter():
            tag = _local(sub.tag)
            if tag == "description" and (sub.text or "").strip():
                desc = sub.text.strip()
            elif tag in ("invoicedquantity", "creditedquantity"):
                cantidad = _to_float(sub.text or "")
            elif tag == "priceamount":
                precio = _to_float(sub.text or "")
            elif tag == "lineextensionamount":
                subtotal = _to_float(sub.text or "")
        lines.append({
            "descripcion": desc,
            "cantidad": cantidad,
            "precio": precio,
            "subtotal": subtotal,
        })
    return lines[:50]


def _extract_taxes(doc: ElementTree.Element) -> list[dict]:
    """Extrae impuestos (TaxTotal/TaxSubtotal)."""
    taxes: list[dict] = []
    for el in doc.iter():
        if _local(el.tag) != "taxsubtotal":
            continue
        base = None
        monto = None
        porcentaje = None
        nombre = ""
        for sub in el.iter():
            tag = _local(sub.tag)
            if tag == "taxableamount":
                base = _to_float(sub.text or "")
            elif tag == "taxamount":
                monto = _to_float(sub.text or "")
            elif tag == "percent":
                porcentaje = _to_float(sub.text or "")
            elif tag == "name" and (sub.text or "").strip():
                nombre = sub.text.strip()
        taxes.append({"base": base, "monto": monto, "porcentaje": porcentaje, "nombre": nombre})
    return taxes[:10]


def _from_document(doc: ElementTree.Element, envelope: ElementTree.Element | None = None) -> dict | None:
    root_name = _local(doc.tag)
    tipo = _ROOT_TIPO_MAP.get(root_name, "I")

    total = None
    moneda = "COP"
    for el in doc.iter():
        if _local(el.tag) == "payableamount":
            total = _to_float((el.text or "").strip())
            moneda = (el.attrib.get("currencyID") or "COP").upper()
            break

    subtotal = None
    for el in doc.iter():
        if _local(el.tag) == "taxinclusiveamount":
            subtotal = _to_float((el.text or "").strip())
            if subtotal is not None:
                break
    if subtotal is None:
        for el in doc.iter():
            if _local(el.tag) == "lineextensionamount":
                subtotal = _to_float((el.text or "").strip())
                if subtotal is not None:
                    break

    code = _find_text(doc, "invoicetypecode") or _find_text(doc, "creditnotetypecode")
    tipo = _TIPO_CODE_MAP.get(code, tipo)

    fecha = _parse_date(_find_text(doc, "issuedate"))

    supplier = _find_party(doc, "accountingsupplierparty")
    customer = _find_party(doc, "accountingcustomerparty")

    emisor = _party_name(supplier) if supplier is not None else ""
    emisor_rfc = _party_id(supplier) if supplier is not None else ""
    receptor = _party_name(customer) if customer is not None else ""
    receptor_rfc = _party_id(customer) if customer is not None else ""

    # Fallback: si la factura embebida no trae emisor/receptor, usar el sobre
    # AttachedDocument (SenderParty/ReceiverParty).
    if envelope is not None:
        if not emisor:
            emisor = _registration_from(envelope, "senderparty")
            emisor_rfc = emisor_rfc or _registration_id(envelope, "senderparty")
        if not receptor:
            receptor = _registration_from(envelope, "receiverparty")
            receptor_rfc = receptor_rfc or _registration_id(envelope, "receiverparty")

    line_tag = "creditnoteline" if root_name == "creditnote" else "invoiceline"

    return {
        "version": _find_text(doc, "ublversion") or "DIAN",
        "tipo": tipo,
        "total": total,
        "subtotal": subtotal,
        "moneda": moneda,
        "fecha": fecha,
        "serie": "",
        "folio": _find_text(doc, "id") if root_name != "invoice" else "",
        "emisor_nombre": emisor,
        "emisor_rfc": emisor_rfc,
        "receptor_nombre": receptor,
        "receptor_rfc": receptor_rfc,
        "conceptos": _extract_lines(doc, line_tag),
        "impuestos": _extract_taxes(doc),
        "pago": _find_text(doc, "paymentmeanscode"),
        "cuche_key": cuche_key_from_xml(doc),
    }


def _registration_from(root: ElementTree.Element, party_tag: str) -> str:
    """Busca el RegistrationName/Name dentro de una party del sobre."""
    target = party_tag.lower()
    for el in root.iter():
        if _local(el.tag) != target:
            continue
        name = _party_name(el)
        if name:
            return name
    return ""


def _registration_id(root: ElementTree.Element, party_tag: str) -> str:
    target = party_tag.lower()
    for el in root.iter():
        if _local(el.tag) != target:
            continue
        for sub in el.iter():
            if _local(sub.tag) == "companyid" and (sub.text or "").strip():
                return sub.text.strip()
    return ""


def _to_float(raw: str | None) -> float | None:
    try:
        return round(float(raw), 2) if raw else None
    except ValueError:
        return None


def _parse_date(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    cleaned = raw.split("T")[0]  # YYYY-MM-DD o inicio de timestamp
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d")
    except ValueError:
        return None
