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
    import os
    import signal

    scheduled = []
    kill_calls = []

    class _DummyHandle:
        def cancel(self):
            pass

    def fake_call_later(delay, callback, *args):
        scheduled.append((delay, callback))
        return _DummyHandle()

    def fake_kill(pid, sig):
        kill_calls.append((pid, sig))

    # Replace call_later on the running loop with a recording stub.
    real_loop = asyncio.get_event_loop()
    monkeypatch.setattr(real_loop, "call_later", fake_call_later)

    # Replace os.kill so that even if the callback IS invoked, no real
    # signal is sent.
    monkeypatch.setattr(os, "kill", fake_kill)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/shutdown")

    assert resp.status_code == 200
    assert resp.json() == {"shutting_down": True}
    assert len(scheduled) == 1

    delay, callback = scheduled[0]
    assert delay == 0.1

    # Invoke the captured callback and verify it sends SIGTERM to this process.
    callback()
    assert kill_calls == [(os.getpid(), signal.SIGTERM)]
