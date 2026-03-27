import pytest
from services.validator import validate_asc, ValidationResult


def test_valid_minimal_asc():
    asc = "Version 4\nSHEET 1 880 680\n"
    result = validate_asc(asc)
    assert result.valid is True
    assert result.errors == []


def test_missing_version_line():
    asc = "SHEET 1 880 680\n"
    result = validate_asc(asc)
    assert result.valid is False
    assert any("Version 4" in e for e in result.errors)


def test_missing_sheet_line():
    asc = "Version 4\n"
    result = validate_asc(asc)
    assert result.valid is False
    assert any("SHEET" in e for e in result.errors)


def test_symbol_without_symattr():
    asc = "Version 4\nSHEET 1 880 680\nSYMBOL res 272 128 R90\n"
    result = validate_asc(asc)
    assert result.valid is False
    assert any("InstName" in e for e in result.errors)


def test_symbol_with_symattr():
    asc = (
        "Version 4\nSHEET 1 880 680\n"
        "SYMBOL res 272 128 R90\n"
        "SYMATTR InstName R1\n"
        "SYMATTR Value 1k\n"
    )
    result = validate_asc(asc)
    assert result.valid is True


def test_wire_with_valid_coordinates():
    asc = (
        "Version 4\nSHEET 1 880 680\n"
        "WIRE 416 144 336 144\n"
    )
    result = validate_asc(asc)
    assert result.valid is True


def test_wire_with_non_integer_coordinates():
    asc = (
        "Version 4\nSHEET 1 880 680\n"
        "WIRE 416.5 144 336 144\n"
    )
    result = validate_asc(asc)
    assert result.valid is False
    assert any("integer" in e.lower() for e in result.errors)


def test_flag_valid():
    asc = (
        "Version 4\nSHEET 1 880 680\n"
        "FLAG 160 272 0\n"
    )
    result = validate_asc(asc)
    assert result.valid is True


def test_text_directive():
    asc = (
        "Version 4\nSHEET 1 880 680\n"
        "TEXT 400 450 Left 2 !.tran 0.005\n"
    )
    result = validate_asc(asc)
    assert result.valid is True


def test_full_reference_asc():
    """Validate the actual reference .asc file content."""
    asc = (
        "Version 4\n"
        "SHEET 1 880 680\n"
        "SYMBOL opamp2 400 128 R0\n"
        "SYMATTR InstName U1\n"
        "SYMATTR Value ADA4627\n"
        "SYMBOL res 272 128 R90\n"
        "WINDOW 0 0 56 VBottom 2\n"
        "WINDOW 3 32 56 VBottom 2\n"
        "SYMATTR InstName R5\n"
        "SYMATTR Value 1000 noiseless\n"
        "WIRE 416 144 336 144\n"
        "FLAG 160 272 0\n"
        "FLAG 608 176 OUT\n"
        "TEXT 400 450 Left 2 !.param RINP=1k PSV=15\n"
        "TEXT 400 480 Left 2 !.tran 0.005\n"
    )
    result = validate_asc(asc)
    assert result.valid is True
