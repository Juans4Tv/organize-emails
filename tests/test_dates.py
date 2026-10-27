import pytest
from datetime import datetime
from shared.parsing.dates import extract_issue_date
from shared.parsing.ubl import cuche_key_from_filename, cuche_key_from_xml
from xml.etree import ElementTree


class TestExtractIssueDate:

    def test_fecha_factura_formato_dd_mm_yyyy(self):
        text = "Fecha de factura: 15/01/2026\nResto del documento"
        assert extract_issue_date(text) == datetime(2026, 1, 15)

    def test_fecha_factura_formato_dd_mm_yyyy_with_dots(self):
        text = "Fecha de factura: 15.01.2026"
        assert extract_issue_date(text) == datetime(2026, 1, 15)

    def test_fecha_con_hora(self):
        text = "Fecha y hora Factura Generación\n23/01/2026, 10:18"
        assert extract_issue_date(text) == datetime(2026, 1, 23)

    def test_fecha_generacion_con_lf(self):
        text = "Fecha y hora Factura\nGeneración\n23/01/2026, 10:18\nExpedición"
        assert extract_issue_date(text) == datetime(2026, 1, 23)

    def test_fecha_escrita(self):
        text = "Fecha de emisión: 24 de julio de 2024"
        assert extract_issue_date(text) == datetime(2024, 7, 24)

    def test_iso_date(self):
        text = "La fecha de la factura es 2026-08-20 para el pedido"
        assert extract_issue_date(text) == datetime(2026, 8, 20)

    def test_iso_with_time(self):
        text = "Fecha: 2026-08-20T14:30:00"
        assert extract_issue_date(text) == datetime(2026, 8, 20)

    def test_no_date_returns_none(self):
        text = "Este documento no tiene fechas válidas"
        assert extract_issue_date(text) is None

    def test_empty_text(self):
        assert extract_issue_date("") is None
        assert extract_issue_date(None) is None

    def test_invalid_date_rejected(self):
        text = "Fecha de factura: 99/99/9999"
        assert extract_issue_date(text) is None

    def test_prioridad_sobre_otras_fechas(self):
        text = "Fecha de vencimiento: 99/99/9999\nFecha de factura: 15/03/2025"
        assert extract_issue_date(text) == datetime(2025, 3, 15)


class TestCucheKey:

    def test_from_filename_ad_prefix(self):
        assert cuche_key_from_filename("ad090119359000826000006fb.xml") == "090119359000826000006fb"

    def test_from_filename_fv_prefix(self):
        assert cuche_key_from_filename("fv08915018350152600082853.xml") == "08915018350152600082853"

    def test_from_filename_no_prefix(self):
        assert cuche_key_from_filename("factura.pdf") == "factura"

    def test_from_filename_mixed_case(self):
        assert cuche_key_from_filename("AD0901XX.pdf") == "0901xx"

    def test_from_xml_root_id(self):
        xml = """<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2">
            <cbc:ID xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">abc123456789</cbc:ID>
        </AttachedDocument>"""
        root = ElementTree.fromstring(xml)
        assert cuche_key_from_xml(root) == "abc123456789"

    def test_from_xml_no_id(self):
        xml = """<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2">
            <cbc:ID xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">ab</cbc:ID>
        </AttachedDocument>"""
        root = ElementTree.fromstring(xml)
        assert cuche_key_from_xml(root) == ""
