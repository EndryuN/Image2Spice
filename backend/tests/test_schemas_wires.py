from services.schemas import WiresResponse


def test_wires_response_accepts_empty_new_fields():
    resp = WiresResponse.model_validate({
        "connections": [],
        "grounds": [],
        "labels": [],
    })
    assert resp.wire_paths == []
    assert resp.buses == []


def test_wires_response_parses_wire_paths():
    resp = WiresResponse.model_validate({
        "connections": [],
        "grounds": [],
        "labels": [],
        "wire_paths": [
            {"from_pin": "R1.A", "to_pin": "Q1.C", "path": "L_horizontal_first"},
        ],
    })
    assert len(resp.wire_paths) == 1
    assert resp.wire_paths[0].from_pin == "R1.A"
    assert resp.wire_paths[0].to_pin == "Q1.C"
    assert resp.wire_paths[0].path == "L_horizontal_first"


def test_wires_response_parses_buses():
    resp = WiresResponse.model_validate({
        "connections": [],
        "grounds": [],
        "labels": [],
        "buses": [
            {"orientation": "horizontal", "y_pct": 40, "connects": ["R1.B", "R2.B", "C1.A"]},
        ],
    })
    assert len(resp.buses) == 1
    assert resp.buses[0].orientation == "horizontal"
    assert resp.buses[0].y_pct == 40
    assert resp.buses[0].connects == ["R1.B", "R2.B", "C1.A"]


def test_wires_response_roundtrip_dump_keeps_alias_keys():
    resp = WiresResponse.model_validate({
        "connections": [],
        "grounds": [],
        "labels": [],
        "wire_paths": [{"from_pin": "R1.A", "to_pin": "R2.A", "path": "direct_horizontal"}],
    })
    dumped = resp.model_dump(by_alias=True)
    assert "wire_paths" in dumped
    assert dumped["wire_paths"][0]["from_pin"] == "R1.A"
