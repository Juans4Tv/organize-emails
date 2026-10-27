import os
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from shared.archives import ArchivePasswordError, extract_members, is_archive_ext
from shared.config import INBOX_DIR, LOCAL_SCAN_DIR, PROCESSING_DIR
from shared.db import Document, get_session_factory
from shared.queues import queue_pdf

from app.deps import current_account

router = APIRouter()


# ---------- inbox manual ----------


def current_account(session) -> str:
    row = session.get(Setting, "imap_user")
    return (row.value or "").strip() if row else ""


def _register_manual_file(session, name: str, data: bytes, account: str | None = None) -> int:
    ext = os.path.splitext(name)[1].lower() or ".pdf"
    stored = os.path.join(PROCESSING_DIR, f"{uuid.uuid4().hex[:16]}{ext}")
    with open(stored, "wb") as fh:
        fh.write(data)
    doc = Document(original_name=name, stored_path=stored,
                   source_type="manual", ext=ext, status="pending",
                   account=account if account is not None else current_account(session))
    session.add(doc)
    session.flush()
    session.refresh(doc)
    return doc.id


@router.post("/api/inbox/scan")
def inbox_scan() -> dict:
    session = get_session_factory()()
    added = 0
    archives = 0
    queued_ids: list[int] = []
    try:
        if not os.path.isdir(INBOX_DIR):
            return {"added": 0}
        for name in os.listdir(INBOX_DIR):
            path = os.path.join(INBOX_DIR, name)
            if not os.path.isfile(path):
                continue
            base, ext = os.path.splitext(name)
            ext = ext.lower()

            if is_archive_ext(ext):
                with open(path, "rb") as fh:
                    payload = fh.read()
                archives += 1
                os.remove(path)
                try:
                    members = extract_members(payload, ext)
                except ArchivePasswordError:
                    session.add(Document(
                        original_name=name, stored_path="", source_type="manual",
                        ext=ext, status="failed", needs_review=True,
                        error=f"Archivo {ext} protegido con contraseña",
                        account=current_account(session)))
                    continue
                for mname, data in members:
                    queued_ids.append(_register_manual_file(session, mname, data))
                    added += 1
            elif ext in (".pdf", ".xml"):
                with open(path, "rb") as fh:
                    payload = fh.read()
                queued_ids.append(_register_manual_file(session, name, payload))
                os.remove(path)
                added += 1
        session.commit()
        for doc_id in queued_ids:
            queue_pdf(doc_id)
    finally:
        session.close()
    return {"added": added, "zips": archives}


# ---------- carpeta local ----------


def _safe_local_path(name: str) -> str:
    """Evita escape de la carpeta local (path traversal)."""
    base = os.path.realpath(LOCAL_SCAN_DIR)
    candidate = os.path.realpath(os.path.join(base, os.path.basename(name)))
    if not candidate.startswith(base + os.sep) and candidate != base:
        raise HTTPException(status_code=400, detail="Ruta fuera de la carpeta local")
    return candidate


@router.get("/api/local-folder/list")
def local_folder_list() -> dict:
    """Lista los archivos (PDF/XML/ZIP) de la carpeta local sin procesarlos."""
    if not os.path.isdir(LOCAL_SCAN_DIR):
        return {"folder": LOCAL_SCAN_DIR, "items": []}
    session = get_session_factory()()
    try:
        known_names = set(session.execute(select(Document.original_name)).scalars().all())
        items = []
        for name in sorted(os.listdir(LOCAL_SCAN_DIR)):
            path = os.path.join(LOCAL_SCAN_DIR, name)
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in (".pdf", ".xml") and not is_archive_ext(ext):
                continue
            st = os.stat(path)
            zip_members = None
            if is_archive_ext(ext):
                try:
                    with open(path, "rb") as fh:
                        members = extract_members(fh.read(), ext)
                    zip_members = len(members)
                except ArchivePasswordError:
                    zip_members = -1
                except Exception:
                    zip_members = -2
            items.append({
                "name": name,
                "ext": ext,
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
                "zip_members": zip_members,
                "already": name in known_names,
            })
    finally:
        session.close()
    return {"folder": LOCAL_SCAN_DIR, "items": items}


