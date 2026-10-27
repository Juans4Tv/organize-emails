#!/usr/bin/env python3
"""Migrate existing documents to the base currency (COP or USD).

Usage: docker compose exec -w /srv -e PYTHONPATH=/srv organizer-service python /tmp/unify_currency.py
"""
import argparse, sys
sys.path.insert(0, "/srv")
from shared.db import Document, Setting, get_session_factory, init_db

def get_settings(session):
    rows = session.execute(select(Setting.key, Setting.value).where(Setting.key.in_(["base_currency", "fx_usd_cop"]))).all()
    return {r.key: r.value for r in rows}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    init_db()
    Sess = get_session_factory()
    with Sess() as s:
        cfg = get_settings(s)
        base = (cfg.get("base_currency") or "COP").upper()
        fx_raw = cfg.get("fx_usd_cop") or "4000"
        try:
            fx = float(fx_raw)
        except ValueError:
            fx = 4000.0

        docs = s.execute(select(Document).where(Document.amount.isnot(None))).scalars().all()
        flipped = 0
        for doc in docs:
            cur = (doc.currency or "").upper() or base
            if cur == base:
                continue
            if not args.yes:
                print(f"  doc {doc.id}: {doc.amount} {cur} -> ", end="")
            if cur == "USD" and base == "COP":
                doc.amount = round(doc.amount * fx, 2)
            elif cur == "COP" and base == "USD":
                doc.amount = round(doc.amount / fx, 2)
            else:
                continue
            doc.currency = base
            flipped += 1
            if not args.yes:
                print(f"{doc.amount} {base}")
        if args.yes:
            s.commit()
            print(f"OK: {flipped} documentos convertidos a {base}")
        else:
            print(f"\nSimulación: {flipped} documentos se convertirían a {base}")
            print("Ejecuta con --yes para aplicar")

if __name__ == "__main__":
    from sqlalchemy import select
    main()
