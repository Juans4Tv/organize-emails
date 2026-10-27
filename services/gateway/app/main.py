import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.config import FACTURAS_DIR, INBOX_DIR, PROCESSING_DIR
from shared.crypto import encrypt_secret, is_encrypted
from shared.db import Setting, get_session_factory, init_db

from app.routers import dashboard, documents, local_folder, places, settings, sync

log = logging.getLogger("gateway")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="OpenOrganizador Gateway")

_origins = os.environ.get(
    "CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


def _encrypt_legacy_password() -> None:
    """Cifra una contraseña IMAP guardada en texto plano por versiones anteriores."""
    session = get_session_factory()()
    try:
        row = session.get(Setting, "imap_password")
        if row and row.value and not is_encrypted(row.value):
            row.value = encrypt_secret(row.value)
            session.commit()
            log.info("Contraseña IMAP migrada a formato cifrado")
    finally:
        session.close()


@app.on_event("startup")
def startup() -> None:
    init_db()
    for d in (FACTURAS_DIR, INBOX_DIR, PROCESSING_DIR):
        os.makedirs(d, exist_ok=True)
    _encrypt_legacy_password()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


for module in (settings, sync, local_folder, places, documents, dashboard):
    app.include_router(module.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
