import re
import unicodedata

LEGAL_SUFFIXES = [
    r"S\s*\.?\s*A\s*\.?\s*(?:DE\s+C\s*\.?\s*V\s*\.?)?",
    r"S\s*\.?\s*A\s*\.?\s*P\s*\.?\s*I\s*\.?",
    r"S\s*\.?\s*DE\s*R\s*\.?\s*L\s*\.?\s*(?:DE\s*C\s*\.?\s*V\s*\.?)?",
    r"S\s*\.?\s*C\s*\.?",
    r"S\s*\.?\s*S\s*\.?",
]

_SUFFIX_RE = re.compile(
    r"\b(?:" + "|".join(LEGAL_SUFFIXES) + r")\b", re.IGNORECASE
)

_RFC_RE = re.compile(r"\b([A-ZÑ&]{3,4}\d{6}(?:[A-Z0-9]{3})?)\b")

_LABEL_RE = re.compile(
    r"(?:raz[oó]n\s+social|nombre\s+comercial|emisor|expedido\s+por|"
    r"proveedor|empresa|establecimiento|sucursal)\s*[:\-]?\s*(.{2,60})",
    re.IGNORECASE,
)

_NOISE_WORDS = {
    "factura", "ticket", "recibo", "total", "subtotal", "iva", "fecha",
    "cliente", "rfc", "pago", "nota", "de", "del", "la", "el", "y",
}


def strip_accents(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)
    )


def normalize_place_name(raw: str) -> str:
    if not raw:
        return ""
    value = raw.strip()
    value = _SUFFIX_RE.sub(" ", value)
    value = re.sub(r"\s+", " ", value).strip(" .,-–—:;")
    if not value:
        return ""
    words = []
    for word in value.split(" "):
        clean = word.strip(".")
        if not clean:
            continue
        words.append(clean.capitalize() if clean.islower() or clean.isupper() else clean)
    return " ".join(words)[:200]


def sanitize_folder(name: str, max_len: int = 80) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', "-", name or "")
    cleaned = re.sub(r"[\s\-]*-[\s\-]*", "-", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return (cleaned.strip(" -.") or "Sin-Lugar")[:max_len].strip(" -.")


def detect_place_from_text(text: str) -> tuple[str, float]:
    """Devuelve (nombre_detectado_normalizado, confianza)."""
    if not text:
        return "", 0.0

    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    def emit(raw: str, conf: float) -> tuple[str, float]:
        normalized = normalize_place_name(raw)
        return (normalized, conf) if normalized else ("", 0.0)

    # 1. Etiquetas explícitas: "Razón social: X", "Emisor: X"...
    for line in lines[:40]:
        match = _LABEL_RE.search(line)
        if match:
            candidate = _clean_candidate(match.group(1))
            if candidate:
                result = emit(candidate, 0.75)
                if result[0]:
                    return result

    # 2. Línea cercana a un RFC (emisor suele declararse junto al RFC)
    for idx, line in enumerate(lines[:60]):
        if _RFC_RE.search(line.upper()):
            window = lines[max(0, idx - 2):idx + 2]
            for w in window:
                candidate = _clean_candidate(w)
                if candidate and not _RFC_RE.search(candidate.upper()):
                    result = emit(candidate, 0.65)
                    if result[0]:
                        return result

    # 3. Primera línea con forma de nombre de empresa/negocio
    for line in lines[:8]:
        candidate = _clean_candidate(line)
        if candidate and len(candidate) >= 4:
            upper_ratio = sum(1 for c in candidate if c.isupper()) / max(1, len(candidate.replace(" ", "")))
            confidence = 0.5 if upper_ratio > 0.6 else 0.35
            result = emit(candidate, confidence)
            if result[0]:
                return result

    return "", 0.0


def _clean_candidate(raw: str) -> str:
    value = raw.strip()
    # corta cuando la línea trae más datos pegados (RFC, dirección, etc.)
    value = re.split(r"\s{2,}|\t|,\s*(?:col|c\.p|cp\b)", value, flags=re.IGNORECASE)[0]
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"[*_|#\[\]{}<>]", " ", value)
    value = re.sub(r"\d{4,}", "", value)
    value = re.sub(r"\s+", " ", value).strip(" .,:;-–—")

    lowered_words = set(strip_accents(value.lower()).split())
    if not value or len(value) < 3:
        return ""
    if lowered_words <= _NOISE_WORDS:
        return ""
    if re.fullmatch(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ]+", value):
        return ""
    if "@" in value or "$" in value:
        return ""
    if re.search(r"\brfc\b", strip_accents(value), re.IGNORECASE):
        return ""

    letters = len(re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", value))
    non_space = len(value.replace(" ", ""))
    if non_space == 0 or letters / non_space < 0.6:
        return ""

    return value
