"""Parseo de montos del usuario y normalización de moneda."""


def parse_user_amount(raw) -> float:
    """Convierte '1.234.567,89', '1234567.89', '1,234,567' o '1234567' a float.

    Lanza ValueError si no se puede interpretar.
    """
    s = str(raw).strip().replace("$", "").replace(" ", "")
    if not s:
        raise ValueError("monto vacío")

    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_comma:
        head, _, tail = s.rpartition(",")
        digits_tail = tail.isdigit()
        if digits_tail and len(tail) == 3 and head:
            s = (head + tail).replace(",", "")  # 1,234,567 -> miles
        elif digits_tail:
            s = head.replace(",", "") + "." + tail
        else:
            raise ValueError(f"monto inválido: {raw!r}")
    else:
        parts = s.split(".")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
            s = s.replace(".", "")  # 1.234.567 / 1234.567 -> miles

    value = float(s)
    return round(value, 2)


def normalize_amount(amount, currency, base: str = "COP",
                     fx_usd_cop=None) -> tuple[float | None, str]:
    """Convierte amount a la moneda base única (COP o USD).

    - Misma moneda -> sin cambio.
    - USD <-> COP usando fx_usd_cop (1 USD = fx COP).
    - Moneda desconocida o vacía -> se asume que ya está en la base.
    - amount None -> (None, base).
    """
    base = (base or "COP").upper()
    if amount is None:
        return None, base
    cur = (currency or "").strip().upper() or base
    if cur == base:
        return round(float(amount), 2), base
    try:
        fx = float(fx_usd_cop)
    except (TypeError, ValueError):
        fx = 0.0
    if fx <= 0:
        return round(float(amount), 2), base
    if cur == "USD" and base == "COP":
        return round(float(amount) * fx, 2), base
    if cur == "COP" and base == "USD":
        return round(float(amount) / fx, 2), base
    return round(float(amount), 2), base
