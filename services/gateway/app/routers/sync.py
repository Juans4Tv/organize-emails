from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from shared.db import Job, get_session_factory

from app.deps import EMAIL_SERVICE_URL

router = APIRouter()


# ---------- sincronización ----------


class SyncIn(BaseModel):
    since: str
    before: str | None = None


@router.post("/api/sync")
async def sync(req: SyncIn) -> dict:
    if not req.since:
        raise HTTPException(status_code=400, detail="Indica la fecha inicial (desde)")
    try:
        datetime.strptime(req.since, "%Y-%m-%d")
        if req.before:
            datetime.strptime(req.before, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido (se espera YYYY-MM-DD)")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{EMAIL_SERVICE_URL}/sync",
            json={"since": req.since, "before": req.before},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=resp.text)
    return resp.json()


@router.post("/api/test-connection")
async def test_connection() -> dict:
    async with httpx.AsyncClient(timeout=45) as client:
        resp = await client.post(f"{EMAIL_SERVICE_URL}/test-connection")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=resp.text)
    return resp.json()


@router.get("/api/jobs/latest")
def latest_job(kind: str = "email_sync") -> dict:
    session = get_session_factory()()
    job = session.execute(
        select(Job).where(Job.kind == kind).order_by(Job.id.desc()).limit(1)
    ).scalar_one_or_none()
    session.close()
    if not job:
        return {"none": True}
    return {
        "id": job.id, "kind": job.kind, "status": job.status,
        "params": job.params, "result": job.result, "error": job.error,
    }


@router.get("/api/jobs/{job_id}")
def job_status(job_id: int) -> dict:
    session = get_session_factory()()
    job = session.get(Job, job_id)
    session.close()
    if not job:
        raise HTTPException(status_code=404, detail="job no encontrado")
    return {
        "id": job.id, "kind": job.kind, "status": job.status,
        "params": job.params, "result": job.result, "error": job.error,
    }
