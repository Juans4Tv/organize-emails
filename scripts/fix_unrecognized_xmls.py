"""One-off: clasifica los 'XML no reconocido como CFDI'.
- HTML (descargas fallidas) -> no_factura
- XML real (DIAN/UBL) -> reencola para extraccion con el nuevo parser
"""
import os

from sqlalchemy import select

from shared.config import PROCESSING_DIR
from shared.db import Document, get_session_factory, init_db
from shared.queues import queue_pdf

HTML_MARKERS = (b"<!doctype html", b"<html")


def is_html(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            head = fh.read(300)
    except OSError:
        return True  # archivo perdido: no vale reprocessar
    low = b" ".join(head.split()).lower()
    return any(m in low for m in HTML_MARKERS)


def main() -> None:
    init_db()
    session = get_session_factory()()
    html_count = 0
    requeued = 0
    try:
        docs = session.execute(
            select(Document).where(Document.error.like("XML no reconocido%"))
        ).scalars().all()
        for doc in docs:
            if doc.stored_path and os.path.exists(doc.stored_path) and not is_html(doc.stored_path):
                doc.status = "pending"
                doc.error = ""
                session.flush()
                queue_pdf(doc.id)
                requeued += 1
            else:
                doc.doc_kind = "no_factura"
                doc.needs_review = False
                doc.status = "organized"
                doc.confidence = max(doc.confidence or 0.0, 0.6)
                html_count += 1
        session.commit()
    finally:
        session.close()
    print(f"HTML->no_factura: {html_count}; DIAN reencolados: {requeued}")


if __name__ == "__main__":
    main()
