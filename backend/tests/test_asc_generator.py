import pytest
from services.asc_generator import generate_asc, SchematicIR


def test_empty_schematic():
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    asc = generate_asc(ir)
    assert asc.startswith("Version 4\n")
    assert "SHEET 1 880 680" in asc


def test_single_resistor():
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    ir.add_component("res", "R1", "1k", 272, 128, "R90")
    asc = generate_asc(ir)
    assert "SYMBOL res 272 128 R90" in asc
    assert "SYMATTR InstName R1" in asc
    assert "SYMATTR Value 1k" in asc


def test_component_with_value2():
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    ir.add_component(
        "voltage", "V3", "PULSE(0 0.01 0 1u 1u 0.0005 0.001 100)",
        112, 288, "R0", value2="AC 0.01"
    )
    asc = generate_asc(ir)
    assert "SYMBOL voltage 112 288 R0" in asc
    assert "SYMATTR InstName V3" in asc
    assert "SYMATTR Value PULSE(0 0.01 0 1u 1u 0.0005 0.001 100)" in asc
    assert "SYMATTR Value2 AC 0.01" in asc


def test_wires():
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    ir.add_wire(416, 144, 336, 144)
    ir.add_wire(336, 144, 336, 176)
    asc = generate_asc(ir)
    assert "WIRE 416 144 336 144" in asc
    assert "WIRE 336 144 336 176" in asc


def test_flags():
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    ir.add_flag("0", 160, 272)
    ir.add_flag("OUT", 608, 176)
    asc = generate_asc(ir)
    assert "FLAG 160 272 0" in asc
    assert "FLAG 608 176 OUT" in asc


def test_text_directives():
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    ir.add_text(".param RINP=1k PSV=15", 400, 450)
    ir.add_text(".tran 0.005", 400, 480)
    asc = generate_asc(ir)
    assert "TEXT 400 450 Left 2 !.param RINP=1k PSV=15" in asc
    assert "TEXT 400 480 Left 2 !.tran 0.005" in asc


def test_section_ordering():
    """Sections must appear in order: version, sheet, symbols, wires, flags, text."""
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    ir.add_component("res", "R1", "1k", 100, 100, "R0")
    ir.add_wire(100, 100, 200, 100)
    ir.add_flag("0", 150, 150)
    ir.add_text(".tran 1", 300, 300)
    asc = generate_asc(ir)
    lines = asc.strip().split("\n")

    symbol_idx = next(i for i, l in enumerate(lines) if l.startswith("SYMBOL"))
    wire_idx = next(i for i, l in enumerate(lines) if l.startswith("WIRE"))
    flag_idx = next(i for i, l in enumerate(lines) if l.startswith("FLAG"))
    text_idx = next(i for i, l in enumerate(lines) if l.startswith("TEXT"))

    assert symbol_idx < wire_idx < flag_idx < text_idx


def test_full_reference_circuit():
    """Generate the reference amplifier noise circuit and validate it."""
    ir = SchematicIR(sheet_width=880, sheet_height=680)

    ir.add_component("opamp2", "U1", "ADA4627", 400, 128, "R0")
    ir.add_component("res", "R5", "1000 noiseless", 272, 128, "R90")
    ir.add_component("res", "R6", "20.5 noiseless", 160, 176, "R0")
    ir.add_component("res", "R4", "{RINP} noiseless", 272, 208, "R90")
    ir.add_component(
        "voltage", "V3", "PULSE(0 0.01 0 1u 1u 0.0005 0.001 100)",
        112, 288, "R0", value2="AC 0.01"
    )
    ir.add_component("voltage", "V1", "{PSV}", 640, 144, "R0")
    ir.add_component("voltage", "V2", "{PSV}", 640, 304, "R0")

    ir.add_wire(416, 144, 336, 144)
    ir.add_wire(336, 144, 336, 176)
    ir.add_wire(336, 176, 160, 176)
    ir.add_wire(416, 208, 336, 208)

    ir.add_flag("0", 160, 272)
    ir.add_flag("OUT", 608, 176)

    ir.add_text(".param RINP=1k PSV=15", 400, 450)
    ir.add_text(".tran 0.005", 400, 480)
    ir.add_text(".noise V(OUT) V3 dec 10 1 1Meg", 400, 510)

    asc = generate_asc(ir)

    from services.validator import validate_asc
    result = validate_asc(asc)
    assert result.valid is True, f"Validation errors: {result.errors}"
