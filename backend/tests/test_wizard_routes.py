import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.mark.asyncio
async def test_identify_rejects_non_image():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/wizard/identify",
            files={"file": ("test.txt", b"not an image", "text/plain")},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_directives_rejects_non_image():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/wizard/directives",
            files={"file": ("test.txt", b"not an image", "text/plain")},
        )
    assert resp.status_code == 400
