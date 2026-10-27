from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import select

from shared.crypto import decrypt_secret
from shared.db import Job, Setting, get_session_factory, init_db
from app.fetcher import start_sync_thread

app = FastAPI(title="email-service")


@app.on_event("startup")
def startup() -> None:
    init_db()


class SyncRequest(BaseModel):
    since: str
    before: str | None = None


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/test-connection")
def test_connection() -> dict:
    from imap_tools import MailBox

    session = get_session_factory()()
    rows = {r.key: r.value for r in session.execute(select(Setting)).scalars().all()}
    session.close()

    host = rows.get("imap_host") or "imap.gmail.com"
    user = rows.get("imap_user")
    password = decrypt_secret(rows.get("imap_password"))
    if not user or not password:
        return {"ok": False,
                "error": "Falta el correo o la contraseña de aplicación. Guárdalos primero."}

    try:
        with MailBox(host, timeout=20).login(user, password) as mailbox:
            mailbox.folder.list()
        return {"ok": True, "host": host, "user": user}
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        upper = msg.upper()
        if "AUTHENTICATIONFAILED" in upper or "INVALID" in upper and "CREDENTIALS" in upper:
            msg = ("Google rechazó el login. Verifica que uses una CONTRASEÑA DE APLICACIÓN "
                   "(16 letras, generada en myaccount.google.com/contraseñas de aplicación) "
                   "y no tu contraseña normal.")
        elif "timed out" in msg.lower():
            msg = f"Sin respuesta de {host} (timeout). Revisa tu conexión."
        elif "name or service not known" in msg.lower() or "getaddrinfo" in msg.lower():
            msg = f"No se pudo resolver el servidor '{host}'."
        return {"ok": False, "error": msg[:500]}


@app.post("/sync")
def sync(req: SyncRequest) -> dict:
    datetime.strptime(req.since, "%Y-%m-%d")
    if req.before:
        datetime.strptime(req.before, "%Y-%m-%d")

    session = get_session_factory()()
    job = Job(kind="email_sync", status="running",
              params=f'{{"since": "{req.since}", "before": "{req.before or ""}"}}')
    session.add(job)
    session.commit()
    session.refresh(job)
    job_id = job.id
    session.close()

    start_sync_thread(job_id, req.since, req.before or "")
    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
def job_status(job_id: int) -> dict:
    session = get_session_factory()()
    job = session.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
    if not job:
        return {"error": "not_found"}
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "params": job.params,
        "result": job.result,
        "error": job.error,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
