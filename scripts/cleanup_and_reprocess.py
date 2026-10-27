#!/usr/bin/env python3
"""Limpia PDFs basura de prueba y re-procesa XMLs afectados con el parser nuevo.

Elimina documentos 'no_factura' que son basura de pruebas (CVs, manuales,
notas, fee schedules) con montos espurios, y re-analiza los XMLs con
emisor vacío o en revisión para que el parser enriquecido (CreditNote,
líneas, _party_name con <cbc:Name>) los corrija.
"""
import os
import sys

sys.path.insert(0, "/srv")
from sqlalchemy import func, select

from shared.config import PROCESSING_DIR
from shared.db import Document, get_session_factory, init_db
from shared.parsing.amounts import extract_amount
from shared.parsing.cfdi import parse_cfdi
from shared.parsing.ubl import parse_ubl

# Lugares que son claramente basura de pruebas (no facturas reales)
BASURA_PLACES = {
    "Fee Schedule", "Camilo Meneses", "Estudiante", "Acuerdo 030",
    "Entrega Inicial", "Experiencia Laboral", "Manual", "Novena De Navidad",
    "Salud Integral", "Notas Primer Corte", "Notas Segundo Corte",
}


def main():
    init_db()
    Sess = get_session_factory()
    with Sess() as s:
        # ---------------------------------------------------------------
        # Paso 1: eliminar basura no_factura
        # ---------------------------------------------------------------
        basura = s.execute(
            select(Document).where(
                Document.doc_kind == "no_factura",
                Document.place_name_raw.in_(sorted(BASURA_PLACES)),
            )
        ).scalars().all()
        print(f"[1] Basura a eliminar: {len(basura)} documentos")
        for d in basura:
            path = d.stored_path
            s.delete(d)
            if path and os.path.exists(path):
                os.remove(path)
            print(f"  - eliminado {d.id} {d.original_name}")

        # ---------------------------------------------------------------
        # Paso 1b: eliminar duplicados XML por contenido CUFE + misma fecha
        # (manuales subidos dos veces con nombres hash distintos)
        # ---------------------------------------------------------------
        xmls_org = s.execute(
            select(Document).where(
                Document.ext == ".xml",
                Document.doc_kind.in_(["factura", "documento", "nota_credito", "nota_debito"]),
                Document.stored_path != "",
            )
        ).scalars().all()
        grupos: dict[tuple, list] = {}
        for d in xmls_org:
            if not os.path.exists(d.stored_path):
                continue
            with open(d.stored_path, "rb") as fh:
                raw = fh.read()
            cfdi = parse_cfdi(raw) or parse_ubl(raw)
            if not cfdi or not cfdi.get("cuche_key"):
                continue
            grupos.setdefault((cfdi["cuche_key"], d.doc_date.date() if d.doc_date else None), []).append(d)
        for (ck, fecha), docs in grupos.items():
            if len(docs) < 2:
                continue
            keep = max(docs, key=lambda x: (x.verified, x.amount is not None, -x.id))
            for dup in docs:
                if dup.id == keep.id:
                    continue
                path = dup.stored_path
                print(f"  [1b] duplicado XML por CUFE {ck}: {dup.id} {dup.original_name}")
                s.delete(dup)
                if path and os.path.exists(path):
                    os.remove(path)

        # ---------------------------------------------------------------
        # Paso 2: re-procesar XMLs con emisor vacío o en revisión
        # ---------------------------------------------------------------
        a_reprocesar = s.execute(
            select(Document).where(
                Document.ext == ".xml",
                Document.doc_kind.in_(["factura", "documento", "nota_credito", "nota_debito"]),
                (Document.emisor_name == "") | (Document.status == "needs_review"),
            )
        ).scalars().all()
        print(f"\n[2] XMLs a re-procesar: {len(a_reprocesar)}")
        for d in a_reprocesar:
            if not d.stored_path or not os.path.exists(d.stored_path):
                continue
            with open(d.stored_path, "rb") as fh:
                data = fh.read()
            cfdi = parse_cfdi(data) or parse_ubl(data)
            if not cfdi:
                print(f"  - {d.id} {d.original_name}: no parseable, se deja")
                continue

            if cfdi.get("emisor_nombre"):
                d.emisor_name = cfdi["emisor_nombre"][:300]
            if cfdi.get("receptor_nombre"):
                d.receptor_name = cfdi["receptor_nombre"][:300]
            if cfdi.get("total") is not None:
                d.amount = cfdi["total"]
            if cfdi.get("fecha"):
                d.doc_date = cfdi["fecha"]
            d.doc_kind = {
                "I": "factura", "E": "nota_credito", "D": "nota_debito",
                "N": "nomina", "P": "pago",
            }.get((cfdi.get("tipo") or "").upper(), "documento")
            d.status = "organized"
            d.needs_review = False
            d.error = ""
            d.verified = bool(d.verified or d.amount is not None)
            print(f"  - re-procesado {d.id} {d.original_name} "
                  f"emisor={cfdi.get('emisor_nombre','')[:30]!r} "
                  f"total={cfdi.get('total')} tipo={cfdi.get('tipo')}")

        s.commit()
        print("\nHecho.")

    # Limpiar archivos huérfanos en processing
    if os.path.isdir(PROCESSING_DIR):
        for name in os.listdir(PROCESSING_DIR):
            path = os.path.join(PROCESSING_DIR, name)
            if os.path.isfile(path) and os.path.getsize(path) == 0:
                os.remove(path)
                print(f"limpiado archivo vacío: {name}")


if __name__ == "__main__":
    main()
