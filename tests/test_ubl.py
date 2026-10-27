import base64
from datetime import datetime
from xml.sax.saxutils import escape

from shared.parsing.ubl import parse_ubl

INVOICE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersion>UBL 2.1</cbc:UBLVersion>
  <cbc:IssueDate>2026-07-15</cbc:IssueDate>
  <cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PartyName><cbc:Name>FES POPAYAN</cbc:Name></cac:PartyName>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>FUNDACION UNIVERSITARIA DE POPAYAN</cbc:RegistrationName>
      </cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PartyLegalEntity><cbc:RegistrationName>CLIENTE EJEMPLO SAS</cbc:RegistrationName></cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="COP">665693.00</cbc:LineExtensionAmount>
    <cbc:TaxInclusiveAmount currencyID="COP">794063.00</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="COP">794063.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
</Invoice>"""

EMBEDDED = base64.b64encode(INVOICE_XML.encode()).decode()

ATTACHED_DOCUMENT = f"""<?xml version="1.0" encoding="UTF-8"?>
<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersion>UBL 2.1</cbc:UBLVersion>
  <cac:SenderParty/>
  <cac:ReceiverParty/>
  <cac:Attachment>
    <cbc:EmbeddedDocumentBinaryObject mimeCode="application/xml">{EMBEDDED}</cbc:EmbeddedDocumentBinaryObject>
  </cac:Attachment>
</AttachedDocument>"""


def _base_asserts(data: dict):
    assert data["total"] == 794063.00
    assert data["subtotal"] == 794063.00
    assert data["moneda"] == "COP"
    assert data["tipo"] == "I"
    assert data["emisor_nombre"] == "FUNDACION UNIVERSITARIA DE POPAYAN"
    assert data["receptor_nombre"] == "CLIENTE EJEMPLO SAS"
    assert data["fecha"] == datetime(2026, 7, 15)


def test_parsea_attached_document_con_factura_embebida():
    data = parse_ubl(ATTACHED_DOCUMENT.encode())
    assert data is not None
    _base_asserts(data)


def test_attached_document_con_factura_en_description():
    sobre = f"""<?xml version="1.0" encoding="UTF-8"?>
<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
  <cbc:IssueDate>2025-03-20</cbc:IssueDate>
  <cac:SenderParty/>
  <cac:ReceiverParty/>
  <cac:Attachment>
    <cac:ExternalReference>
      <cbc:MimeCode>text/xml</cbc:MimeCode>
      <cbc:Description>{escape(INVOICE_XML)}</cbc:Description>
    </cac:ExternalReference>
  </cac:Attachment>
</AttachedDocument>"""
    data = parse_ubl(sobre.encode())
    assert data is not None
    _base_asserts(data)


def test_sobre_sin_factura_embebida_usa_datos_del_sobre():
    sobre = """<?xml version="1.0" encoding="UTF-8"?>
<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
  <cbc:ID>800236937</cbc:ID>
  <cbc:IssueDate>2025-03-20</cbc:IssueDate>
  <cbc:ParentDocumentID>FD25811111</cbc:ParentDocumentID>
  <cac:SenderParty>
    <cac:PartyTaxScheme>
      <cbc:RegistrationName>THE WALT DISNEY COMPANY COLOMBIA S.A</cbc:RegistrationName>
    </cac:PartyTaxScheme>
  </cac:SenderParty>
  <cac:ReceiverParty>
    <cac:PartyTaxScheme>
      <cbc:RegistrationName>juan cedeno</cbc:RegistrationName>
    </cac:PartyTaxScheme>
  </cac:ReceiverParty>
  <cac:Attachment>
    <cac:ExternalReference><cbc:MimeCode>text/xml</cbc:MimeCode></cac:ExternalReference>
  </cac:Attachment>
</AttachedDocument>"""
    data = parse_ubl(sobre.encode())
    assert data is not None
    assert data["emisor_nombre"] == "THE WALT DISNEY COMPANY COLOMBIA S.A"
    assert data["receptor_nombre"] == "juan cedeno"
    assert data["fecha"] == datetime(2025, 3, 20)
    assert data["folio"] == "FD25811111"
    assert data["total"] is None


def test_parsea_invoice_directo():
    data = parse_ubl(INVOICE_XML.encode())
    assert data is not None
    _base_asserts(data)


def test_nota_credito_es_tipo_e():
    xml = INVOICE_XML.replace("<cbc:InvoiceTypeCode>01<", "<cbc:InvoiceTypeCode>02<")
    data = parse_ubl(xml.encode())
    assert data is not None
    assert data["tipo"] == "E"


def test_no_es_ubl():
    assert parse_ubl(b"<otro><cosa/></otro>") is None
    assert parse_ubl(b"no soy xml") is None


def test_attached_document_sin_embebido_devuelve_none():
    sin_attachment = """<?xml version="1.0" encoding="UTF-8"?>
