"""Cifrado simétrico para credenciales sensibles guardadas en la base de datos.

La clave se genera automáticamente en ``<DATA_DIR>/.secret_key`` la primera vez
que se necesita. El archivo vive en el volumen de datos, por lo que sobrevive a
los reinicios y no se versiona. Los valores antiguos en texto plano siguen
funcionando: ``decrypt_secret`` los devuelve tal cual hasta que se vuelvan a
guardar.
"""
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

from shared.config import DATA_DIR

log = logging.getLogger("crypto")

_PREFIX = "enc:v1:"
_cached_key: bytes | None = None


def _key_path() -> str:
    return os.path.join(DATA_DIR, ".secret_key")


def _load_key() -> bytes:
    global _cached_key
    if _cached_key is not None:
        return _cached_key

    os.makedirs(DATA_DIR, exist_ok=True)
    path = _key_path()

    if os.path.exists(path):
        with open(path, "rb") as fh:
            key = fh.read().strip()
        if key:
            _cached_key = key
            return key

    key = Fernet.generate_key()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Otro proceso la creó al mismo tiempo.
        with open(path, "rb") as fh:
            key = fh.read().strip()
        if not key:
            raise RuntimeError("La clave de cifrado existe pero está vacía")
    else:
        with os.fdopen(fd, "wb") as fh:
            fh.write(key)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    _cached_key = key
    return key


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(_PREFIX)


def encrypt_secret(value: str | None) -> str:
    """Cifra un valor. Si ya está cifrado o viene vacío, lo deja igual."""
    if not value:
        return ""
    if is_encrypted(value):
        return value
    token = Fernet(_load_key()).encrypt(value.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def decrypt_secret(value: str | None) -> str:
    """Descifra un valor. Los valores antiguos sin prefijo se devuelven tal cual."""
    if not value:
        return ""
    if not is_encrypted(value):
        return value
    try:
        token = value[len(_PREFIX):].encode("ascii")
        return Fernet(_load_key()).decrypt(token).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        log.error("No se pudo descifrar una credencial; revisa la clave .secret_key")
        return ""
