import pytest

from shared.money import parse_user_amount
from shared.names import name_matches_owner


@pytest.mark.parametrize("raw,expected", [
    ("1234567.89", 1234567.89),
    ("1.234.567,89", 1234567.89),
    ("1234567", 1234567.0),
    ("1234567,5", 1234567.5),
    ("1,234,567", 1234567.0),
    ("$ 97.629.032,96", 97629032.96),
    ("0.99", 0.99),
    ("1234.567", 1234567.0),
])
def test_parse_user_amount_ok(raw, expected):
    assert parse_user_amount(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "abc", "12,34.56.78"])
def test_parse_user_amount_invalid(raw):
    with pytest.raises(ValueError):
        parse_user_amount(raw)


def test_owner_full_name_contains():
    assert name_matches_owner(
        "JUAN MIGUEL CEDEÑO SOLANO", "Juan Miguel Cedeño Solano"
    )


def test_owner_partial_tokens():
    # en la factura solo aparecen nombre y un apellido
    assert name_matches_owner("Juan Cedeño", "Juan Miguel Cedeño Solano")


def test_owner_accent_and_case_insensitive():
    assert name_matches_owner("cedeno solano", "Cedeño Solano Juan Miguel")


def test_different_person():
    assert not name_matches_owner(
        "Fundacion Universitaria De Popayan", "Juan Miguel Cedeño Solano"
    )


def test_empty_names_never_match():
    assert not name_matches_owner("", "Juan")
    assert not name_matches_owner("Juan", "")
