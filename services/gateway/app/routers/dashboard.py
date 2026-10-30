from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import Response
from sqlalchemy import Integer, case, cast, func, select

from shared.db import Document, Email, Place, get_session_factory

from app.deps import current_account
from app.excel import documents_workbook

router = APIRouter()


# ---------- dashboard ----------


@router.get("/api/dashboard")
def dashboard(account: str | None = None) -> dict:
    session = get_session_factory()()
    scope = [Document.account == account] if account else []

    totals_q = session.execute(
        select(
            Document.flow,
            Document.doc_kind,
            func.count(Document.id),
            func.coalesce(func.sum(Document.amount), 0),
        ).where(Document.status.in_(("organized", "needs_review")),
                Document.doc_kind.notin_(["no_factura", "repr"]),
                *scope)
        .group_by(Document.flow, Document.doc_kind)
    ).all()
    totals: dict[str, dict] = {}
    for flow, kind, count, amount in totals_q:
        sign = -1.0 if kind == "nota_credito" else 1.0
        entry = totals.setdefault(flow, {"count": 0, "amount": 0.0})
        entry["count"] += count
        entry["amount"] = round(entry["amount"] + sign * (amount or 0), 2)

    by_place_q = session.execute(
        select(
            Place.id,
            Place.name,
            Document.flow,
            Document.doc_kind,
            func.count(Document.id),
            func.coalesce(func.sum(Document.amount), 0),
            func.sum(cast(Document.verified, Integer)).label("verified"),
            func.sum(cast(Document.needs_review, Integer)).label("review"),
        )
        .join(Document, Document.place_id == Place.id)
        .where(Document.status != "link_manual", Document.doc_kind.notin_(["no_factura", "repr"]),
               *scope)
        .group_by(Place.id, Place.name, Document.flow, Document.doc_kind)
        .order_by(Place.name)
    ).all()

    by_place: dict[int, dict] = {}
    for place_id, name, flow, kind, count, amount, verified_count, review_count in by_place_q:
        entry = by_place.setdefault(place_id, {
            "id": place_id, "place": name, "gasto": 0.0, "ganancia": 0.0,
            "count": 0, "verified": 0, "needs_review": 0,
        })
        sign = -1.0 if kind == "nota_credito" else 1.0
        key = "gasto" if flow == "gasto" else ("ganancia" if flow == "ganancia" else None)
        if key:
            entry[key] = round(entry[key] + sign * (amount or 0), 2)
        entry["count"] += count
        entry["verified"] += int(verified_count or 0)
        entry["needs_review"] += int(review_count or 0)

    month_expr = func.to_char(Document.doc_date, "YYYY-MM").label("mes")
    by_month_q = session.execute(
        select(month_expr, Document.flow, Document.doc_kind, func.count(Document.id),
               func.coalesce(func.sum(Document.amount), 0))
        .where(Document.doc_date.is_not(None), Document.status != "link_manual",
               Document.doc_kind.notin_(["no_factura", "repr"]), *scope)
        .group_by(month_expr, Document.flow, Document.doc_kind)
        .order_by(month_expr)
    ).all()

    by_month: dict[str, dict] = {}
    for mes, flow, kind, count, amount in by_month_q:
        entry = by_month.setdefault(mes, {"month": mes, "gasto": 0.0, "ganancia": 0.0})
        sign = -1.0 if kind == "nota_credito" else 1.0
        key = "gasto" if flow == "gasto" else ("ganancia" if flow == "ganancia" else None)
        if key:
            entry[key] = round(entry[key] + sign * (amount or 0), 2)

    pending_review = session.execute(
        select(func.count(Document.id)).where(Document.needs_review.is_(True), *scope)
    ).scalar_one()
    link_manual = session.execute(
        select(func.count(Document.id)).where(Document.status == "link_manual", *scope)
    ).scalar_one()
    verified_total = session.execute(
        select(func.count(Document.id)).where(
            Document.verified.is_(True), Document.status != "link_manual", *scope
        )
    ).scalar_one()
    docs_total = session.execute(
        select(func.count(Document.id)).where(Document.status != "link_manual", *scope)
    ).scalar_one()

    by_account_q = session.execute(
        select(
            Document.account,
            func.count(Document.id),
            func.coalesce(func.sum(case(
                (Document.doc_kind.notin_(["no_factura", "repr", "nota_credito"]), Document.amount),
                (Document.doc_kind == "nota_credito", func.coalesce(Document.amount, 0.0) * -1.0),
                else_=0.0,
            )), 0),
            func.sum(cast(Document.needs_review, Integer)),
        )
        .where(Document.status != "link_manual")
        .group_by(Document.account)
        .order_by(Document.account)
    ).all()
    current = current_account(session)

    session.close()
    return {
        "totals": totals,
        "by_place": list(by_place.values()),
        "by_month": list(by_month.values()),
        "needs_review_count": pending_review,
        "links_manual_count": link_manual,
        "verified_count": int(verified_total),
        "documents_count": int(docs_total),
        "by_account": [
            {"account": r[0] or "(sin cuenta)", "count": r[1], "monto": round(r[2] or 0, 2),
             "needs_review": int(r[3] or 0), "current": (r[0] or "") == current}
            for r in by_account_q
        ],
    }


# ---------- exportación ----------


@router.get("/api/export.xlsx")
def export_xlsx(account: str | None = None) -> Response:
    session = get_session_factory()()
    query = select(Document).order_by(Document.updated_at.desc())
    if account:
        query = query.where(Document.account == account)
    docs = session.execute(query).scalars().all()
    rows = []
    for d in docs:
        place = session.get(Place, d.place_id) if d.place_id else None
        email = session.get(Email, d.email_id) if d.email_id else None
        rows.append((d, place, email))
    session.close()

    content = documents_workbook(rows)
    filename = f"organizador_{datetime.now():%Y%m%d_%H%M}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
