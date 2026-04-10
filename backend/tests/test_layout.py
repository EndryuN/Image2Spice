import pytest
from services.circuit_graph import CircuitGraph
from services.layout import compute_layout_from_graph

DICTIONARY = {
    "components": {
        "res": {
            "pins": [
                {"name": "A", "x": 16, "y": 16, "spiceOrder": 1},
                {"name": "B", "x": 16, "y": 96, "spiceOrder": 2},
            ],
            "symbol": {"width": 32, "height": 80, "svgPath": ""},
        },
        "voltage": {
            "pins": [
                {"name": "+", "x": 0, "y": 16, "spiceOrder": 1},
                {"name": "-", "x": 0, "y": 96, "spiceOrder": 2},
            ],
            "symbol": {"width": 64, "height": 80, "svgPath": ""},
        },
    }
}


def _make_graph(comps, conns, grounds=None, labels=None):
    g = CircuitGraph(DICTIONARY)
    g.add_components(comps)
    g.build_nets(conns, grounds or [], labels or [])
    g.assign_tiers()
    g.resolve_orientations()
    return g


def test_canvas_auto_sizing():
    comps = [
        {"name": "V1", "type": "voltage", "value": "30V"},
        {"name": "R1", "type": "res", "value": "2"},
        {"name": "R2", "type": "res", "value": "8"},
        {"name": "R3", "type": "res", "value": "1"},
        {"name": "V2", "type": "voltage", "value": "10V"},
    ]
    conns = [
        {"from": {"component": "V1", "pin": "+"}, "to": {"component": "R1", "pin": "A"}},
        {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R2", "pin": "A"}},
        {"from": {"component": "R2", "pin": "A"}, "to": {"component": "R3", "pin": "A"}},
        {"from": {"component": "R3", "pin": "A"}, "to": {"component": "V2", "pin": "+"}},
        {"from": {"component": "V1", "pin": "-"}, "to": {"component": "R1", "pin": "B"}},
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "B"}},
        {"from": {"component": "R2", "pin": "B"}, "to": {"component": "R3", "pin": "B"}},
        {"from": {"component": "R3", "pin": "B"}, "to": {"component": "V2", "pin": "-"}},
    ]
    graph = _make_graph(comps, conns)
    positions, sheet = compute_layout_from_graph(graph)
    assert sheet[0] >= 800
    assert sheet[1] >= 600


def test_grid_snap():
    comps = [{"name": "R1", "type": "res", "value": "1k"}]
    graph = _make_graph(comps, [])
    positions, sheet = compute_layout_from_graph(graph)
    assert positions["R1"][0] % 16 == 0
    assert positions["R1"][1] % 16 == 0


def test_minimum_spacing():
    comps = [
        {"name": "R1", "type": "res", "value": "1k"},
        {"name": "R2", "type": "res", "value": "2k"},
        {"name": "R3", "type": "res", "value": "3k"},
    ]
    conns = [
        {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R2", "pin": "A"}},
        {"from": {"component": "R2", "pin": "A"}, "to": {"component": "R3", "pin": "A"}},
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "B"}},
        {"from": {"component": "R2", "pin": "B"}, "to": {"component": "R3", "pin": "B"}},
    ]
    graph = _make_graph(comps, conns)
    positions, sheet = compute_layout_from_graph(graph)
    names = list(positions.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            xi, yi = positions[names[i]]
            xj, yj = positions[names[j]]
            dist = abs(xi - xj) + abs(yi - yj)
            assert dist >= 128, f"{names[i]} and {names[j]} too close: {dist}"


def test_parallel_components_same_y():
    comps = [
        {"name": "R1", "type": "res", "value": "1k"},
        {"name": "R2", "type": "res", "value": "2k"},
    ]
    conns = [
        {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R2", "pin": "A"}},
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "B"}},
    ]
    graph = _make_graph(comps, conns)
    positions, _ = compute_layout_from_graph(graph)
    assert positions["R1"][1] == positions["R2"][1]
