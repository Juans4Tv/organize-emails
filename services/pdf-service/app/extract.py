import io
import logging
import os

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from shared.parsing.cfdi import parse_cfdi
from shared.parsing.ubl import parse_ubl

log = logging.getLogger("pdf-service")

OCR_MIN_CHARS = 60
OCR_DPI = 200
OCR_MAX_PAGES = 4


def extract_pdf_text(path: str) -> tuple[str, bool]:
    """Devuelve (texto, uso_ocr)."""
    text = ""
    with fitz.open(path) as doc:
        for page in doc:
            text += page.get_text("text") + "\n"

    if len(text.strip()) >= OCR_MIN_CHARS:
        return _normalize(text), False

    log.info("PDF sin capa de texto, aplicando OCR: %s", os.path.basename(path))
    ocr_text = _ocr_pdf(path)
    return _normalize((text + "\n" + ocr_text)), True


def _ocr_pdf(path: str) -> str:
    parts: list[str] = []
    try:
        with fitz.open(path) as doc:
            for i, page in enumerate(doc):
                if i >= OCR_MAX_PAGES:
                    break
                pix = page.get_pixmap(dpi=OCR_DPI)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                parts.append(pytesseract.image_to_string(img, lang="spa"))
    except RuntimeError:
        log.exception("Fallo render/OCR")
    return "\n".join(parts)


def extract_image_text(path: str) -> str:
    img = Image.open(path)
    return pytesseract.image_to_string(img, lang="spa")


def read_xml(path: str):
    """Parsea XML: intenta CFDI (México) y luego UBL/DIAN (Colombia)."""
    with open(path, "rb") as fh:
        data = fh.read()
    return parse_cfdi(data) or parse_ubl(data)


def _normalize(text: str) -> str:
    return "\n".join(
        ln.rstrip() for ln in (text or "").splitlines() if ln.strip()
    ).strip()
