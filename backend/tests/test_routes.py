import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_dictionary():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dictionary")
    assert resp.status_code == 200
    data = resp.json()
    assert "res" in data["components"]
    assert "opamp2" in data["components"]
    assert ".tran" in data["directives"]["directives"]


@pytest.mark.asyncio
async def test_validate_valid():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/validate",
            json={"asc": "Version 4\nSHEET 1 880 680\n"},
        )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


@pytest.mark.asyncio
async def test_validate_invalid():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/validate",
            json={"asc": "SHEET 1 880 680\n"},
        )
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


@pytest.mark.asyncio
async def test_refine():
    ir_data = {
        "sheet": {"width": 880, "height": 680},
        "components": [
            {
                "type": "res",
                "instanceName": "R1",
                "value": "1k",
                "position": {"x": 100, "y": 100},
                "rotation": "R0",
            }
        ],
        "wires": [],
        "flags": [],
        "text": [],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/refine", json={"ir": ir_data})
    assert resp.status_code == 200
    assert "SYMBOL res 100 100 R0" in resp.json()["asc"]
    assert resp.json()["validation"]["valid"] is True


@pytest.mark.asyncio
async def test_shutdown_returns_shutting_down(monkeypatch):
    """POST /api/shutdown returns the shutdown signal and schedules SIGTERM."""
    import asyncio
    import signal

    scheduled = []

    def fake_call_later(delay, callback):
        scheduled.append((delay, callback))

    # Get the real event loop once before mocking, to avoid issues with httpx needing it
    real_loop = asyncio.get_event_loop()

    # Create a wrapper that delegates to the real loop but captures call_later
    original_call_later = real_loop.call_later

    def mock_call_later(delay, callback):
        scheduled.append((delay, callback))
        return original_call_later(delay, callback)

    monkeypatch.setattr(real_loop, "call_later", mock_call_later)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/shutdown")

    assert resp.status_code == 200
    assert resp.json() == {"shutting_down": True}
    assert len(scheduled) == 1
    delay, _callback = scheduled[0]
    assert delay == 0.1
