"""Utilidades de nombres de archivo y de partes (sin dependencias externas)."""
import os
import re
import unicodedata

_AD_FV_PREFIX_RE = re.compile(r"^(ad|fv)(?=.)")


def _name_tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFD", (value or "").lower())
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    return {t for t in re.findall(r"[a-z]{3,}", normalized)}


def name_matches_owner(name_a: str, name_b: str, min_overlap: int = 2) -> bool:
    """True si dos razones sociales parecen la misma persona/empresa.

    Compara tokens normalizados (sin acentos ni mayusculas): coincide si
    uno contiene al conjunto del otro (p.ej. nombre + apellidos vs nombre
    completo) o si comparten al menos `min_overlap` tokens.
    """
    ta = _name_tokens(name_a)
    tb = _name_tokens(name_b)
    if not ta or not tb:
        return False
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(shorter) >= 2 and shorter <= longer:
        return True
    return len(ta & tb) >= min_overlap


def pdf_sibling_match(xml_name: str, pdf_name: str) -> bool:
    """True si el PDF parece la representación visual del XML DIAN.

    Empareja por stem del archivo: idéntico, o tras quitar el prefijo
    'ad'/'fv' (AttachedDocument vs Factura de venta, p.ej.
    ad0901…xml ↔ fv0901…pdf comparten el CUFE).
    """
    xml_stem = _AD_FV_PREFIX_RE.sub("", os.path.splitext(xml_name)[0].strip().lower())
    pdf_stem = _AD_FV_PREFIX_RE.sub("", os.path.splitext(pdf_name)[0].strip().lower())
    return bool(xml_stem) and xml_stem == pdf_stem
