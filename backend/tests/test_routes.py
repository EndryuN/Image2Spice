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
