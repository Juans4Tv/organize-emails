"""Extract invoice issue date (fecha de emisión) from PDF text.

Searches for common Colombian invoice date patterns:
  - "Fecha de factura: DD/MM/YYYY"
  - "Fecha y hora Factura Generación DD/MM/YYYY"
  - "DD de MES de YYYY"
  - ISO timestamps YYYY-MM-DD

Returns datetime or None if no date found.
"""
import re
from datetime import datetime

_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

_DATE_LABEL_RE = re.compile(
    r"Fecha\s+(?:de\s+)?(?:factura|emisi[oó]n|expedici[oó]n)"
    r"[\s:\n]*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})",
    re.IGNORECASE | re.DOTALL,
)

_DATE_GENERACION_RE = re.compile(
    r"Fecha\s+y\s+hora\s+Factura\s*\n?\s*Generaci[oó]n"
    r"[\s:\n]*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})",
    re.IGNORECASE | re.DOTALL,
)

_DATE_WRITTEN_RE = re.compile(
    r"Fecha\s+(?:de\s+)?(?:factura|emisi[oó]n|expedici[oó]n)"
    r"[\s:\n]*(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})",
    re.IGNORECASE | re.DOTALL,
)

_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def extract_issue_date(text: str) -> datetime | None:
    """Extract the invoice issue date from full_text.

    Priority:
      1. 'Fecha de factura/emisión' with DD/MM/YYYY
      2. 'Fecha y hora Factura Generación' with DD/MM/YYYY
      3. 'Fecha de factura/emisión' with DD de MES de YYYY
      4. ISO date YYYY-MM-DD anywhere
    Returns None if nothing found.
    """
    if not text:
        return None

    for m in _DATE_LABEL_RE.finditer(text):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2000 <= y <= 2099 and 1 <= mo <= 12 and 1 <= d <= 31:
            try:
                return datetime(y, mo, d)
            except ValueError:
                continue

    for m in _DATE_GENERACION_RE.finditer(text):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2000 <= y <= 2099 and 1 <= mo <= 12 and 1 <= d <= 31:
            try:
                return datetime(y, mo, d)
            except ValueError:
                continue

    for m in _DATE_WRITTEN_RE.finditer(text):
        d = int(m.group(1))
        month_num = _MONTHS.get(m.group(2).lower())
        y = int(m.group(3))
        if month_num and 2000 <= y <= 2099 and 1 <= d <= 31:
            try:
                return datetime(y, month_num, d)
            except ValueError:
                continue

    for m in _ISO_RE.finditer(text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2000 <= y <= 2099 and 1 <= mo <= 12 and 1 <= d <= 31:
            try:
                return datetime(y, mo, d)
            except ValueError:
                continue

    return None
