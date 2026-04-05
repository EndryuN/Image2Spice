"""End-to-end test: mock VLM responses -> layout -> wires -> asc_generator -> validate."""
import json
from pathlib import Path

from services.schemas import normalize_pin
from services.layout import compute_layout
from services.wire_router import compute_wires
from services.asc_generator import SchematicIR, generate_asc
from services.validator import validate_asc

DICTIONARY_DIR = Path(__file__).parent.parent.parent / "dictionary"


def _load_dictionary() -> dict:
    return json.loads(
        (DICTIONARY_DIR / "components.json").read_text(encoding="utf-8")
    )


# ── Mock VLM responses for a simple voltage divider ──────────────────────────

MOCK_COMPONENTS = [
    {"type": "voltage", "instanceName": "V1", "value": "5"},
    {"type": "res", "instanceName": "R1", "value": "10k"},
    {"type": "res", "instanceName": "R2", "value": "10k"},
]

MOCK_DIRECTIVES = [".tran 1m"]

MOCK_LAYOUT = [
    {"instanceName": "V1", "region": "center-left", "nearby": []},
    {"instanceName": "R1", "region": "center", "nearby": [{"name": "V1", "direction": "right"}]},
    {"instanceName": "R2", "region": "center", "nearby": [{"name": "R1", "direction": "below"}]},
]

MOCK_WIRE_DESC = {
    "connections": [
        {"from": {"component": "V1", "pin": "+"}, "to": {"component": "R1", "pin": "A"}},
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "A"}},
    ],
    "grounds": [
        {"component": "V1", "pin": "-"},
        {"component": "R2", "pin": "B"},
    ],
    "labels": [],
}


def test_e2e_voltage_divider():
    dictionary = _load_dictionary()

    # Build comp_sizes with bounds
    comp_sizes = {}
    for comp_id, comp_data in dictionary["components"].items():
        bounds = comp_data.get("geometry", {}).get("bounds")
        comp_sizes[comp_id] = {
            "width": comp_data["symbol"]["width"],
            "height": comp_data["symbol"]["height"],
            "bounds": bounds,
        }

    # Step 1: Layout
    positions = compute_layout(MOCK_LAYOUT, comp_sizes)
    assert "V1" in positions
    assert "R1" in positions
    assert "R2" in positions

    # All positions on 16px grid
    for name, pos in positions.items():
        assert pos["x"] % 16 == 0, f"{name} x not snapped"
        assert pos["y"] % 16 == 0, f"{name} y not snapped"

    # Step 2: Normalize pins in wire description
    wire_desc = json.loads(json.dumps(MOCK_WIRE_DESC))  # deep copy
    for conn in wire_desc["connections"]:
        for key in ("from", "to"):
            ep = conn[key]
            comp = next(c for c in MOCK_COMPONENTS if c["instanceName"] == ep["component"])
            ep["pin"] = normalize_pin(comp["type"], ep["pin"])
    for gnd in wire_desc["grounds"]:
        comp = next(c for c in MOCK_COMPONENTS if c["instanceName"] == gnd["component"])
        gnd["pin"] = normalize_pin(comp["type"], gnd["pin"])

    # Step 3: Wire routing
    pin_defs = {}
    component_bounds = {}
    for comp_id, comp_data in dictionary["components"].items():
        pin_defs[comp_id] = comp_data.get("pins", [])
        bounds = comp_data.get("geometry", {}).get("bounds")
        if bounds:
            component_bounds[comp_id] = bounds

    comp_map = {}
    for comp in MOCK_COMPONENTS:
        name = comp["instanceName"]
        comp_map[name] = {
            "x": positions[name]["x"],
            "y": positions[name]["y"],
            "type": comp["type"],
        }

    wire_result = compute_wires(comp_map, pin_defs, wire_desc, component_bounds)
    assert len(wire_result.wires) >= 2  # at least 2 connections + 2 ground stubs
    assert len(wire_result.flags) >= 2  # 2 ground flags

    # Step 4: Build SchematicIR
    ir = SchematicIR(880, 680)
    for comp in MOCK_COMPONENTS:
        name = comp["instanceName"]
        ir.add_component(
            comp["type"], name, comp["value"],
            positions[name]["x"], positions[name]["y"], "R0",
            comp.get("value2"),
        )
    for w in wire_result.wires:
        ir.add_wire(*w)
    for f in wire_result.flags:
        ir.add_flag(f["name"], f["x"], f["y"])
    for d in MOCK_DIRECTIVES:
        ir.add_text(d, 50, 600)

    # Step 5: Generate .asc
    asc_text = generate_asc(ir)
    assert asc_text.startswith("Version 4")
    assert "SHEET 1 880 680" in asc_text
    assert "SYMBOL voltage" in asc_text
    assert "SYMBOL res" in asc_text
    assert "SYMATTR InstName V1" in asc_text
    assert "SYMATTR InstName R1" in asc_text
    assert "SYMATTR InstName R2" in asc_text
    assert "WIRE" in asc_text
    assert "FLAG" in asc_text

    # Step 6: Validate .asc
    validation = validate_asc(asc_text)
    assert validation.valid, f"Validation errors: {validation.errors}"


