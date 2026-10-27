from fastapi import APIRouter
from sqlalchemy import Integer, cast, func, select

from shared.db import Document, Place, get_session_factory

from app.deps import current_account

router = APIRouter()


# ---------- lugares ----------


@router.get("/api/places")
def list_places() -> list[dict]:
    session = get_session_factory()()
    rows = session.execute(
        select(
            Place.id,
            Place.name,
            Place.source,
            func.count(Document.id).label("total"),
            func.sum(func.coalesce(Document.amount, 0)).label("monto"),
        )
        .outerjoin(Document, Document.place_id == Place.id)
        .where(Document.doc_kind.notin_(["no_factura", "repr"]))
        .group_by(Place.id)
        .order_by(Place.name)
    ).all()
    session.close()
    return [
        {"id": r.id, "name": r.name, "source": r.source,
         "documents": r.total, "monto_total": round(r.monto or 0, 2)}
        for r in rows
    ]


# ---------- cuentas ----------


@router.get("/api/accounts")
def list_accounts() -> list[dict]:
    session = get_session_factory()()
    rows = session.execute(
        select(
            Document.account,
            func.count(Document.id),
            func.sum(cast(Document.needs_review, Integer)),
        )
        .group_by(Document.account)
        .order_by(Document.account)
    ).all()
    current = current_account(session)
    session.close()
    return [
        {"account": r[0] or "(sin cuenta)", "count": r[1],
         "needs_review": int(r[2] or 0), "current": (r[0] or "") == current}
        for r in rows
    ]
