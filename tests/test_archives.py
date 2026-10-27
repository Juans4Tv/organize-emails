import io
import tarfile
import zipfile

import pytest

from shared.archives import ArchivePasswordError, extract_members, is_archive_ext


def _zip_with(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_tar_gz_con_pdf():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        data = b"%PDF-1.4 fake"
        info = tarfile.TarInfo("facturas/factura1.pdf")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    members = extract_members(buf.getvalue(), ".tar.gz")
    assert len(members) == 1
    assert members[0][0] == "factura1.pdf"
    assert members[0][1][:5] == b"%PDF-"


def test_zip_filtra_no_deseados():
    payload = _zip_with({
        "a/factura.pdf": b"%PDF-1.4",
        "b/nota.xml": b"<Comprobante/>",
        "c/leeme.txt": b"hola",
        "d/imagen.png": b"\x89PNG",
    })
    members = extract_members(payload, ".zip")
    names = sorted(m[0] for m in members)
    assert names == ["factura.pdf", "nota.xml"]


def test_magic_rar_detectado_por_contenido():
    # RAR falso (cabecera Rar! pero contenido inválido): bsdtar devuelve [] sin explotar
    from shared.archives import RAR_MAGIC
    payload = RAR_MAGIC + b"basura-no-rar"
    assert extract_members(payload, "") == []


@pytest.mark.parametrize("ext", [".zip", ".rar", ".7z", ".tar", ".tar.gz", ".tgz"])
def test_is_archive_ext(ext):
    assert is_archive_ext(ext)


def test_no_es_archivo_comprimido():
    assert not is_archive_ext(".pdf")