def test_e2e_with_vlm_style_pin_names():
    """Test that VLM-style pin names (numeric) produce the same valid output."""
    dictionary = _load_dictionary()

    comp_sizes = {}
    for comp_id, comp_data in dictionary["components"].items():
        bounds = comp_data.get("geometry", {}).get("bounds")
        comp_sizes[comp_id] = {
            "width": comp_data["symbol"]["width"],
            "height": comp_data["symbol"]["height"],
            "bounds": bounds,
        }

    positions = compute_layout(MOCK_LAYOUT, comp_sizes)

    # Use numeric pin names like a VLM would
    wire_desc = {
        "connections": [
            {"from": {"component": "V1", "pin": "1"}, "to": {"component": "R1", "pin": "1"}},
            {"from": {"component": "R1", "pin": "2"}, "to": {"component": "R2", "pin": "1"}},
        ],
        "grounds": [
            {"component": "V1", "pin": "2"},
            {"component": "R2", "pin": "2"},
        ],
        "labels": [],
    }

    # Normalize
    for conn in wire_desc["connections"]:
        for key in ("from", "to"):
            ep = conn[key]
            comp = next(c for c in MOCK_COMPONENTS if c["instanceName"] == ep["component"])
            ep["pin"] = normalize_pin(comp["type"], ep["pin"])
    for gnd in wire_desc["grounds"]:
        comp = next(c for c in MOCK_COMPONENTS if c["instanceName"] == gnd["component"])
        gnd["pin"] = normalize_pin(comp["type"], gnd["pin"])

    # Verify normalization worked
    assert wire_desc["connections"][0]["from"]["pin"] == "+"
    assert wire_desc["connections"][0]["to"]["pin"] == "A"

    pin_defs = {}
    component_bounds = {}
    for comp_id, comp_data in dictionary["components"].items():
        pin_defs[comp_id] = comp_data.get("pins", [])
        bounds = comp_data.get("geometry", {}).get("bounds")
        if bounds:
            component_bounds[comp_id] = bounds

    comp_map = {}
    for comp in MOCK_COMPONENTS:
        name = comp["instanceName"]
        comp_map[name] = {"x": positions[name]["x"], "y": positions[name]["y"], "type": comp["type"]}

    wire_result = compute_wires(comp_map, pin_defs, wire_desc, component_bounds)
    assert len(wire_result.wires) >= 2

    ir = SchematicIR(880, 680)
    for comp in MOCK_COMPONENTS:
        name = comp["instanceName"]
        ir.add_component(comp["type"], name, comp["value"],
                         positions[name]["x"], positions[name]["y"], "R0")
    for w in wire_result.wires:
        ir.add_wire(*w)
    for f in wire_result.flags:
        ir.add_flag(f["name"], f["x"], f["y"])

    asc_text = generate_asc(ir)
    validation = validate_asc(asc_text)
    assert validation.valid, f"Validation errors: {validation.errors}"
