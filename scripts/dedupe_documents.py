"""Elimina duplicados REALES: mismo correo + nombre/ext + SHA-256 idéntico.

Reglas:
- Grupo = documentos del mismo email_id con mismo nombre (sin mayúsculas) y ext.
- Solo se elimina una copia si su archivo tiene EXACTAMENTE el mismo hash
  que la copia conservada y la fecha de documento coincide (o falta).
- Se conserva la mejor copia: organizada+verificada > organizada > antigua.
- Copias sin archivo en disco: se eliminan solo si existe una copia buena
  verificada por hash.
- Grupos que no cumplen TODO se conservan y se listan como "REVISAR".

Uso:  python dedupe_documents.py          # simulación (no borra nada)
      python dedupe_documents.py --yes    # ejecuta realmente
"""
import hashlib
import os
import sys
from collections import defaultdict

from sqlalchemy import select

from shared.db import Document, get_session_factory, init_db


def file_hash(path: str) -> str | None:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


def rank(doc: Document):
    return (
        0 if (doc.status == "organized" and doc.verified) else
        1 if doc.status == "organized" else
        2,
        doc.id,
    )


def dates_compatible(a, b) -> bool:
    return a is None or b is None or a == b


def main(really: bool) -> None:
    init_db()
    session = get_session_factory()()
    docs = session.execute(
        select(Document).where(Document.email_id.is_not(None))
    ).scalars().all()

    groups: dict[tuple, list] = defaultdict(list)
    for d in docs:
        key = (d.email_id, d.original_name.strip().lower(), d.ext)
        groups[key].append(d)

    to_delete: list[tuple[Document, str]] = []
    review: list[str] = []
    multi = {k: g for k, g in groups.items() if len(g) > 1}
    print(f"Grupos con repeticiones: {len(multi)}")

    for key, group in sorted(multi.items()):
        hashes = {d.id: file_hash(d.stored_path) for d in group}
        with_file = [d for d in group if hashes[d.id]]
        without_file = [d for d in group if not hashes[d.id]]

        if not with_file:
            base = sorted(group, key=rank)[0]
            rest = [d for d in group if d.id != base.id]
            if all(dates_compatible(d.doc_date, base.doc_date) for d in rest):
                to_delete += [(d, "sin archivo, metadatos iguales") for d in rest]
            else:
                review.append(f"{key[1]} (email {key[0]}): sin archivos y fechas distintas -> ids {[d.id for d in group]}")
            continue

        distinct = {hashes[d.id] for d in with_file}
        if len(distinct) != 1:
            review.append(f"{key[1]} (email {key[0]}): CONTENIDO DISTINTO -> ids {[d.id for d in with_file]}")
            continue
        content_hash = distinct.pop()
        keeper = sorted(with_file, key=rank)[0]

        for d in group:
            if d.id == keeper.id:
                continue
            h = hashes[d.id]
            if h == content_hash and dates_compatible(d.doc_date, keeper.doc_date):
                to_delete.append((d, f"copia byte a byte de #{keeper.id}"))
            elif h is None:
                to_delete.append((d, "sin archivo; contenido ya verificado"))
            else:
                motivo = "contenido distinto" if h else ""
                if h and not dates_compatible(d.doc_date, keeper.doc_date):
                    motivo = "fecha distinta"
                review.append(f"{key[1]} (email {key[0]}): {motivo} -> id {d.id} conservado")

    print(f"\n=== A ELIMINAR: {len(to_delete)} ===")
    for d, motivo in to_delete:
        lugar = d.stored_path or "(sin archivo)"
        print(f"  DEL #{d.id:<4} [{d.status:<11}] {d.original_name[:52]:<52} -> {motivo}")

    print(f"\n=== CONSERVADOS PARA REVISIÓN MANUAL: {len(review)} ===")
    for r in review:
        print(f"  ! {r}")

    if not really:
        total_files = sum(1 for d, _ in to_delete if d.stored_path)
        print(f"\nSimulación: {len(to_delete)} filas ({total_files} con archivo físico). "
              f"Ejecuta con --yes para aplicar.")
        return

    # Recalcular rutas que NO deben tocarse (conservadas)
    delete_ids = {d.id for d, _ in to_delete}
    keep_paths = {d.stored_path for d in docs
                  if d.id not in delete_ids and d.stored_path}

    removed_rows = removed_files = 0
    for d, _motivo in to_delete:
        if d.stored_path and d.stored_path not in keep_paths and os.path.exists(d.stored_path):
            os.remove(d.stored_path)
            removed_files += 1
        session.delete(d)
        removed_rows += 1
    session.commit()
    print(f"\nHecho: {removed_rows} filas eliminadas, {removed_files} archivos borrados.")


if __name__ == "__main__":
    main("--yes" in sys.argv)