<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersion>UBL 2.1</cbc:UBLVersion>
  <cac:SenderParty/>
  <cac:ReceiverParty/>
</AttachedDocument>"""
    assert parse_ubl(sin_attachment.encode()) is None


def test_cfdi_sigue_ganando_en_cfdi_puros():
    from shared.parsing.cfdi import parse_cfdi
    cfdi_sample = (b'<?xml version="1.0"?><cfdi:Comprobante '
                   b'xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Version="4.0" '
                   b'Total="100.00" Moneda="MXN"/>')
    assert parse_cfdi(cfdi_sample) is not None


def test_creditnote_extrae_lineas_y_tipo_e():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<CreditNote xmlns="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
     xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
     xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
  <cbc:IssueDate>2026-06-05</cbc:IssueDate>
  <cac:AccountingSupplierParty>
    <cac:Party><cac:PartyTaxScheme><cbc:RegistrationName>CENTRAL DEL AGRO S.A.S</cbc:RegistrationName></cac:PartyTaxScheme></cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party><cac:PartyTaxScheme><cbc:RegistrationName>CEDENO YESID</cbc:RegistrationName></cac:PartyTaxScheme></cac:Party>
  </cac:AccountingCustomerParty>
  <cac:CreditNoteLine>
    <cbc:ID>1</cbc:ID>
    <cbc:CreditedQuantity>50</cbc:CreditedQuantity>
    <cac:Item><cbc:Description>FERTILIZANTE</cbc:Description></cac:Item>
    <cac:Price><cbc:PriceAmount>165000.00</cbc:PriceAmount></cac:Price>
    <cbc:LineExtensionAmount>8250000.00</cbc:LineExtensionAmount>
  </cac:CreditNoteLine>
  <cac:LegalMonetaryTotal>
    <cbc:PayableAmount currencyID="COP">8250000.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
</CreditNote>"""
    data = parse_ubl(xml.encode())
    assert data is not None
    assert data["tipo"] == "E"
    assert data["total"] == 8250000.0
    assert data["emisor_nombre"] == "CENTRAL DEL AGRO S.A.S"
    assert len(data["conceptos"]) == 1
    line = data["conceptos"][0]
    assert line["descripcion"] == "FERTILIZANTE"
    assert line["cantidad"] == 50.0
    assert line["precio"] == 165000.0
    assert line["subtotal"] == 8250000.0


def test_debitnote_es_tipo_d():
    xml = INVOICE_XML.replace("<cbc:InvoiceTypeCode>01<", "<cbc:InvoiceTypeCode>03<")
    data = parse_ubl(xml.encode())
    assert data is not None
    assert data["tipo"] == "D"


def test_factura_embebida_sin_party_usa_datos_del_sobre():
    inv_minimo = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
     xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
     xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
  <cbc:IssueDate>2026-08-16</cbc:IssueDate>
  <cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>
  <cac:LegalMonetaryTotal>
    <cbc:PayableAmount currencyID="COP">130500.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
</Invoice>"""
    sobre = f"""<?xml version="1.0" encoding="UTF-8"?>
<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2"
     xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
     xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
  <cbc:IssueDate>2026-08-16</cbc:IssueDate>
  <cac:SenderParty>
    <cac:PartyTaxScheme><cbc:RegistrationName>MANISOL S.A.S</cbc:RegistrationName><cbc:CompanyID>890801339</cbc:CompanyID></cac:PartyTaxScheme>
  </cac:SenderParty>
  <cac:ReceiverParty>
    <cac:PartyTaxScheme><cbc:RegistrationName>YESID ALBERTO CEDEÑO</cbc:RegistrationName></cac:PartyTaxScheme>
  </cac:ReceiverParty>
  <cac:Attachment>
    <cac:ExternalReference>
      <cbc:MimeCode>text/xml</cbc:MimeCode>
      <cbc:Description>{escape(inv_minimo)}</cbc:Description>
    </cac:ExternalReference>
  </cac:Attachment>
</AttachedDocument>"""
    data = parse_ubl(sobre.encode())
    assert data is not None
    assert data["total"] == 130500.0
    assert data["emisor_nombre"] == "MANISOL S.A.S"
    assert data["emisor_rfc"] == "890801339"
