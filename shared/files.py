import os
import shutil

from shared.config import FACTURAS_DIR
from shared.parsing.places import sanitize_folder


def _dedupe_target(target_dir: str, filename: str) -> str:
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(target_dir, filename)
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(target_dir, f"{base}-{counter}{ext}")
        counter += 1
    return candidate


def month_bucket(doc_date) -> str:
    if doc_date:
        return doc_date.strftime("%Y-%m")
    return "sin-fecha"


def move_document_file(doc, place_name: str) -> str | None:
    """Mueve el archivo del documento a facturas/<Lugar>/<YYYY-MM>/.

    Devuelve la ruta final o None si no hay archivo físico.
    """
    if not doc.stored_path or not os.path.exists(doc.stored_path):
        return None

    folder = os.path.join(
        FACTURAS_DIR,
        sanitize_folder(place_name),
        month_bucket(doc.doc_date),
    )
    os.makedirs(folder, exist_ok=True)

    filename = sanitize_folder(os.path.basename(doc.original_name), max_len=120)
    target = _dedupe_target(folder, filename)
    shutil.move(doc.stored_path, target)
    doc.stored_path = target
    return target
