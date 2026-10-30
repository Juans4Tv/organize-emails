import hashlib
import logging
import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests
from imap_tools import AND, MailBox
from sqlalchemy import func, select

from shared.archives import ArchivePasswordError, extract_members, is_archive_ext
from shared.crypto import decrypt_secret
from shared.config import FACTURAS_DIR, INBOX_DIR, PROCESSING_DIR
from shared.db import Document, Email, Job, Setting, get_session_factory
from shared.queues import queue_pdf

log = logging.getLogger("email-service")
logging.basicConfig(level=logging.INFO)

HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
LINK_HINT_RE = re.compile(
    r"(factura|descarga|download|\.xml(\?|$)|comprobante|archivo)", re.IGNORECASE
)
HTML_SNIFF_RE = re.compile(rb"^\s*(?:<!doctype\s+html|<html[\s>])", re.IGNORECASE)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OpenOrganizador/1.0"
WANTED_EXTS = {".pdf", ".xml"}


def _get_settings(session) -> dict:
    rows = session.execute(select(Setting)).scalars().all()
    data = {r.key: r.value for r in rows}
    data["imap_password"] = decrypt_secret(data.get("imap_password"))
    return data


def _save_bytes(payload: bytes, ext: str) -> str:
    os.makedirs(PROCESSING_DIR, exist_ok=True)
    stored_path = os.path.join(PROCESSING_DIR, f"{uuid.uuid4().hex[:16]}{ext}")
    with open(stored_path, "wb") as fh:
        fh.write(payload)
    return stored_path


