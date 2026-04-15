"""Tests for /api/wizard/wires handler migration to route_with_paths."""
import json
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@pytest.fixture
def mock_wires_desc_legacy():
    """VLM response with NO wire_paths/buses — backward compat check."""
    return {
        "connections": [
            {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R2", "pin": "A"}},
        ],
        "grounds": [],
        "labels": [],
        "wire_paths": [],
        "buses": [],
    }


@pytest.fixture
def mock_wires_desc_with_paths():
    """VLM response WITH wire_paths — exercises the new router."""
    return {
        "connections": [
            {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R2", "pin": "A"}},
        ],
        "grounds": [],
        "labels": [],
        "wire_paths": [
            {"from_pin": "R1.A", "to_pin": "R2.A", "path": "L_vertical_first"},
        ],
        "buses": [],
    }


@pytest.fixture
def components_payload():
    return [
        {"instanceName": "R1", "type": "res", "value": "1k"},
        {"instanceName": "R2", "type": "res", "value": "2k"},
    ]


@pytest.fixture
def positions_payload():
    return {
        "R1": {"x": 64, "y": 64, "rotation": "R0"},
        "R2": {"x": 256, "y": 128, "rotation": "R0"},
    }


def _post(mock_desc, components, positions):
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
        b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe"
        b"\x02\xfe\xa3V\x1f\x8f\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with patch("api.wizard_routes.describe_wires", new=AsyncMock(return_value=mock_desc)):
        return client.post(
            "/api/wizard/wires",
            files={"file": ("test.png", png, "image/png")},
            data={
                "components_json": json.dumps(components),
                "positions_json": json.dumps(positions),
                "provider_json": "{}",
            },
        )


def test_wires_endpoint_legacy_payload_still_works(
    mock_wires_desc_legacy, components_payload, positions_payload,
):
    resp = _post(mock_wires_desc_legacy, components_payload, positions_payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "wires" in body
    assert len(body["wires"]) >= 1, "Expected at least one wire between R1 and R2"


def test_wires_endpoint_honors_wire_path_hint(
    mock_wires_desc_with_paths, components_payload, positions_payload,
):
    resp = _post(mock_wires_desc_with_paths, components_payload, positions_payload)
    assert resp.status_code == 200, resp.text
    wires = resp.json()["wires"]

    # L_vertical_first: the horizontal leg sits at the BOTTOM component's y (R2, y=128),
    # not the TOP component's y (R1, y=64).  Horizontal-first would place it at R1's y.
    horiz_segments = [w for w in wires if w["y1"] == w["y2"]]
    assert horiz_segments, f"Expected a horizontal segment; got {wires}"
    horiz_y = horiz_segments[0]["y1"]
    # R1 at y=64, R2 at y=128 -> midpoint = 96.  L_vertical_first corner is closer to R2.
    assert horiz_y > 96, (
        f"Expected horizontal leg near R2's y (128), got {horiz_y} - "
        f"looks like L_horizontal_first (corner at R1's y), hint was not honored"
    )
