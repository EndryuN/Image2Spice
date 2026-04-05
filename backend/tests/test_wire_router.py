import pytest
from services.wire_router import compute_wires, WireResult


def test_simple_connection():
    components = {
        "R1": {"x": 100, "y": 100, "type": "res"},
        "R2": {"x": 300, "y": 100, "type": "res"},
    }
    pin_defs = {
        "res": [
            {"name": "A", "x": 16, "y": 16, "spiceOrder": 1},
            {"name": "B", "x": 16, "y": 96, "spiceOrder": 2},
        ],
    }
    connections_data = {
        "connections": [
            {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "A"}}
        ],
        "grounds": [],
        "labels": [],
    }
    result = compute_wires(components, pin_defs, connections_data)
    assert len(result.wires) >= 1
    assert result.wires[0][0] == 116  # R1.x + pin.x = 100+16
    assert result.wires[0][1] == 196  # R1.y + pin.y = 100+96


def test_ground_connection():
    components = {
        "V1": {"x": 100, "y": 100, "type": "voltage"},
    }
    pin_defs = {
        "voltage": [
            {"name": "+", "x": 0, "y": 16, "spiceOrder": 1},
            {"name": "-", "x": 0, "y": 96, "spiceOrder": 2},
        ],
    }
    connections_data = {
        "connections": [],
        "grounds": [{"component": "V1", "pin": "-"}],
        "labels": [],
    }
    result = compute_wires(components, pin_defs, connections_data)
    assert len(result.flags) == 1
    assert result.flags[0]["name"] == "0"
    assert len(result.wires) == 1  # stub wire


def test_net_label():
    components = {
        "U1": {"x": 200, "y": 200, "type": "opamp2"},
    }
    pin_defs = {
        "opamp2": [
            {"name": "In+", "x": -32, "y": 80, "spiceOrder": 1},
            {"name": "In-", "x": -32, "y": 48, "spiceOrder": 2},
            {"name": "V+", "x": 0, "y": 32, "spiceOrder": 3},
            {"name": "V-", "x": 0, "y": 96, "spiceOrder": 4},
            {"name": "OUT", "x": 32, "y": 64, "spiceOrder": 5},
        ],
    }
    connections_data = {
        "connections": [],
        "grounds": [],
        "labels": [{"component": "U1", "pin": "OUT", "label": "OUT"}],
    }
    result = compute_wires(components, pin_defs, connections_data)
    assert len(result.flags) >= 1
    assert result.flags[0]["name"] == "OUT"


def test_l_route_wires():
    components = {
        "R1": {"x": 100, "y": 100, "type": "res"},
        "R2": {"x": 300, "y": 300, "type": "res"},
    }
    pin_defs = {
        "res": [
            {"name": "A", "x": 16, "y": 16, "spiceOrder": 1},
            {"name": "B", "x": 16, "y": 96, "spiceOrder": 2},
        ],
    }
    connections_data = {
        "connections": [
            {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "A"}}
        ],
        "grounds": [],
        "labels": [],
    }
    result = compute_wires(components, pin_defs, connections_data)
    assert len(result.wires) == 2  # L-route needs 2 segments


def test_pin_normalization_in_connections():
    """Wire router should work when _find_pin receives canonical names."""
    components = {
        "R1": {"x": 100, "y": 100, "type": "res"},
        "V1": {"x": 100, "y": 300, "type": "voltage"},
    }
    pin_defs = {
        "res": [
            {"name": "A", "x": 16, "y": 16, "spiceOrder": 1},
            {"name": "B", "x": 16, "y": 96, "spiceOrder": 2},
        ],
        "voltage": [
            {"name": "+", "x": 0, "y": 16, "spiceOrder": 1},
            {"name": "-", "x": 0, "y": 96, "spiceOrder": 2},
        ],
    }
    connections_data = {
        "connections": [
            {"from": {"component": "R1", "pin": "B"}, "to": {"component": "V1", "pin": "+"}}
        ],
        "grounds": [],
        "labels": [],
    }
    result = compute_wires(components, pin_defs, connections_data)
    assert len(result.wires) >= 1


def test_ground_with_stub_wire():
    """Ground flags should have a short wire stub."""
    components = {
        "V1": {"x": 100, "y": 100, "type": "voltage"},
    }
    pin_defs = {
        "voltage": [
            {"name": "+", "x": 0, "y": 16, "spiceOrder": 1},
            {"name": "-", "x": 0, "y": 96, "spiceOrder": 2},
        ],
    }
    connections_data = {
        "connections": [],
        "grounds": [{"component": "V1", "pin": "-"}],
        "labels": [],
    }
    result = compute_wires(components, pin_defs, connections_data)
    assert len(result.flags) == 1
    assert result.flags[0]["name"] == "0"
    pin_y = 100 + 96
    assert result.flags[0]["y"] == pin_y + 32
    assert len(result.wires) == 1
    assert result.wires[0] == (100, pin_y, 100, pin_y + 32)


def test_dual_l_route_picks_best():
    """When both L-routes are available, the router should pick one without crashing."""
    components = {
        "R1": {"x": 100, "y": 100, "type": "res"},
        "R2": {"x": 400, "y": 400, "type": "res"},
    }
    pin_defs = {
        "res": [
            {"name": "A", "x": 16, "y": 16, "spiceOrder": 1},
            {"name": "B", "x": 16, "y": 96, "spiceOrder": 2},
        ],
    }
    connections_data = {
        "connections": [
            {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "A"}}
        ],
        "grounds": [],
        "labels": [],
    }
    bounds = {
        "res": [0, 16, 32, 96],
    }
    result = compute_wires(components, pin_defs, connections_data, bounds)
    assert len(result.wires) == 2


def test_obstacle_avoidance():
    """Router should avoid a component bounding box placed in the L-route path."""
    components = {
        "R1": {"x": 100, "y": 100, "type": "res"},
        "R2": {"x": 400, "y": 100, "type": "res"},
        "BLOCKER": {"x": 250, "y": 100, "type": "res"},
    }
    pin_defs = {
        "res": [
            {"name": "A", "x": 16, "y": 16, "spiceOrder": 1},
            {"name": "B", "x": 16, "y": 96, "spiceOrder": 2},
        ],
    }
    connections_data = {
        "connections": [
            {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "A"}}
        ],
        "grounds": [],
        "labels": [],
    }
    bounds = {
        "res": [0, 16, 32, 96],
    }
    result = compute_wires(components, pin_defs, connections_data, bounds)
    assert len(result.wires) >= 2