@router.post("/api/local-folder/upload")
async def local_folder_upload(file: UploadFile = File(...)) -> dict:
    """Sube un archivo (drag&drop o selector) a la carpeta local sin procesarlo."""
    os.makedirs(LOCAL_SCAN_DIR, exist_ok=True)
    name = os.path.basename(file.filename or "archivo")
    ext = os.path.splitext(name)[1].lower()
    if ext not in (".pdf", ".xml") and not is_archive_ext(ext):
        raise HTTPException(status_code=400, detail=f"Extensión no soportada: {ext}")
    if not name or not name.replace(".", "").strip():
        raise HTTPException(status_code=400, detail="Nombre de archivo vacío")
    path = _safe_local_path(name)
    try:
        content = await file.read()
    finally:
        await file.close()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacío")
    with open(path, "wb") as fh:
        fh.write(content)
    return {"ok": True, "name": name}


@router.get("/api/local-folder/download/{name}")
def local_folder_download(name: str):
    """Descarga un archivo de la carpeta local."""
    path = _safe_local_path(name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(path, filename=name)


@router.get("/api/local-folder/open")
def local_folder_open() -> dict:
    """Devuelve la ruta de la carpeta local.

    ``HOST_LOCAL_SCAN_DIR`` es opcional: permite mostrar la ruta absoluta del
    equipo anfitrión (por ejemplo para abrirla desde el navegador). Dentro de
    Docker la ruta real siempre es ``LOCAL_SCAN_DIR``.
    """
    if not os.path.isdir(LOCAL_SCAN_DIR):
        os.makedirs(LOCAL_SCAN_DIR, exist_ok=True)
    return {
        "container_path": LOCAL_SCAN_DIR,
        "windows_path": os.environ.get("HOST_LOCAL_SCAN_DIR", "").strip(),
        "folder_exists": True,
    }


class LocalProcessIn(BaseModel):
    files: list[str] = []
    account: str = ""


@router.post("/api/local-folder/process")
def local_folder_process(payload: LocalProcessIn) -> dict:
    """Procesa archivos seleccionados de la carpeta local asignándolos a una
    cuenta elegida (por defecto la cuenta activa). No mezcla datos: cada
    lote va a la cuenta indicada."""
    if not payload.files:
        raise HTTPException(status_code=400, detail="No se seleccionó ningún archivo")
    if not os.path.isdir(LOCAL_SCAN_DIR):
        os.makedirs(LOCAL_SCAN_DIR, exist_ok=True)

    account = (payload.account or "").strip()
    session = get_session_factory()()
    added = 0
    archives = 0
    queued_ids: list[int] = []
    errors: list[str] = []
    try:
        for name in payload.files:
            path = _safe_local_path(name)
            if not os.path.isfile(path):
                errors.append(f"{name}: no encontrado")
                continue
            base, ext = os.path.splitext(name)
            ext = ext.lower()
            with open(path, "rb") as fh:
                data = fh.read()

            if is_archive_ext(ext):
                archives += 1
                try:
                    members = extract_members(data, ext)
                except ArchivePasswordError:
                    session.add(Document(
                        original_name=name, stored_path="", source_type="manual",
                        ext=ext, status="failed", needs_review=True,
                        error=f"Archivo {ext} protegido con contraseña",
                        account=account or current_account(session)))
                    errors.append(f"{name}: archivo protegido con contraseña")
                    continue
                for mname, mdata in members:
                    queued_ids.append(_register_manual_file(session, mname, mdata, account))
                    added += 1
            elif ext in (".pdf", ".xml"):
                queued_ids.append(_register_manual_file(session, name, data, account))
                added += 1
            else:
                errors.append(f"{name}: extensión no soportada")
                continue
            # mover el archivo a un subdirectorio procesados para no re-procesar
            proc_dir = os.path.join(LOCAL_SCAN_DIR, "_procesados")
            os.makedirs(proc_dir, exist_ok=True)
            os.replace(path, os.path.join(proc_dir, name))

        session.commit()
        for doc_id in queued_ids:
            queue_pdf(doc_id)
    finally:
        session.close()
    return {"added": added, "zips": archives, "errors": errors}
