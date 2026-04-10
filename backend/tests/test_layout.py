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


COMPONENT_BOUNDS = {
    "res": [0, 16, 32, 96],
    "voltage": [-32, 16, 32, 96],
    "opamp2": [-32, 32, 32, 96],
    "cap": [0, 0, 32, 64],
}


def test_same_region_no_overlap():
    """Three components in 'center' must not overlap."""
    layout_desc = [
        {"instanceName": "R1", "region": "center", "nearby": []},
        {"instanceName": "R2", "region": "center", "nearby": []},
        {"instanceName": "R3", "region": "center", "nearby": []},
    ]
    sizes = {k: {"width": b[2] - b[0], "height": b[3] - b[1], "bounds": b}
             for k, b in COMPONENT_BOUNDS.items()}
    result = compute_layout(layout_desc, sizes, 880, 680)
    coords = [(result[n]["x"], result[n]["y"]) for n in ["R1", "R2", "R3"]]
    # All three must be at distinct positions
    assert len(set(coords)) == 3


def test_collision_resolution_minimum_spacing():
    """Components placed at the same spot must be pushed apart by at least 96px."""
    layout_desc = [
        {"instanceName": "R1", "region": "center", "nearby": []},
        {"instanceName": "R2", "region": "center", "nearby": []},
    ]
    sizes = {k: {"width": b[2] - b[0], "height": b[3] - b[1], "bounds": b}
             for k, b in COMPONENT_BOUNDS.items()}
    result = compute_layout(layout_desc, sizes, 880, 680)
    r1, r2 = result["R1"], result["R2"]
    dx = abs(r1["x"] - r2["x"])
    dy = abs(r1["y"] - r2["y"])
    # Must be separated in at least one axis by >= 96
    assert dx >= 96 or dy >= 96


def test_clamp_within_bounds():
    """Even with collision pushes, all positions stay within sheet bounds."""
    layout_desc = [
        {"instanceName": f"R{i}", "region": "top-left", "nearby": []}
        for i in range(6)
    ]
    sizes = {"res": {"width": 32, "height": 80, "bounds": [0, 16, 32, 96]}}
    result = compute_layout(layout_desc, sizes, 880, 680)
    for name, pos in result.items():
        assert 32 <= pos["x"] <= 848, f"{name} x={pos['x']} out of bounds"
        assert 32 <= pos["y"] <= 648, f"{name} y={pos['y']} out of bounds"


def test_compaction_toward_center():
    """Components spread across far corners should be pulled inward."""
    layout_desc = [
        {"instanceName": "R1", "region": "top-left", "nearby": []},
        {"instanceName": "R2", "region": "bottom-right", "nearby": []},
    ]
    sizes = {"res": {"width": 32, "height": 80, "bounds": [0, 16, 32, 96]}}
    result = compute_layout(layout_desc, sizes, 880, 680)
    # Centroid should be closer to sheet center (440, 340) than corners
    cx = (result["R1"]["x"] + result["R2"]["x"]) / 2
    cy = (result["R1"]["y"] + result["R2"]["y"]) / 2
    assert 200 < cx < 680
    assert 150 < cy < 530
