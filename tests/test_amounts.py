from shared.parsing.amounts import extract_amount, extract_currency


def test_total_con_signo_pesos():
    amount, conf = extract_amount("SUBTOTAL 1000.00\nTOTAL $1,234.56")
    assert amount == 1234.56
    assert conf >= 0.85


def test_total_a_pagar_prioridad_alta():
    amount, conf = extract_amount("Valor: 50.00\nTOTAL A PAGAR: $2,500.00")
    assert amount == 2500.0
    assert conf >= 0.9


def test_valor_total():
    amount, conf = extract_amount("VALOR TOTAL $890.99")
    assert amount == 890.99
    assert conf >= 0.9


def test_importe_total():
    amount, _ = extract_amount("IMPORTE TOTAL: 15,000.00 MXN")
    assert amount == 15000.0


def test_subtotal_no_confunde():
    amount, _ = extract_amount("SUBTOTAL $2,000.00\nIVA $320.00\nTOTAL A PAGAR $2,320.00")
    assert amount == 2320.0


def test_total_con_palabra_importe():
    amount, _ = extract_amount("IMPORTE TOTAL: $9876.54 MXN")
    assert amount == 9876.54


def test_sin_etiqueta_toma_el_mayor():
    amount, _ = extract_amount("Cargo 1: $50.00\nCargo 2: $1,200.00")
    assert amount == 1200.0


def test_formato_europeo():
    amount, _ = extract_amount("Total: 1.234,56")
    assert amount == 1234.56


def test_texto_vacio():
    assert extract_amount("")[0] is None


def test_sin_montos():
    assert extract_amount("gracias por su compra")[0] is None


def test_moneda_detectada():
    assert extract_currency("TOTAL USD 100") == "USD"
    assert extract_currency("total 500 mxn") == "MXN"
    assert extract_currency("total 500 cop") == "COP"
    assert extract_currency("sin moneda") == "COP"