def _file_sha256(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


def _is_duplicate(session, email_row: Email | None, filename: str,
                  payload: bytes, ext: str) -> bool:
    """True SOLO si el mismo correo ya registró un archivo con el mismo
    nombre, extensión y contenido byte a byte (SHA-256)."""
    if email_row is None:
        return False
    name = os.path.basename(filename).strip().lower()
    candidates = session.execute(
        select(Document).where(
            Document.email_id == email_row.id,
            Document.ext == ext,
            func.lower(Document.original_name) == name,
        )
    ).scalars().all()
    if not candidates:
        return False
    new_hash = hashlib.sha256(payload).hexdigest()
    for cand in candidates:
        if cand.stored_path and _file_sha256(cand.stored_path) == new_hash:
            log.info("Duplicado omitido (mismo correo y contenido): %s", filename)
            return True
    return False


def _cuche_key_for_file(filename: str, payload: bytes) -> str:
    """Get CUFE key: filename prefix first, XML content fallback, PDF content hash fallback."""
    from shared.parsing.ubl import cuche_key_from_filename
    key = cuche_key_from_filename(filename)
    if key and len(key) > 5:
        return key
    if filename.lower().endswith(".xml"):
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(payload)
            from shared.parsing.ubl import cuche_key_from_xml
            return cuche_key_from_xml(root)
        except (ET.ParseError, ValueError):
            pass
    # PDF content hash as last resort for dedup within same account
    if filename.lower().endswith(".pdf"):
        return f"sha256:{hashlib.sha256(payload).hexdigest()[:40]}"
    return ""


def _semantic_duplicate(session, filename: str, payload: bytes, ext: str,
                        account: str) -> Document | None:
    """Find existing doc with same emisor+amount+date or same PDF content hash."""
    from shared.parsing.amounts import extract_amount
    from shared.parsing.dates import extract_issue_date
    if ext != ".pdf":
        return None
    content_hash = hashlib.sha256(payload).hexdigest()
    existing = session.execute(
        select(Document).where(Document.cuche_key == f"sha256:{content_hash}",
                               Document.ext == ".pdf")
    ).scalars().first()
    if existing:
        return existing
    try:
        import fitz
        with fitz.open(stream=payload, filetype="pdf") as doc:
            text = "".join(page.get_text() for page in doc[:2])
    except Exception:
        text = ""
    amount, _ = extract_amount(text)
    if amount is None:
        return None
    date = extract_issue_date(text)
    if date is None:
        return None
    return session.execute(
        select(Document).where(
            Document.amount == amount,
            Document.doc_date == date.strftime("%Y-%m-%d"),
            Document.ext == ".pdf",
            Document.status == "organized",
            Document.account == account,
        )
    ).scalars().first()


def _register(session, email_row: Email | None, filename: str, payload: bytes,
              source_type: str, link_url: str = "", account: str = "") -> Document | None:
    ext = os.path.splitext(filename)[1].lower() or ".pdf"
    if _is_duplicate(session, email_row, filename, payload, ext):
        return None

    # CUFE dedup: if same CUFE already exists, skip or mark as repr
    cuche = _cuche_key_for_file(filename, payload)
    if cuche:
        existing = session.execute(
            select(Document).where(Document.cuche_key == cuche)
        ).scalars().first()
        if existing:
            if existing.ext == ".xml" and ext == ".pdf":
                log.info("PDF omitido (XML hermano ya existe con CUFE %s): %s", cuche[:20], filename)
                return None
            elif existing.ext == ext:
                log.info("Duplicado CUFE omitido: %s", filename)
                return None

    # Semantic dedup for PDFs (emisor+amount+date)
    if ext == ".pdf" and not cuche:
        sem_dup = _semantic_duplicate(session, filename, payload, ext, account)
        if sem_dup:
            log.info("PDF duplicado semántico ignorado: %s -> ya existe id=%s", filename, sem_dup.id)
            return None

    doc = Document(
        email_id=email_row.id if email_row else None,
        original_name=os.path.basename(filename),
        stored_path=_save_bytes(payload, ext),
        source_type=source_type,
        link_url=link_url,
        ext=ext,
        status="pending",
        account=account or (email_row.account if email_row else ""),
        cuche_key=cuche[:64] if cuche else "",
    )
    session.add(doc)
    session.flush()
    session.refresh(doc)
    queue_pdf(doc.id)
    log.info("Registrado: %s (%s)", filename, source_type)
    return doc


def _register_manual_link(session, email_row: Email | None, url: str, account: str = "") -> None:
    session.add(Document(
        email_id=email_row.id if email_row else None,
        original_name=f"link_{urlparse(url).netloc}",
        stored_path="",
        source_type="link",
        link_url=url,
        ext="",
        status="link_manual",
        account=account or (email_row.account if email_row else ""),
    ))


def _extract_archive(session, email_row: Email | None, payload: bytes,
                     ext_hint: str, source_type: str, account: str = "") -> int:
    added = 0
    try:
        for name, data in extract_members(payload, ext_hint):
            if _register(session, email_row, name, data,
                         f"{source_type}+{ext_hint.lstrip('.')}",
                         account=account) is not None:
                added += 1
    except ArchivePasswordError:
        note = Document(
            email_id=email_row.id if email_row else None,
            original_name=f"comprimido_protegido{ext_hint}",
            stored_path="",
            source_type=source_type,
            ext=ext_hint,
            status="failed",
            needs_review=True,
            error=f"Archivo {ext_hint} protegido con contraseña: extráelo a mano y suelta los PDF en data/inbox",
            account=account or (email_row.account if email_row else ""),
        )
        session.add(note)
        log.warning("Comprimido protegido omitido (%s)", ext_hint)
    return added


def _try_download_link(url: str) -> tuple[bytes, str] | None:
    try:
        resp = requests.get(url, timeout=(5, 10), stream=True,
                            headers={"User-Agent": USER_AGENT}, allow_redirects=True)
        if resp.status_code != 200:
            return None
        chunks, total = [], 0
        for chunk in resp.iter_content(chunk_size=65536):
            chunks.append(chunk)
            total += len(chunk)
            if total > 60 * 1024 * 1024:
                break
        payload = b"".join(chunks)
        content_type = resp.headers.get("content-type", "").lower()

        # Páginas HTML (logins, home de sitios) no son facturas: van a link manual.
        if "text/html" in content_type or HTML_SNIFF_RE.search(payload[:300]):
            return None

        if payload[:5] == b"%PDF-":
            return payload, ".pdf"
        if payload[:4] == b"PK\x03\x04":
            return payload, ".zip"
        if payload[:6] == bytes([0x37, 0x7A, 0xBC, 0xAF, 0x27, 0x1C]):
            return payload, ".7z"
        if payload[:4] == b"Rar!":
            return payload, ".rar"
        stripped = payload.lstrip()
        if "pdf" in content_type:
            return payload, ".pdf"
        if "zip" in content_type:
            return payload, ".zip"
        if "xml" in content_type or (stripped[:1] == b"<"):
            return payload, ".xml"
        if "rar" in content_type:
            return payload, ".rar"
    except requests.RequestException as exc:
        log.info("Link no descargable (%s): %s", type(exc).__name__, url[:120])
    return None


def _links_from_html(html: str) -> list[str]:
    links: list[str] = []
    for match in HREF_RE.finditer(html or ""):
        url = match.group(1).strip()
        if not url.startswith(("http://", "https://")):
            continue
        path = urlparse(url).path.lower()
        ext = os.path.splitext(path)[1]
        if ext in (".pdf", ".xml") or is_archive_ext(ext) or LINK_HINT_RE.search(url):
            if url not in links:
                links.append(url)
    return links


def _process_message(session, msg, stats: dict, account: str = "") -> None:
    """Procesa un correo y registra sus archivos. Lanza excepción si falla."""
    mid_header = msg.headers.get("message-id")
    if mid_header and mid_header[0] and mid_header[0].strip():
        message_id = mid_header[0].strip()
    else:
        message_id = f"noid-{msg.date or ''}-{hash((msg.subject, msg.from_))}"
    sender_raw = msg.from_ or ""
    email_row = session.execute(
        select(Email).where(Email.message_id == message_id)
    ).scalar_one_or_none()
    if email_row is None:
        email_row = Email(message_id=message_id, account=account)
    elif not email_row.account and account:
        email_row.account = account

    email_row.sender_email = sender_raw
    email_row.sender_name = (msg.from_values.name if msg.from_values else "") or ""
    email_row.subject = msg.subject or ""
    email_row.date_received = msg.date
    session.add(email_row)
    session.flush()
    session.refresh(email_row)

    for att in msg.attachments:
        filename = os.path.basename(att.filename or f"adjunto_{uuid.uuid4().hex[:8]}")
        ext = os.path.splitext(filename)[1].lower()

        if is_archive_ext(ext):
            n = _extract_archive(session, email_row, att.payload, ext, "attachment", account=account)
            stats["zips"] += 1
            stats["archivos"] += n
        elif ext in WANTED_EXTS:
            if _register(session, email_row, filename, att.payload,
                         "attachment", account=account) is not None:
                stats["archivos"] += 1

    for url in _links_from_html(msg.html or ""):
        downloaded = _try_download_link(url)
        if downloaded is None:
            _register_manual_link(session, email_row, url, account=account)
            stats["links_manuales"] += 1
        else:
            payload, kind = downloaded
            name = os.path.basename(urlparse(url).path) or f"descarga{kind}"
            if not os.path.splitext(name)[1]:
                name += kind
            if is_archive_ext(kind):
                n = _extract_archive(session, email_row, payload, kind, "link", account=account)
                stats["archivos"] += n
                stats["links_descargados"] += 1
            else:
                if _register(session, email_row, name, payload,
                             "link", account=account) is not None:
                    stats["archivos"] += 1
                stats["links_descargados"] += 1


def run_sync(job_id: int, since: str, before: str) -> dict:
    session_factory = get_session_factory()
    session = session_factory()
    stats = {"emails": 0, "archivos": 0, "zips": 0, "links_descargados": 0,
             "links_manuales": 0, "emails_con_error": 0}
    try:
        settings = _get_settings(session)
        host = settings.get("imap_host") or "imap.gmail.com"
        user = settings.get("imap_user")
        password = settings.get("imap_password")
        if not user or not password:
            raise RuntimeError("Configura usuario y contraseña de aplicación primero")

        d_since = datetime.strptime(since, "%Y-%m-%d").date()
        criteria_args = {"date_gte": d_since}
        if before:
            d_before = datetime.strptime(before, "%Y-%m-%d").date()
            criteria_args["date_lt"] = d_before + timedelta(days=1)

        for d in (FACTURAS_DIR, INBOX_DIR, PROCESSING_DIR):
            os.makedirs(d, exist_ok=True)

        with MailBox(host, timeout=30).login(user, password) as mailbox:
            account = (user or "").strip()
            for msg in mailbox.fetch(AND(**criteria_args), mark_seen=False):
                try:
                    _process_message(session, msg, stats, account=account)
                    session.commit()
                    stats["emails"] += 1
                except Exception:  # noqa: BLE001
                    session.rollback()
                    stats["emails_con_error"] += 1
                    log.exception("Correo problemático omitido, se continúa")
                    continue

                job = session.get(Job, job_id)
                if job is not None:
                    job.result = json.dumps(stats, ensure_ascii=False)
                    session.commit()

        job = session.get(Job, job_id)
        if job is not None:
            job.status = "done"
            job.result = json.dumps(stats, ensure_ascii=False)
            job.error = ""
        log.info("Sync completado: %s", stats)
        return stats
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        fresh = session.get(Job, job_id)
        if fresh:
            fresh.status = "failed"
            fresh.error = f"{type(exc).__name__}: {exc}"
        log.exception("Sync falló")
        return {}
    finally:
        session.commit()
        session.close()


def start_sync_thread(job_id: int, since: str, before: str) -> threading.Thread:
    thread = threading.Thread(target=run_sync, args=(job_id, since, before), daemon=True)
    thread.start()
    return thread
