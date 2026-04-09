import pytest
from services.layout import compute_layout

COMPONENT_SIZES = {
    "res": {"width": 32, "height": 80},
    "voltage": {"width": 48, "height": 96},
    "opamp2": {"width": 64, "height": 64},
}


def test_single_component_center():
    layout_desc = [
        {"instanceName": "U1", "region": "center", "nearby": []}
    ]
    result = compute_layout(layout_desc, COMPONENT_SIZES, 880, 680)
    assert result["U1"]["x"] == 432
    assert result["U1"]["y"] == 336


def test_two_components_regions():
    layout_desc = [
        {"instanceName": "R1", "region": "top-left", "nearby": []},
        {"instanceName": "V1", "region": "bottom-right", "nearby": []},
    ]
    result = compute_layout(layout_desc, COMPONENT_SIZES, 880, 680)
    assert result["R1"]["x"] < result["V1"]["x"]
    assert result["R1"]["y"] < result["V1"]["y"]


def test_nearby_above():
    layout_desc = [
        {"instanceName": "U1", "region": "center", "nearby": []},
        {"instanceName": "R1", "region": "center", "nearby": [
            {"name": "U1", "direction": "below"}
        ]},
    ]
    result = compute_layout(layout_desc, COMPONENT_SIZES, 880, 680)
    assert result["R1"]["y"] < result["U1"]["y"]


def test_nearby_right():
    layout_desc = [
        {"instanceName": "U1", "region": "center", "nearby": []},
        {"instanceName": "V1", "region": "center", "nearby": [
            {"name": "U1", "direction": "left"}
        ]},
    ]
    result = compute_layout(layout_desc, COMPONENT_SIZES, 880, 680)
    assert result["V1"]["x"] > result["U1"]["x"]


def test_grid_snap():
    layout_desc = [
        {"instanceName": "R1", "region": "center", "nearby": []}
    ]
    result = compute_layout(layout_desc, COMPONENT_SIZES, 880, 680)
    assert result["R1"]["x"] % 16 == 0
    assert result["R1"]["y"] % 16 == 0
