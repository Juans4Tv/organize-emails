import re
from datetime import datetime
from xml.etree import ElementTree

_TZ_SUFFIX_RE = re.compile(r"(?:[+-]\d{2}:\d{2}|Z)$")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _find_first(root: ElementTree.Element, name: str) -> ElementTree.Element | None:
    target = name.lower()
    for el in root.iter():
        if _local(el.tag) == target:
            return el
    return None


def parse_cfdi(xml_bytes: bytes) -> dict | None:
    """Parsea un XML CFDI (3.x / 4.x). Devuelve None si no es CFDI."""
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return None

    if _local(root.tag) != "comprobante":
        return None

    attrs = {_local(k).lower(): v for k, v in root.attrib.items()}

    result: dict = {
        "version": attrs.get("version", ""),
        "tipo": attrs.get("tipodecomprobante", "").upper(),
        "total": _to_float(attrs.get("total")),
        "subtotal": _to_float(attrs.get("subtotal")),
        "moneda": attrs.get("moneda", "MXN").upper() or "MXN",
        "fecha": _parse_date(attrs.get("fecha", "")),
        "serie": attrs.get("serie", ""),
        "folio": attrs.get("folio", ""),
        "emisor_nombre": "",
        "emisor_rfc": "",
        "receptor_nombre": "",
        "receptor_rfc": "",
    }

    emisor = _find_first(root, "emisor")
    if emisor is not None:
        eattrs = {_local(k).lower(): v for k, v in emisor.attrib.items()}
        result["emisor_nombre"] = (eattrs.get("nombre") or "").strip()
        result["emisor_rfc"] = (eattrs.get("rfc") or "").strip()

    receptor = _find_first(root, "receptor")
    if receptor is not None:
        rattrs = {_local(k).lower(): v for k, v in receptor.attrib.items()}
        result["receptor_nombre"] = (rattrs.get("nombre") or "").strip()
        result["receptor_rfc"] = (rattrs.get("rfc") or "").strip()

    conceptos: list[str] = []
    concepto_node = _find_first(root, "conceptos")
    if concepto_node is not None:
        for el in concepto_node.iter():
            if _local(el.tag) == "concepto":
                cattrs = {_local(k).lower(): v for k, v in el.attrib.items()}
                desc = cattrs.get("descripcion", "")
                if desc:
                    conceptos.append(desc.strip())
    result["conceptos"] = conceptos[:20]

    return result


def classify_flow(cfdi: dict, own_rfc: str = "") -> tuple[str, float]:
    """Devuelve (flujo, confianza): 'gasto' o 'ganancia' desde la perspectiva del usuario."""
    tipo = (cfdi.get("tipo") or "").upper()
    own = (own_rfc or "").strip().upper()

    if own:
        emisor_rfc = (cfdi.get("emisor_rfc") or "").upper()
        receptor_rfc = (cfdi.get("receptor_rfc") or "").upper()
        if emisor_rfc and emisor_rfc == own:
            return "ganancia", 0.95
        if receptor_rfc and receptor_rfc == own and tipo == "I":
            return "gasto", 0.95

    if tipo == "E":
        return "ganancia", 0.7
    if tipo == "N":
        return "neutral", 0.6
    if tipo == "I":
        return "gasto", 0.8
    return "desconocido", 0.0


def _to_float(raw: str | None) -> float | None:
    try:
        return round(float(raw), 2) if raw else None
    except ValueError:
        return None


def _parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    cleaned = _TZ_SUFFIX_RE.sub("", raw)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None
