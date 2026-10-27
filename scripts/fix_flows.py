"""Corrige flujos gasto/ganancia con la regla de propiedad por nombre.

Pasos:
1. Si no existe el ajuste 'owner_name', lo deriva del correo IMAP
   (juanmiguelcedenosolano -> Juan Miguel Cedenosolano).
2. Rellena emisor_name/receptor_name de los XML organizados re-parseando
   el archivo (CFDI o UBL/DIAN).
3. Aplica la regla: receptor ~ dueno -> gasto; emisor ~ dueno -> ganancia.
4. Lista los documentos en 'ganancia' que quedan, para revision manual.

Uso:  python fix_flows.py          # simulacion
      python fix_flows.py --yes    # aplica cambios
"""
import os
import sys

from sqlalchemy import select

from shared.db import Document, Setting, get_session_factory, init_db
from shared.names import name_matches_owner
from shared.parsing.cfdi import parse_cfdi
from shared.parsing.ubl import parse_ubl


def seed_owner(session) -> str:
    row = session.get(Setting, "owner_name")
    if row and (row.value or "").strip():
        return row.value.strip()
    imap = session.get(Setting, "imap_user")
    local = ((imap.value or "").split("@")[0] if imap else "")
    words = [p for p in local.split(".") if p]
    split_camel = []
    for w in words:
        acc = ""
        for ch in w:
            if ch.isupper() and acc:
                split_camel.append(acc)
                acc = ch
            else:
                acc += ch
        if acc:
            split_camel.append(acc)
    derived = " ".join(p.capitalize() for p in split_camel)
    if not derived:
        return ""
    session.add(Setting(key="owner_name", value=derived))
    session.commit()
    print(f"owner_name creado a partir del correo: '{derived}'")
    return derived


def fill_party_names(session) -> int:
    docs = session.execute(
        select(Document).where(
            Document.ext == ".xml",
            Document.status == "organized",
            Document.receptor_name == "",
            Document.emisor_name == "",
            Document.stored_path != "",
        )
    ).scalars().all()
    filled = 0
    for doc in docs:
        try:
            with open(doc.stored_path, "rb") as fh:
                data = fh.read()
        except OSError:
            continue
        cfdi = parse_cfdi(data) or parse_ubl(data)
        if not cfdi:
            continue
        doc.emisor_name = (cfdi.get("emisor_nombre") or "")[:300]
        doc.receptor_name = (cfdi.get("receptor_nombre") or "")[:300]
        filled += 1
    return filled


def main(really: bool) -> None:
    init_db()
    session = get_session_factory()()
    owner = seed_owner(session)
    if not owner:
        print("Sin owner_name ni correo para derivarlo. Configura 'Tu nombre' primero.")
        return
    print(f"Regla activa con owner_name='{owner}'\n")

    filled = fill_party_names(session)
    print(f"XML con emisor/receptor recien extraidos: {filled}")

    session.expire_all()
    docs = session.execute(
        select(Document).where(Document.status == "organized",
                               Document.doc_kind != "no_factura")
    ).scalars().all()

    flips, kept_ganancia = [], []
    for d in docs:
        receptor, emisor = (d.receptor_name or "").strip(), (d.emisor_name or "").strip()
        new_flow, base = None, ""
        if receptor and name_matches_owner(receptor, owner):
            new_flow, base = "gasto", f"receptor={receptor[:30]}"
        elif emisor and name_matches_owner(emisor, owner):
            new_flow, base = "ganancia", f"emisor={emisor[:30]}"
        elif d.flow == "ganancia" and not emisor:
            tokens = [t for t in owner.lower().split() if len(t) >= 3]
            hits = sum(1 for t in tokens if t in (d.full_text or "").lower())
            if len(tokens) >= 2 and hits >= 2:
                new_flow, base = "gasto", "nombre del propietario en el texto del PDF"
        if new_flow and new_flow != d.flow:
            flips.append((d, d.flow, new_flow, base))
        if d.flow == "ganancia" and not new_flow:
            kept_ganancia.append(d)

    print(f"\n=== CAMBIOS DE FLUJO: {len(flips)} ===")
    for d, old, new, base in flips:
        print(f"  #{d.id:<4} {old:>8} -> {new:<8} {d.place_name_raw[:30]:<30} [{base}]")

    print(f"\n=== QUEDAN EN GANANCIA (revisar manual): {len(kept_ganancia)} ===")
    for d in kept_ganancia:
        print(f"  #{d.id:<4} {d.place_name_raw[:40]:<40} ${d.amount or 0} "
              f"rec:{(d.receptor_name or '-')[:30]}")

    if not really:
        print(f"\nSimulacion: {len(flips)} cambios pendientes. Usa --yes para aplicar.")
        return

    for d, _old, new, _base in flips:
        d.flow = new
        d.needs_review = False
    session.commit()
    print(f"\nHecho: {len(flips)} flujos corregidos.")


if __name__ == "__main__":
    main("--yes" in sys.argv)
