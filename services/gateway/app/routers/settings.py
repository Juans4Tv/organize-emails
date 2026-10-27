from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from shared.crypto import encrypt_secret
from shared.db import Setting, get_session_factory

router = APIRouter()


# ---------- configuración ----------


@router.get("/api/settings")
def get_settings() -> dict:
    session = get_session_factory()()
    rows = {r.key: r.value for r in session.execute(select(Setting)).scalars().all()}
    session.close()
    return {
        "imap_host": rows.get("imap_host", "imap.gmail.com"),
        "imap_user": rows.get("imap_user", ""),
        "own_rfc": rows.get("own_rfc", ""),
        "owner_name": rows.get("owner_name", ""),
        "base_currency": rows.get("base_currency", "COP"),
        "fx_usd_cop": rows.get("fx_usd_cop", "4000"),
        "has_password": bool(rows.get("imap_password")),
    }


class SettingsIn(BaseModel):
    imap_host: str | None = None
    imap_user: str | None = None
    imap_password: str | None = None
    own_rfc: str | None = None
    owner_name: str | None = None
    base_currency: str | None = None
    fx_usd_cop: str | None = None


@router.put("/api/settings")
def put_settings(payload: SettingsIn) -> dict:
    session = get_session_factory()()
    updates: dict[str, str] = {}
    if payload.imap_host is not None and payload.imap_host.strip():
        updates["imap_host"] = payload.imap_host.strip()
    if payload.imap_user is not None:
        updates["imap_user"] = payload.imap_user.strip()
    if payload.own_rfc is not None:
        updates["own_rfc"] = payload.own_rfc.strip().upper()
    if payload.owner_name is not None:
        updates["owner_name"] = " ".join(payload.owner_name.split())
    if payload.base_currency is not None:
        v = payload.base_currency.strip().upper()[:3]
        if v in ("", "COP", "USD"):
            updates["base_currency"] = v or "COP"
    if payload.fx_usd_cop is not None:
        raw = payload.fx_usd_cop.strip().replace(",", ".")
        try:
            val = float(raw) if raw else 0.0
            updates["fx_usd_cop"] = str(max(0.0, val))
        except ValueError:
            pass
    if payload.imap_password:  # solo se actualiza si viene algo (no vacío)
        updates["imap_password"] = encrypt_secret(payload.imap_password)

    for key, value in updates.items():
        row = session.get(Setting, key)
        if row is None:
            session.add(Setting(key=key, value=value))
        else:
            row.value = value
    session.commit()
    session.close()
    return {"updated": sorted(updates)}
