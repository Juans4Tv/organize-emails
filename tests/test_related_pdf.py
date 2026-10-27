from shared.names import pdf_sibling_match


def test_exact_stem():
    assert pdf_sibling_match(
        "ad0890900076006260067FEB0.xml", "ad0890900076006260067FEB0.pdf"
    )


def test_ad_xml_vs_fv_pdf():
    # AttachedDocument (ad) vs Factura de venta (fv), mismo CUFE
    assert pdf_sibling_match(
        "ad090119359000826000006fb.xml", "fv090119359000826000006fb.pdf"
    )


def test_fv_xml_vs_fv_pdf():
    assert pdf_sibling_match(
        "fv08915018350152600082853.xml", "fv08915018350152600082853.PDF"
    )


def test_case_and_spaces_ignored():
    assert pdf_sibling_match(
        " AD090119.XML ", "ad090119.pdf"
    )


def test_different_cufe():
    assert not pdf_sibling_match("ad090111.xml", "fv090122.pdf")


def test_unrelated_names():
    assert not pdf_sibling_match("factura.xml", "comprobante_pago.pdf")


def test_bare_stem_not_stripped():
    # 'ad'/'fv' solos no se quitan; stems idénticos siguen emparejando
    assert pdf_sibling_match("ad.xml", "ad.pdf")
    assert not pdf_sibling_match("otro.xml", "fv.pdf")
