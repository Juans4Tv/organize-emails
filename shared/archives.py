"""Extracción de miembros desde archivos comprimidos: zip, rar, 7z, tar.*.

Los formatos nativos (zip/tar) usan la stdlib; rar y 7z se delegan a bsdtar
(libarchive), instalado en las imágenes Docker.
"""
import io
import logging
import os
import subprocess
import tarfile
import tempfile
import zipfile

log = logging.getLogger("archives")

ZIP_MAGIC = b"PK\x03\x04"
RAR_MAGIC = b"Rar!"
SEVENZ_MAGIC = b"7z\xbc\xaf\x27\x1c"

ARCHIVE_EXTS = {
    ".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz",
    ".tar.gz", ".tar.bz2", ".tar.xz",
}
WANTED_MEMBER_EXTS = {".pdf", ".xml"}


class ArchivePasswordError(Exception):
    pass


def is_archive_ext(ext: str) -> bool:
    return (ext or "").lower() in ARCHIVE_EXTS


def _wanted(name: str) -> bool:
    base = os.path.basename(name.replace("\\", "/"))
    if not base or base.startswith(("__MACOSX", ".")):
        return False
    return os.path.splitext(base)[1].lower() in WANTED_MEMBER_EXTS


def extract_members(payload: bytes, ext_hint: str = "") -> list[tuple[str, bytes]]:
    """Devuelve [(nombre_archivo, bytes)] de los pdf/xml dentro del archivo.

    Lanza ArchivePasswordError si el archivo requiere contraseña.
    """
    if payload[:4] == ZIP_MAGIC or ext_hint.lower() == ".zip":
        return _from_zip(payload)
    if payload[:6] == SEVENZ_MAGIC or ext_hint.lower() == ".7z":
        return _via_bsdtar(payload, ".7z")
    if payload[:4] == RAR_MAGIC or ext_hint.lower() in (".rar",):
        return _via_bsdtar(payload, ".rar")
    return _from_tar(payload)


def _from_zip(payload: bytes) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for info in zf.infolist():
                if info.is_dir() or not _wanted(info.filename):
                    continue
                try:
                    out.append((os.path.basename(info.filename), zf.read(info)))
                except RuntimeError as exc:
                    if "password" in str(exc).lower():
                        raise ArchivePasswordError("ZIP protegido con contraseña") from exc
                    raise
    except zipfile.BadZipFile:
        log.warning("ZIP corrupto")
    return out


def _from_tar(payload: bytes) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    try:
        with tarfile.open(fileobj=io.BytesIO(payload)) as tf:
            for member in tf.getmembers():
                if not member.isfile() or not _wanted(member.name):
                    continue
                fh = tf.extractfile(member)
                if fh is not None:
                    out.append((os.path.basename(member.name), fh.read()))
    except tarfile.TarError:
        log.warning("Archivo tar no legible")
    except EOFError:
        log.warning("Archivo truncado")
    return out


def _via_bsdtar(payload: bytes, ext: str) -> list[tuple[str, bytes]]:
    """RAR/7z vía bsdtar (libarchive). Requiere libarchive-tools en la imagen."""
    tmp_dir = tempfile.mkdtemp(prefix="oo_arc_")
    archive_path = os.path.join(tmp_dir, f"archivo{ext}")
    extract_dir = os.path.join(tmp_dir, "out")
    os.makedirs(extract_dir, exist_ok=True)
    try:
        with open(archive_path, "wb") as fh:
            fh.write(payload)
        try:
            proc = subprocess.run(
                ["bsdtar", "-xf", archive_path, "-C", extract_dir],
                capture_output=True,
                timeout=120,
            )
        except FileNotFoundError:
            log.warning("bsdtar no disponible en este sistema; no se pudo extraer %s", ext)
            return []
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", "replace").lower()
            if "password" in err or "encrypted" in err:
                raise ArchivePasswordError(f"Archivo {ext} protegido con contraseña")
            log.warning("bsdtar no pudo extraer (%s): %s", ext, err[:200])
            return []
        out: list[tuple[str, bytes]] = []
        for root, _dirs, files in os.walk(extract_dir):
            for name in files:
                if not _wanted(name):
                    continue
                path = os.path.join(root, name)
                try:
                    with open(path, "rb") as fh:
                        out.append((name, fh.read()))
                except OSError:
                    continue
        return out
    finally:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)
