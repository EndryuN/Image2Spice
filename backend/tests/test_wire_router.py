import pytest
from services.circuit_graph import CircuitGraph
from services.wire_router import route_nets, WireResult

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


def _make_routed_graph(comps, conns, grounds=None, labels=None):
    from services.layout import compute_layout_from_graph
    g = CircuitGraph(DICTIONARY)
    g.add_components(comps)
    g.build_nets(conns, grounds or [], labels or [])
    g.assign_tiers()
    g.resolve_orientations()
    compute_layout_from_graph(g)
    return g


def test_two_pin_net_produces_wire():
    comps = [
        {"name": "R1", "type": "res", "value": "1k"},
        {"name": "R2", "type": "res", "value": "2k"},
    ]
    conns = [
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "A"}},
    ]
    graph = _make_routed_graph(comps, conns)
    result = route_nets(graph)
    assert len(result.wires) >= 1


def test_self_short_rejected():
    comps = [{"name": "R1", "type": "res", "value": "1k"}]
    conns = [
        {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R1", "pin": "B"}},
    ]
    graph = _make_routed_graph(comps, conns)
    result = route_nets(graph)
    assert len(result.wires) == 0


def test_bus_routing_collinear_pins():
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
    graph = _make_routed_graph(comps, conns)
    result = route_nets(graph)
    assert len(result.wires) >= 2
    for w in result.wires:
        assert w[0] == w[2] or w[1] == w[3], f"Diagonal wire: {w}"


def test_ground_flag():
    comps = [{"name": "V1", "type": "voltage", "value": "5"}]
    grounds = [{"component": "V1", "pin": "-"}]
    graph = _make_routed_graph(comps, [], grounds=grounds)
    result = route_nets(graph)
    assert len(result.flags) == 1
    assert result.flags[0]["name"] == "0"


def test_no_duplicate_wires():
    comps = [
        {"name": "R1", "type": "res", "value": "1k"},
        {"name": "R2", "type": "res", "value": "2k"},
    ]
    conns = [
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "A"}},
    ]
    graph = _make_routed_graph(comps, conns)
    result = route_nets(graph)
    wire_set = set()
    for w in result.wires:
        normalized = (min(w[0], w[2]), min(w[1], w[3]), max(w[0], w[2]), max(w[1], w[3]))
        assert normalized not in wire_set, f"Duplicate wire: {w}"
        wire_set.add(normalized)
