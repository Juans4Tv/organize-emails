from shared.parsing.cfdi import classify_flow, parse_cfdi

CFDI_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
    Version="4.0" TipoDeComprobante="I" Total="1150.00"
    Moneda="MXN" Fecha="2026-08-01T12:30:00">
  <cfdi:Emisor Rfc="EMP890101AAA" Nombre="Tecnologia Aplicada SA de CV"/>
  <cfdi:Receptor Rfc="XAXX010101000" Nombre="PUBLICO EN GENERAL"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="43232400" Descripcion="Laptop" Importe="991.38"/>
  </cfdi:Conceptos>
</cfdi:Comprobante>"""


def test_parsea_cfdi_basico():
    cfdi = parse_cfdi(CFDI_SAMPLE.encode())
    assert cfdi is not None
    assert cfdi["total"] == 1150.00
    assert cfdi["tipo"] == "I"
    assert cfdi["emisor_rfc"] == "EMP890101AAA"
    assert "Tecnologia Aplicada" in cfdi["emisor_nombre"]
    assert cfdi["fecha"].year == 2026
    assert cfdi["conceptos"][0] == "Laptop"


def test_no_es_cfdi():
    assert parse_cfdi(b"<otro><cosa/></otro>") is None
    assert parse_cfdi(b"esto no es xml") is None


def test_flujo_con_rfc_propio_receptor():
    flow, conf = classify_flow(parse_cfdi(CFDI_SAMPLE.encode()), own_rfc="XAXX010101000")
    assert flow == "gasto"
    assert conf == 0.95


def test_flujo_emisor_soy_yo_es_ganancia():
    flow, _ = classify_flow(parse_cfdi(CFDI_SAMPLE.encode()), own_rfc="EMP890101AAA")
    assert flow == "ganancia"


def test_flujo_nota_de_credito_sin_rfc_propio():
    sample = CFDI_SAMPLE.replace('TipoDeComprobante="I"', 'TipoDeComprobante="E"')
    flow, _ = classify_flow(parse_cfdi(sample.encode()))
    assert flow == "ganancia"


def test_flujo_ingreso_recibido_default_gasto():
    flow, _ = classify_flow(parse_cfdi(CFDI_SAMPLE.encode()))
    assert flow == "gasto"
