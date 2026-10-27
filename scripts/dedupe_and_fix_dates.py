#!/usr/bin/env python3
"""Backfill: populate cuche_key, fix PDF dates from XML siblings, dedup.

Run inside organizer service container:
  docker cp scripts/dedupe_and_fix_dates.py openorganizador-organizer-service-1:/tmp/
  docker exec -w /srv -e PYTHONPATH=/srv openorganizador-organizer-service-1 python /tmp/dedupe_and_fix_dates.py --yes
"""
import argparse
import hashlib
import os
import sys

sys.path.insert(0, "/srv")
from sqlalchemy import func, select
from shared.db import Document, Setting, get_session_factory, init_db
from shared.parsing.ubl import cuche_key_from_filename, cuche_key_from_xml


def sha256(path):
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


def get_settings(session):
    rows = session.execute(select(Setting)).scalars().all()
    return {r.key: r.value for r in rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    init_db()
    Sess = get_session_factory()
    with Sess() as s:
        settings = get_settings(s)
        base_cur = (settings.get("base_currency") or "COP").upper()
        print(f"=== Moneda base: {base_cur} ===\n")

        # ---------------------------------------------------------------
        # Step 1: Populate cuche_key for all XML documents
        # ---------------------------------------------------------------
        xmls = s.execute(
            select(Document).where(Document.ext == ".xml", Document.cuche_key == "")
        ).scalars().all()
        populated = 0
        for doc in xmls:
            key = cuche_key_from_filename(doc.original_name)
            if len(key) > 5:
                doc.cuche_key = key[:64]
                populated += 1
                continue
            if doc.stored_path and os.path.exists(doc.stored_path):
                try:
                    import xml.etree.ElementTree as ET
                    tree = ET.parse(doc.stored_path)
                    key = cuche_key_from_xml(tree.getroot())
                    if key:
                        doc.cuche_key = key[:64]
                        populated += 1
                except Exception:
                    pass
        print(f"[1] CUFE popular en {populated} XMLs (de {len(xmls)})")

        # ---------------------------------------------------------------
        # Step 2: Dedup XML+XML by cuche_key
        # ---------------------------------------------------------------
        dupes = s.execute(
            select(Document.cuche_key, func.count(Document.id))
            .where(Document.cuche_key != "", Document.ext == ".xml",
                   Document.status == "organized")
            .group_by(Document.cuche_key)
            .having(func.count(Document.id) > 1)
        ).all()
        removed = 0
        for ckey, cnt in dupes:
            docs = s.execute(
                select(Document).where(
                    Document.cuche_key == ckey,
                    Document.ext == ".xml",
                    Document.status == "organized",
                ).order_by(Document.verified.desc(), Document.doc_date.desc(), Document.id)
            ).scalars().all()
            for dup in docs[1:]:
                print(f"  Duplicado XML (CUFE {ckey[:20]}): id={dup.id} {dup.original_name}")
                try:
                    removal_path = dup.stored_path
                    s.delete(dup)
                    removed += 1
                    if removal_path and os.path.exists(removal_path):
                        os.remove(removal_path)
                except Exception as e:
                    print(f"    Error: {e}")
        print(f"[2] Eliminados {removed} XML duplicados por CUFE")

        # ---------------------------------------------------------------
        # Step 2b: Dedup XML+XML by CONTENT CUFE + same doc_date
        # (manual uploads use hash filenames, so filename-derived keys differ)
        # Only dedup when content-CUFE AND doc_date BOTH match, to
        # avoid false positives where shared resolution IDs collide across
        # distinct invoices (e.g. Disney resolution numbers).
        # ---------------------------------------------------------------
        xmls_all = s.execute(
            select(Document).where(Document.ext == ".xml",
                                    Document.doc_kind == "factura",
                                    Document.status == "organized",
                                    Document.doc_date.isnot(None))
        ).scalars().all()
        groups: dict[tuple, list] = {}
        for d in xmls_all:
            try:
                import xml.etree.ElementTree as ET
                root = ET.parse(d.stored_path).getroot()
                ck = cuche_key_from_xml(root)
            except Exception:
                ck = ""
            if ck:
                groups.setdefault((ck, d.doc_date.date()), []).append(d)
        removed2 = 0
        for (ck, dt), docs in groups.items():
            if len(docs) < 2:
                continue
            docs_sorted = sorted(docs, key=lambda x: (x.verified, x.id))
            for dup in docs_sorted[1:]:
                print(f"  Duplicado XML (contenido CUFE {ck} + fecha {dt}): id={dup.id} {dup.original_name}")
                try:
                    removal_path = dup.stored_path
                    s.delete(dup)
                    removed2 += 1
                    if removal_path and os.path.exists(removal_path):
                        os.remove(removal_path)
                except Exception as e:
                    print(f"    Error: {e}")
        print(f"[2b] Eliminados {removed2} XML duplicados por contenido+fecha")

        # ---------------------------------------------------------------
        # Step 3: Mark PDF as repr if XML sibling exists
        # ---------------------------------------------------------------
        pdfs_with_sibling = s.execute(
            select(Document).where(Document.ext == ".pdf",
                                   Document.doc_kind != "repr",
                                   Document.status == "organized")
        ).scalars().all()
        marked = 0
        for pdf in pdfs_with_sibling:
            stem = os.path.splitext(pdf.original_name)[0]
            if not stem or len(stem) <= 5:
                continue
            sibling = s.execute(
                select(Document).where(
                    Document.ext == ".xml",
                    Document.id != pdf.id,
                    func.lower(func.substr(Document.original_name, 1, len(stem))) == stem.lower(),
                )
            ).scalars().first()
            if sibling:
                pdf.doc_kind = "repr"
                pdf.status = "organized"
                marked += 1
                print(f"  PDF repr: {pdf.original_name} <-> XML {sibling.original_name}")
        print(f"[3] Marcados {marked} PDFs como repr (XML hermano existe)")

        # ---------------------------------------------------------------
        # Step 4: Fix PDF dates from XML siblings
        # ---------------------------------------------------------------
        reprs = s.execute(
            select(Document).where(Document.doc_kind == "repr",
                                   Document.doc_date.isnot(None))
        ).scalars().all()
        fixed_dates = 0
        for pdf in reprs:
            stem = os.path.splitext(pdf.original_name)[0]
            if not stem or len(stem) <= 5:
                continue
            sibling = s.execute(
                select(Document).where(
                    Document.ext == ".xml",
                    Document.id != pdf.id,
                    Document.doc_date.isnot(None),
                    func.lower(func.substr(Document.original_name, 1, len(stem))) == stem.lower(),
                )
            ).scalars().first()
            if sibling and sibling.doc_date and pdf.doc_date != sibling.doc_date:
                old = pdf.doc_date.strftime("%Y-%m-%d") if pdf.doc_date else "?"
                pdf.doc_date = sibling.doc_date
                fixed_dates += 1
                print(f"  Fecha corregida: {pdf.original_name} {old} -> {sibling.doc_date.strftime('%Y-%m-%d')}")
        print(f"[4] Corregidas {fixed_dates} fechas de PDF desde XML hermano")

        # ---------------------------------------------------------------
        # Step 5: Dedup semántico para PDFs restantes (emisor+amount+date)
        # ---------------------------------------------------------------
        remaining_pdfs = s.execute(
            select(Document).where(Document.ext == ".pdf",
                                   Document.doc_kind != "repr",
                                   Document.doc_kind != "no_factura",
                                   Document.status == "organized",
                                   Document.amount.isnot(None))
        ).scalars().all()
        sem_dupes = 0
        for pdf in remaining_pdfs:
            same = s.execute(
                select(Document).where(
                    Document.ext == ".pdf",
                    Document.id != pdf.id,
                    Document.doc_kind.notin_(["repr", "no_factura"]),
                    Document.status == "organized",
                    Document.amount == pdf.amount,
                    Document.doc_date == pdf.doc_date,
                )
            ).scalars().all()
            for dup in same:
                if dup.id < pdf.id:
                    continue
                pdf_hash = sha256(pdf.stored_path)
                dup_hash = sha256(dup.stored_path)
                if pdf_hash == dup_hash:
                    print(f"  Duplicado semántico (hash igual): {pdf.original_name}")
                else:
                    print(f"  Duplicado semántico (hash difiere): {pdf.original_name} vs {dup.original_name}")
                    print(f"    Ambos montos: {pdf.amount}, fechas: {pdf.doc_date.date() if pdf.doc_date else 'N/A'}")
                if args.yes:
                    s.delete(dup)
                    sem_dupes += 1
                    if dup.stored_path and os.path.exists(dup.stored_path):
                        os.remove(dup.stored_path)
        print(f"[5] Eliminados {sem_dupes} PDF duplicados semánticos")

        # ---------------------------------------------------------------
        # Step 6: Match manual PDFs to XML siblings by amount + emisor
        # (manual uploads use hash filenames, not fv/ad prefixes)
        # ---------------------------------------------------------------
        unpaired_pdfs = s.execute(
            select(Document).where(
                Document.ext == ".pdf",
                Document.doc_kind == "documento",
                Document.status == "organized",
                Document.amount.isnot(None),
            )
        ).scalars().all()
        paired = 0
        fixed_dates2 = 0
        for pdf in unpaired_pdfs:
            # si el PDF ya tiene un hermano por stem, [3] lo marcó; omitir
            stem = os.path.splitext(pdf.original_name)[0]
            if stem and len(stem) > 5:
                already = s.execute(
                    select(Document).where(
                        Document.ext == ".xml",
                        Document.id != pdf.id,
                        func.lower(func.substr(Document.original_name, 1, len(stem))) == stem.lower(),
                    )
                ).scalars().first()
                if already:
                    continue
            # solo emparejar por monto si la combinación monto+emisor es única
            # (evita falsos positivos cuando varias facturas tienen el mismo monto)
            sibs = s.execute(
                select(Document).where(
                    Document.ext == ".xml",
                    Document.doc_kind == "factura",
                    Document.amount == pdf.amount,
                    Document.id != pdf.id,
                    Document.emisor_name != "",
                ).order_by(Document.verified.desc(), Document.id)
            ).scalars().all()
            if len(sibs) != 1:
                continue
            xml_sib = sibs[0]
            pdf.doc_kind = "repr"
            if pdf.doc_date != xml_sib.doc_date and xml_sib.doc_date:
                old = pdf.doc_date.strftime("%Y-%m-%d") if pdf.doc_date else "?"
                pdf.doc_date = xml_sib.doc_date
                fixed_dates2 += 1
                print(f"  PDF->XML por monto único: {pdf.original_name} fecha {old} -> "
                      f"{xml_sib.doc_date.strftime('%Y-%m-%d')}")
            else:
                print(f"  PDF->XML por monto único: {pdf.original_name} <-> XML {xml_sib.original_name}")
            paired += 1
        print(f"[6] Emparejados {paired} PDFs manuales a XML por monto único, "
              f"{fixed_dates2} fechas corregidas")

        if args.yes:
            print(f"\n=== APLICANDO CAMBIOS ===")
            s.commit()
            print("Cambios aplicados correctamente.")
        else:
            s.rollback()
            print(f"\n=== SIMULACIÓN (usa --yes para aplicar) ===")

    print(f"\nDONE.")


if __name__ == "__main__":
    main()
