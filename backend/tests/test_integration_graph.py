"""Integration test: circuit 04 (parallel resistors) through the full graph pipeline."""
import pytest
from services.circuit_graph import CircuitGraph
from services.layout import compute_layout_from_graph
from services.wire_router import route_nets
from services.schematic_builder import build_asc

DICTIONARY = {
    "components": {
        "res": {
            "pins": [
                {"name": "A", "x": 16, "y": 16, "spiceOrder": 1},
                {"name": "B", "x": 16, "y": 96, "spiceOrder": 2},
            ],
            "symbol": {"width": 32, "height": 80, "svgPath": ""},
            "windows": [
                {"index": 0, "x": 36, "y": 40, "justification": "Left", "fontSize": 2},
                {"index": 3, "x": 36, "y": 76, "justification": "Left", "fontSize": 2},
            ],
        },
        "voltage": {
            "pins": [
                {"name": "+", "x": 0, "y": 16, "spiceOrder": 1},
                {"name": "-", "x": 0, "y": 96, "spiceOrder": 2},
            ],
            "symbol": {"width": 64, "height": 80, "svgPath": ""},
            "windows": [
                {"index": 0, "x": 24, "y": 16, "justification": "Left", "fontSize": 2},
                {"index": 3, "x": 24, "y": 96, "justification": "Left", "fontSize": 2},
            ],
        },
    }
}


def test_circuit04_full_pipeline():
    analysis = {
        "components": [
            {"name": "V1", "type": "voltage", "value": "30V"},
            {"name": "R1", "type": "res", "value": "2"},
            {"name": "R2", "type": "res", "value": "8"},
            {"name": "R3", "type": "res", "value": "1"},
            {"name": "V2", "type": "voltage", "value": "10V"},
        ],
        "connections": [
            {"from": "V1.+", "to": "R1.A"},
            {"from": "R1.A", "to": "R2.A"},
            {"from": "R2.A", "to": "R3.A"},
            {"from": "R3.A", "to": "V2.+"},
            {"from": "V1.-", "to": "R1.B"},
            {"from": "R1.B", "to": "R2.B"},
            {"from": "R2.B", "to": "R3.B"},
            {"from": "R3.B", "to": "V2.-"},
        ],
        "grounds": [],
        "labels": [],
    }
    asc = build_asc(analysis, DICTIONARY)
    lines = asc.split("\n")

    assert lines[0] == "Version 4"
    assert lines[1].startswith("SHEET 1")

    symbol_lines = [l for l in lines if l.startswith("SYMBOL")]
    assert len(symbol_lines) == 5

    window_lines = [l for l in lines if l.startswith("WINDOW")]
    assert len(window_lines) >= 10

    wire_lines = [l for l in lines if l.startswith("WIRE")]
    assert len(wire_lines) >= 4

    for wl in wire_lines:
        parts = wl.split()
        x1, y1, x2, y2 = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
        assert not (x1 == x2 and y1 == y2), f"Zero-length wire: {wl}"
        assert x1 == x2 or y1 == y2, f"Diagonal wire: {wl}"


def test_circuit04_resistors_same_tier():
    graph = CircuitGraph(DICTIONARY)
    graph.add_components([
        {"name": "V1", "type": "voltage", "value": "30V"},
        {"name": "R1", "type": "res", "value": "2"},
        {"name": "R2", "type": "res", "value": "8"},
        {"name": "R3", "type": "res", "value": "1"},
        {"name": "V2", "type": "voltage", "value": "10V"},
    ])
    graph.build_nets([
        {"from": {"component": "V1", "pin": "+"}, "to": {"component": "R1", "pin": "A"}},
        {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R2", "pin": "A"}},
        {"from": {"component": "R2", "pin": "A"}, "to": {"component": "R3", "pin": "A"}},
        {"from": {"component": "R3", "pin": "A"}, "to": {"component": "V2", "pin": "+"}},
        {"from": {"component": "V1", "pin": "-"}, "to": {"component": "R1", "pin": "B"}},
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "B"}},
        {"from": {"component": "R2", "pin": "B"}, "to": {"component": "R3", "pin": "B"}},
        {"from": {"component": "R3", "pin": "B"}, "to": {"component": "V2", "pin": "-"}},
    ], [], [])
    graph.assign_tiers()
    graph.resolve_orientations()
    positions, _ = compute_layout_from_graph(graph)

    r1y = positions["R1"][1]
    r2y = positions["R2"][1]
    r3y = positions["R3"][1]
    assert r1y == r2y == r3y


def test_circuit04_no_self_shorts():
    graph = CircuitGraph(DICTIONARY)
    graph.add_components([
        {"name": "V1", "type": "voltage", "value": "30V"},
        {"name": "R1", "type": "res", "value": "2"},
        {"name": "V2", "type": "voltage", "value": "10V"},
    ])
    graph.build_nets([
        {"from": {"component": "V1", "pin": "+"}, "to": {"component": "R1", "pin": "A"}},
        {"from": {"component": "R1", "pin": "A"}, "to": {"component": "V2", "pin": "+"}},
        {"from": {"component": "V1", "pin": "-"}, "to": {"component": "R1", "pin": "B"}},
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "V2", "pin": "-"}},
    ], [], [])
    graph.assign_tiers()
    graph.resolve_orientations()
    compute_layout_from_graph(graph)
    result = route_nets(graph)

    for w in result.wires:
        assert not (w[0] == w[2] and w[1] == w[3]), f"Zero-length wire: {w}"
