import logging
import os

from sqlalchemy import select

from shared.config import PROCESSING_DIR, QUEUE_PDF
from shared.db import Document, get_session_factory, init_db
from shared.queues import pop, queue_organize, queue_pdf

from app.extract import extract_pdf_text, read_xml

log = logging.getLogger("pdf-service")
logging.basicConfig(level=logging.INFO)

WANTED_EXTS = (".pdf", ".xml")


def process_document(session_factory, document_id: int) -> None:
    session = session_factory()
    try:
        doc = session.get(Document, document_id)
        if doc is None:
            log.warning("Documento %s no existe", document_id)
            return
        if not doc.stored_path or doc.status == "link_manual":
            return

        doc.status = "extracting"
        session.commit()

        if doc.ext == ".xml":
            cfdi = read_xml(doc.stored_path)
            doc.full_text = ""
            if cfdi is None:
                doc.status = "failed"
                doc.error = "XML no reconocido como CFDI"
                doc.needs_review = True
                session.commit()
                queue_organize(doc.id)
                return
        else:
            text, _used_ocr = extract_pdf_text(doc.stored_path)
            doc.full_text = text[:20000]
            if not text.strip():
                doc.status = "failed"
                doc.error = "No se pudo extraer texto (¿PDF dañado o solo imágenes?)"
                doc.needs_review = True
                session.commit()
                queue_organize(doc.id)
                return

        doc.status = "extracted"
        doc.error = ""
        session.commit()
        queue_organize(document_id)
        log.info("Documento %s procesado -> cola organizacion", document_id)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        fresh = session.get(Document, document_id)
        if fresh:
            fresh.status = "failed"
            fresh.error = f"{type(exc).__name__}: {exc}"
            fresh.needs_review = True
            session.commit()
            queue_organize(document_id)
        log.exception("Error procesando documento %s", document_id)
    finally:
        session.close()


def recover_stuck_documents(session_factory) -> int:
    """Re-encola documentos pendientes/atascados y registra huérfanos en /processing."""
    session = session_factory()
    queued = 0
    try:
        stuck = session.execute(
            select(Document.id).where(Document.status.in_(("pending", "extracting")))
        ).scalars().all()
        for doc_id in stuck:
            queue_pdf(int(doc_id))
            queued += 1

        known = set(session.execute(select(Document.stored_path)).scalars())
        orphans = 0
        if os.path.isdir(PROCESSING_DIR):
            for name in sorted(os.listdir(PROCESSING_DIR)):
                ext = os.path.splitext(name)[1].lower()
                path = os.path.join(PROCESSING_DIR, name)
                if ext not in WANTED_EXTS or not os.path.isfile(path):
                    continue
                if path in known:
                    continue
                doc = Document(original_name=name, stored_path=path,
                               source_type="manual", ext=ext, status="pending")
                session.add(doc)
                session.flush()
                session.refresh(doc)
                queue_pdf(doc.id)
                orphans += 1
        session.commit()
        if stuck:
            log.info("Recuperados %s documentos pendientes", len(stuck))
        if orphans:
            log.info("Registrados %s archivos huérfanos de processing/", orphans)
    except Exception:  # noqa: BLE001
        session.rollback()
        log.exception("Fallo recuperando documentos atascados")
    finally:
        session.close()
    return queued


def main() -> None:
    init_db()
    session_factory = get_session_factory()
    recover_stuck_documents(session_factory)
    log.info("pdf-service escuchando cola: %s", QUEUE_PDF)
    while True:
        payload = pop(QUEUE_PDF, timeout=5)
        if not payload:
            continue
        try:
            process_document(session_factory, int(payload["document_id"]))
        except Exception:  # noqa: BLE001
            log.exception("Fallo grave en mensaje: %s", payload)


if __name__ == "__main__":
    main()
