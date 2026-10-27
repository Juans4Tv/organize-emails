import re

_CURRENCY_RE = re.compile(r"\b(COP|MXN|USD|EUR|MX|US)\b", re.IGNORECASE)

# Etiquetas de monto priorizadas (de mayor a menor confianza).
_STRONG_LABEL_RE = re.compile(
    r"(?<![a-z])(?:"
    r"total\s+a\s+pagar|valor\s+total|valor\s+a\s+pagar|monto\s+total|"
    r"importe\s+total|total\s+facturado|valor\s+facturado|total\s+de\s+la\s+compra|"
    r"gran\s+total|saldo\s+total|a\s+su\s+cargo"
    r")[^\d\$]{0,40}?\$?\s*([0-9][\d,\.\s]{0,20})",
    re.IGNORECASE,
)
_TOTAL_LABEL_RE = re.compile(
    r"(?<![a-z])(?:importe\s+)?total[^\d\$]{0,40}?\$?\s*([0-9][\d,\.\s]{0,20})",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(r"\$\s*([0-9][\d,\.\s]{0,20})")


def _to_number(raw: str) -> float | None:
    cleaned = re.sub(r"[\s\$]", "", raw)
    if not cleaned:
        return None
    has_comma = "," in cleaned
    has_dot = "." in cleaned

    # Ambos separadores: el que esté más a la derecha es el decimal.
    #   "1.234.567,89" (es-CO): puntos miles, coma decimal
    #   "15,000.00"  (US/MX):   coma miles, punto decimal
    if has_comma and has_dot:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    # solo puntos: "2.700.000" / "2.700.000.00" -> miles (y decimal si cierra en 2)
    elif has_dot:
        parts = cleaned.split(".")
        if len(parts) > 2:
            # 2.700.000.00 -> último punto decimal (≤2 dígitos), resto miles
            if len(parts[-1]) <= 2:
                cleaned = cleaned.replace(".", "", len(parts) - 2)
            else:
                cleaned = cleaned.replace(".", "")
        elif len(parts) == 2:
            # 2.700 -> 2700 (miles) o 2.50 -> 2.50 (decimal)
            if len(parts[1]) == 3:
                cleaned = parts[0] + parts[1]
            else:
                cleaned = cleaned  # dejar decimal como está
    # solo comas: "1,200" -> 1200 (miles) o "12,50" -> 12.5 (decimal)
    elif has_comma:
        parts = cleaned.split(",")
        if len(parts[-1]) == 3 and len(parts) > 1:
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def _looks_like_amount(value: float) -> bool:
    return 0.01 <= value <= 100_000_000


def _first_labeled(text: str, regex: re.Pattern) -> tuple[float | None, int]:
    for match in regex.finditer(text):
        value = _to_number(match.group(1))
        if value is not None and _looks_like_amount(value):
            return value, match.start()
    return None, -1


def extract_amount(text: str) -> tuple[float | None, float]:
    """Devuelve (monto, confianza). Confianza entre 0 y 1."""
    if not text:
        return None, 0.0

    value, _pos = _first_labeled(text, _STRONG_LABEL_RE)
    if value is not None:
        return value, 0.92

    value, _pos = _first_labeled(text, _TOTAL_LABEL_RE)
    if value is not None:
        return value, 0.85

    candidates: list[float] = []
    positions: list[int] = []
    for match in _MONEY_RE.finditer(text):
        v = _to_number(match.group(1))
        if v is not None and _looks_like_amount(v):
            candidates.append(v)
            positions.append(match.start())

    if not candidates:
        plain = re.findall(r"(?<![\d.,])([1-9]\d{1,7}(?:\.\d{1,2})?)(?![\d.])", text)
        candidates.extend(v for v in (_to_number(p) for p in plain) if v is not None)

    if not candidates:
        return None, 0.0

    largest_idx = max(range(len(candidates)), key=lambda i: candidates[i])
    largest = candidates[largest_idx]
    echoes = [c for c in candidates if abs(c - largest) < 0.05]
    # si el mayor aparece temprano en el documento es más probable que sea el total
    early_bonus = 0.05 if positions and positions[largest_idx] < len(text) * 0.5 else 0.0
    confidence = min(0.6, 0.4 if len(echoes) >= 2 else 0.3) + early_bonus

    return round(largest, 2), confidence


def extract_currency(text: str) -> str:
    match = _CURRENCY_RE.search(text or "")
    if not match:
        return "COP"
    token = match.group(1).upper()
    if token in ("USD", "US"):
        return "USD"
    if token == "EUR":
        return "EUR"
    if token == "MXN":
        return "MXN"
    return "COP"
