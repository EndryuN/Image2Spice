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
