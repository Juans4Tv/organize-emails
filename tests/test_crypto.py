import shared.crypto as crypto


def test_crypto_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(crypto, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(crypto, "_cached_key", None)

    token = crypto.encrypt_secret("abcd efgh ijkl mnop")

    assert token != "abcd efgh ijkl mnop"
    assert crypto.is_encrypted(token)
    assert crypto.decrypt_secret(token) == "abcd efgh ijkl mnop"
    assert (tmp_path / ".secret_key").exists()


def test_crypto_es_idempotente_y_lee_texto_plano(tmp_path, monkeypatch):
    monkeypatch.setattr(crypto, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(crypto, "_cached_key", None)

    token = crypto.encrypt_secret("secreto")
    assert crypto.encrypt_secret(token) == token
    assert crypto.decrypt_secret("valor-antiguo") == "valor-antiguo"


def test_crypto_valores_vacios():
    assert crypto.encrypt_secret("") == ""
    assert crypto.decrypt_secret("") == ""
    assert crypto.is_encrypted("") is False
