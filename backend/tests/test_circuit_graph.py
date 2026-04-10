import pytest
from services.circuit_graph import CircuitGraph


SAMPLE_DICTIONARY = {
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

SAMPLE_COMPONENTS = [
    {"name": "V1", "type": "voltage", "value": "30V"},
    {"name": "R1", "type": "res", "value": "2"},
    {"name": "R2", "type": "res", "value": "8"},
    {"name": "R3", "type": "res", "value": "1"},
    {"name": "V2", "type": "voltage", "value": "10V"},
]


def test_build_components():
    graph = CircuitGraph(SAMPLE_DICTIONARY)
    graph.add_components(SAMPLE_COMPONENTS)
    assert len(graph.components) == 5
    assert graph.components["V1"].type == "voltage"
    assert graph.components["V1"].value == "30V"
    assert graph.components["R1"].pins == SAMPLE_DICTIONARY["components"]["res"]["pins"]
    assert graph.components["V2"].symbol_size == (64, 80)


def test_add_component_unknown_type_uses_defaults():
    graph = CircuitGraph(SAMPLE_DICTIONARY)
    graph.add_components([{"name": "X1", "type": "unknown_type", "value": "1"}])
    assert graph.components["X1"].type == "unknown_type"
    assert graph.components["X1"].pins == []
    assert graph.components["X1"].symbol_size == (64, 80)  # default


SAMPLE_CONNECTIONS = [
    {"from": {"component": "V1", "pin": "+"}, "to": {"component": "R1", "pin": "A"}},
    {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R2", "pin": "A"}},
    {"from": {"component": "R2", "pin": "A"}, "to": {"component": "R3", "pin": "A"}},
    {"from": {"component": "R3", "pin": "A"}, "to": {"component": "V2", "pin": "+"}},
    {"from": {"component": "V1", "pin": "-"}, "to": {"component": "R1", "pin": "B"}},
    {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "B"}},
    {"from": {"component": "R2", "pin": "B"}, "to": {"component": "R3", "pin": "B"}},
    {"from": {"component": "R3", "pin": "B"}, "to": {"component": "V2", "pin": "-"}},
]

SAMPLE_GROUNDS: list[dict] = []
SAMPLE_LABELS: list[dict] = []


def test_build_nets_union_find():
    graph = CircuitGraph(SAMPLE_DICTIONARY)
    graph.add_components(SAMPLE_COMPONENTS)
    graph.build_nets(SAMPLE_CONNECTIONS, SAMPLE_GROUNDS, SAMPLE_LABELS)
    assert len(graph.nets) == 2
    for net in graph.nets.values():
        assert len(net.pins) == 5


def test_build_nets_with_ground():
    graph = CircuitGraph(SAMPLE_DICTIONARY)
    graph.add_components(SAMPLE_COMPONENTS)
    grounds = [{"component": "V1", "pin": "-"}]
    graph.build_nets(SAMPLE_CONNECTIONS, grounds, [])
    v1_minus_net = None
    for net in graph.nets.values():
        if ("V1", "-") in net.pins:
            v1_minus_net = net
            break
    assert v1_minus_net is not None
    assert v1_minus_net.name == "0"


def test_build_nets_with_label():
    graph = CircuitGraph(SAMPLE_DICTIONARY)
    graph.add_components(SAMPLE_COMPONENTS)
    labels = [{"component": "V1", "pin": "+", "label": "VCC"}]
    graph.build_nets(SAMPLE_CONNECTIONS, [], labels)
    v1_plus_net = None
    for net in graph.nets.values():
        if ("V1", "+") in net.pins:
            v1_plus_net = net
            break
    assert v1_plus_net is not None
    assert v1_plus_net.name == "VCC"
