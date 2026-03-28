import pytest
from services.asy_parser import parse_asy_string, AsySymbol, Pin


RESISTOR_ASY = """\
Version 4
SymbolType CELL
LINE Normal 16 88 16 96
LINE Normal 0 80 16 88
LINE Normal 32 64 0 80
LINE Normal 0 48 32 64
LINE Normal 32 32 0 48
LINE Normal 16 16 16 24
LINE Normal 16 24 32 32
WINDOW 0 36 40 Left 2
WINDOW 3 36 76 Left 2
SYMATTR Value R
SYMATTR Prefix R
SYMATTR Description A resistor
PIN 16 16 NONE 0
PINATTR PinName A
PINATTR SpiceOrder 1
PIN 16 96 NONE 0
PINATTR PinName B
PINATTR SpiceOrder 2
"""

VOLTAGE_ASY = """\
Version 4
SymbolType CELL
LINE Normal -8 36 8 36
LINE Normal -8 76 8 76
LINE Normal 0 28 0 44
LINE Normal 0 96 0 88
LINE Normal 0 16 0 24
CIRCLE Normal -32 24 32 88
WINDOW 0 24 16 Left 2
WINDOW 3 24 96 Left 2
SYMATTR Value V
SYMATTR Prefix V
SYMATTR Description Voltage Source
PIN 0 16 NONE 0
PINATTR PinName +
PINATTR SpiceOrder 1
PIN 0 96 NONE 0
PINATTR PinName -
PINATTR SpiceOrder 2
"""

OPAMP2_ASY = """\
Version 4
SymbolType CELL
LINE Normal -32 32 32 64
LINE Normal -32 96 32 64
LINE Normal -32 32 -32 96
LINE Normal -28 48 -20 48
LINE Normal -28 80 -20 80
LINE Normal -24 84 -24 76
LINE Normal 0 32 0 48
LINE Normal 0 96 0 80
LINE Normal 4 44 12 44
LINE Normal 8 40 8 48
LINE Normal 4 84 12 84
WINDOW 0 16 32 Left 2
WINDOW 3 16 96 Left 2
SYMATTR Value opamp2
SYMATTR Prefix X
SYMATTR Description Basic Operational Amplifier
PIN -32 80 NONE 0
PINATTR PinName In+
PINATTR SpiceOrder 1
PIN -32 48 NONE 0
PINATTR PinName In-
PINATTR SpiceOrder 2
PIN 0 32 NONE 0
PINATTR PinName V+
PINATTR SpiceOrder 3
PIN 0 96 NONE 0
PINATTR PinName V-
PINATTR SpiceOrder 4
PIN 32 64 NONE 0
PINATTR PinName OUT
PINATTR SpiceOrder 5
"""


def test_parse_resistor():
    sym = parse_asy_string(RESISTOR_ASY)
    assert isinstance(sym, AsySymbol)
    assert len(sym.lines) == 7
    assert len(sym.pins) == 2
    pin_a = next(p for p in sym.pins if p.name == "A")
    pin_b = next(p for p in sym.pins if p.name == "B")
    assert (pin_a.x, pin_a.y) == (16, 16)
    assert (pin_b.x, pin_b.y) == (16, 96)
    assert sym.prefix == "R"
    assert sym.description == "A resistor"
    assert len(sym.circles) == 0
    # bounds: (min_x, min_y, max_x, max_y)
    bx1, by1, bx2, by2 = sym.bounds
    assert bx1 == 0
    assert by1 == 16
    assert bx2 == 32
    assert by2 == 96


def test_parse_voltage_source_with_circle():
    sym = parse_asy_string(VOLTAGE_ASY)
    assert len(sym.lines) == 5
    assert len(sym.circles) == 1
    assert sym.prefix == "V"
    assert len(sym.pins) == 2
    pin_names = {p.name for p in sym.pins}
    assert "+" in pin_names
    assert "-" in pin_names


def test_parse_opamp2_with_subdirectory():
    sym = parse_asy_string(OPAMP2_ASY)
    assert len(sym.lines) == 11
    assert sym.prefix == "X"
    assert len(sym.pins) == 5
    pin_names = {p.name for p in sym.pins}
    assert pin_names == {"In+", "In-", "V+", "V-", "OUT"}


def test_to_svg_path():
    content = """\
Version 4
SymbolType CELL
LINE Normal 0 0 32 0
LINE Normal 32 0 32 32
PIN 0 0 NONE 0
PINATTR PinName A
PINATTR SpiceOrder 1
"""
    sym = parse_asy_string(content)
    svg = sym.to_svg_path()
    assert "M0,0 L32,0" in svg
    assert "M32,0 L32,32" in svg


def test_to_svg_path_with_circle():
    content = """\
Version 4
SymbolType CELL
CIRCLE Normal 0 0 64 64
PIN 0 0 NONE 0
PINATTR PinName A
PINATTR SpiceOrder 1
"""
    sym = parse_asy_string(content)
    svg = sym.to_svg_path()
    # Circle defined by bounding box (0,0)-(64,64) has center (32,32)
    assert "32,32" in svg


def test_to_dict():
    sym = parse_asy_string(RESISTOR_ASY)
    d = sym.to_dict()
    assert d["prefix"] == "R"
    assert d["description"] == "A resistor"
    assert isinstance(d["pins"], list)
    assert len(d["pins"]) == 2
    assert "geometry" in d
    assert "lines" in d["geometry"]
    assert "bounds" in d["geometry"]
    assert "symbol" in d
    assert "svgPath" in d["symbol"]
    assert "width" in d["symbol"]
    assert "height" in d["symbol"]
