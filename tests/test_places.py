from shared.parsing.places import (
    detect_place_from_text,
    normalize_place_name,
    sanitize_folder,
)


def test_normaliza_sufijos_legales():
    assert normalize_place_name("COMERCIALIZADORA DEL NORTE SA DE CV") == "Comercializadora Del Norte"
    assert normalize_place_name("LA BUENA S.A. DE C.V.") == "La Buena"


def test_sanitize_folder_quita_caracteres_invalidos():
    assert sanitize_folder('TIENDA/ OXXO: "centro"') == "TIENDA-OXXO-centro"
    assert sanitize_folder("") == "Sin-Lugar"
    assert "\\" not in sanitize_folder("a\\b")


def test_detecta_razon_social_etiquetada():
    text = "FACTURA\nRAZON SOCIAL: PAPELERIA MUNDIAL SA DE CV\nRFC: PMI980101ABC\nTOTAL $500.00"
    name, conf = detect_place_from_text(text)
    assert "Papeleria Mundial" in name
    assert conf >= 0.7


def test_detecta_cercano_a_rfc():
    text = "TICKET 12345\nFECHA 2026-01-15\nFARMACIAS SIMILARES\nRFC: FSI850101XYZ\nTOTAL $230.00"
    name, _ = detect_place_from_text(text)
    assert "Farmacias Similares" in name


def test_primera_linea_como_fallback():
    text = "SUPER MERCADOS AHORRO\nCalle falsa 123\nTOTAL $100.00"
    name, conf = detect_place_from_text(text)
    assert "Super" in name
    assert conf > 0


def test_vacio():
    assert detect_place_from_text("")[0] == ""
