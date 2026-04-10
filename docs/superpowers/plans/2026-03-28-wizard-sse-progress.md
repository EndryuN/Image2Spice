# Wizard SSE Progress Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the silent "Loading..." in the Generate Wizard with real-time SSE progress events streamed from the backend, plus an activity log panel inside the wizard modal and a pre-flight Ollama health check.

**Architecture:** Add `chat_with_vision_stream()` to the Ollama client (async generator yielding lifecycle phases). Add streaming variants of each vision function that yield SSE event dicts. Add 4 streaming endpoints + 1 health check endpoint. Frontend consumes SSE via `fetch` + `ReadableStream` in a `useWizardStream` hook, rendering a log panel inside the wizard.

**Tech Stack:** Python 3.10+, FastAPI StreamingResponse, httpx streaming, React 19, TypeScript, native fetch ReadableStream

---

## File Map

```
Modified files:
  backend/services/ollama_client.py     -- add chat_with_vision_stream()
  backend/services/vision.py            -- add 4 streaming vision functions
  backend/api/wizard_routes.py          -- add 4 streaming endpoints + health check
  backend/tests/test_wizard_routes.py   -- add streaming + health check tests
  frontend/src/components/GenerateWizard.tsx -- use stream hook, add log panel, pre-flight check

New files:
  frontend/src/hooks/useWizardStream.ts -- SSE consumer hook
```

---

### Task 1: Streaming Ollama Client

**Files:**
- Modify: `backend/services/ollama_client.py`
- Test: `backend/tests/test_ollama_stream.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_ollama_stream.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.ollama_client import chat_with_vision_stream


@pytest.mark.asyncio
async def test_stream_yields_sending_then_generating_then_done():
    """chat_with_vision_stream yields phase events then done_raw."""

    # Simulate Ollama streaming response: two chunks
    chunk1 = b'{"message":{"content":"hel"},"done":false}\n'
    chunk2 = b'{"message":{"content":"lo"},"done":true}\n'

    async def fake_aiter(self):
        for line in [chunk1, chunk2]:
            yield line

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.aiter_lines = lambda: fake_aiter(mock_response)
    mock_response.aclose = AsyncMock()
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_client = AsyncMock()
    mock_client.stream = MagicMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("services.ollama_client.httpx.AsyncClient", return_value=mock_client):
        events = []
        async for event in chat_with_vision_stream("model", "sys", "usr", b"img"):
            events.append(event)

    assert events[0]["phase"] == "sending"
    assert events[1]["phase"] == "generating"
    assert events[2]["phase"] == "done_raw"
    assert events[2]["content"] == "hello"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend && python -m pytest tests/test_ollama_stream.py -v
```
Expected: FAIL with `ImportError` (function doesn't exist yet)

- [ ] **Step 3: Implement chat_with_vision_stream**

Add to `backend/services/ollama_client.py` after the existing `chat_with_vision` function:

```python
from collections.abc import AsyncGenerator


async def chat_with_vision_stream(
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_bytes: bytes,
) -> AsyncGenerator[dict, None]:
    """Streaming variant that yields lifecycle phase events."""
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": user_prompt,
                "images": [image_b64],
            },
        ],
        "stream": True,
        "options": {"temperature": 0.1},
    }

    yield {"phase": "sending", "message": "Sending to Ollama..."}

    import json as _json
    first_token = True
    accumulated = []

    async with httpx.AsyncClient(timeout=600.0) as client:
        async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                chunk = _json.loads(line)
                content = chunk.get("message", {}).get("content", "")
                if content:
                    if first_token:
                        yield {"phase": "generating", "message": "AI is analyzing..."}
                        first_token = False
                    accumulated.append(content)

    yield {"phase": "done_raw", "content": "".join(accumulated)}
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd backend && python -m pytest tests/test_ollama_stream.py -v
```
Expected: PASS

- [ ] **Step 5: Run existing tests to verify nothing broke**

Run:
```bash
cd backend && python -m pytest tests/ -v
```
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/ollama_client.py backend/tests/test_ollama_stream.py
git commit -m "feat: add streaming Ollama client for SSE progress"
```

---

### Task 2: Streaming Vision Functions

**Files:**
- Modify: `backend/services/vision.py`
- Test: `backend/tests/test_vision_stream.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_vision_stream.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock
from services.vision import identify_components_stream


async def _fake_ollama_stream(*args, **kwargs):
    yield {"phase": "sending", "message": "Sending to Ollama..."}
    yield {"phase": "generating", "message": "AI is analyzing..."}
    yield {"phase": "done_raw", "content": '[{"type":"res","instanceName":"R1","value":"1k"}]'}


@pytest.mark.asyncio
async def test_identify_stream_yields_phases_then_done():
    with patch("services.vision.chat_with_vision_stream", side_effect=_fake_ollama_stream):
        events = []
        async for event in identify_components_stream(b"fake_image"):
            events.append(event)

    event_types = [e["event"] for e in events]
    assert "phase" in event_types
    assert "done" in event_types

    done_event = next(e for e in events if e["event"] == "done")
    assert done_event["data"]["components"][0]["instanceName"] == "R1"


@pytest.mark.asyncio
async def test_identify_stream_emits_error_on_bad_json():
    async def _bad_ollama(*args, **kwargs):
        yield {"phase": "sending", "message": "Sending to Ollama..."}
        yield {"phase": "generating", "message": "AI is analyzing..."}
        yield {"phase": "done_raw", "content": "not valid json at all"}

    with patch("services.vision.chat_with_vision_stream", side_effect=_bad_ollama):
        events = []
        async for event in identify_components_stream(b"fake_image"):
            events.append(event)

    error_event = next(e for e in events if e["event"] == "error")
    assert "unparseable" in error_event["data"]["message"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend && python -m pytest tests/test_vision_stream.py -v
```
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement streaming vision functions**

Add to `backend/services/vision.py` after the import line `from services.ollama_client import chat_with_vision`:

```python
from services.ollama_client import chat_with_vision_stream
```

Then add the following four functions after the existing `describe_wires` function:

```python
from collections.abc import AsyncGenerator


async def identify_components_stream(image_bytes: bytes) -> AsyncGenerator[dict, None]:
    """Streaming variant of identify_components. Yields SSE event dicts."""
    yield {"event": "phase", "data": {"phase": "received", "message": f"Image received ({len(image_bytes) // 1024} KB)"}}
    system = _load_prompt("identify_system.txt")
    user = (
        "List every component in this schematic. For each, provide:\n"
        "- type (one of: res, cap, ind, voltage, current, opamp2, opamp, npn, pnp, nmos, pmos, diode, zener)\n"
        "- instanceName (the label, e.g. R1, U1, V3)\n"
        "- value (the displayed value)\n"
        "- value2 (only for voltage sources with a second value, otherwise omit)\n\n"
        'Output as JSON array:\n[{"type": "res", "instanceName": "R1", "value": "1k"}, ...]'
    )
    raw_content = None
    try:
        async for event in chat_with_vision_stream(VISION_MODEL, system, user, image_bytes):
            if event["phase"] == "done_raw":
                raw_content = event["content"]
            else:
                yield {"event": "phase", "data": event}

        yield {"event": "phase", "data": {"phase": "parsing", "message": "Parsing response..."}}
        result = _extract_json(raw_content)
        components = result if isinstance(result, list) else result.get("components", [])
        yield {"event": "done", "data": {"components": components}}
    except (json.JSONDecodeError, ValueError):
        yield {"event": "error", "data": {"message": "AI returned an unparseable response. Try again."}}
    except Exception as e:
        import httpx as _httpx
        if isinstance(e, _httpx.ConnectError):
            yield {"event": "error", "data": {"message": "Cannot connect to Ollama at localhost:11434"}}
        elif isinstance(e, _httpx.ReadTimeout):
            yield {"event": "error", "data": {"message": "Ollama timed out after 10 minutes"}}
        else:
            yield {"event": "error", "data": {"message": f"Unexpected error: {e}"}}


async def read_directives_stream(image_bytes: bytes) -> AsyncGenerator[dict, None]:
    """Streaming variant of read_directives. Yields SSE event dicts."""
    yield {"event": "phase", "data": {"phase": "received", "message": f"Image received ({len(image_bytes) // 1024} KB)"}}
    system = _load_prompt("directives_system.txt")
    user = (
        "List every SPICE directive visible in this schematic.\n"
        'Output as a JSON array of strings:\n'
        '[".param RINP=1k PSV=15", ".tran 0.005"]'
    )
    raw_content = None
    try:
        async for event in chat_with_vision_stream(VISION_MODEL, system, user, image_bytes):
            if event["phase"] == "done_raw":
                raw_content = event["content"]
            else:
                yield {"event": "phase", "data": event}

        yield {"event": "phase", "data": {"phase": "parsing", "message": "Parsing response..."}}
        result = _extract_json(raw_content)
        directives = result if isinstance(result, list) else result.get("directives", [])
        yield {"event": "done", "data": {"directives": directives}}
    except (json.JSONDecodeError, ValueError):
        yield {"event": "error", "data": {"message": "AI returned an unparseable response. Try again."}}
    except Exception as e:
        import httpx as _httpx
        if isinstance(e, _httpx.ConnectError):
            yield {"event": "error", "data": {"message": "Cannot connect to Ollama at localhost:11434"}}
        elif isinstance(e, _httpx.ReadTimeout):
            yield {"event": "error", "data": {"message": "Ollama timed out after 10 minutes"}}
        else:
            yield {"event": "error", "data": {"message": f"Unexpected error: {e}"}}


async def describe_layout_stream(image_bytes: bytes, components: list[dict]) -> AsyncGenerator[dict, None]:
    """Streaming variant of describe_layout. Yields SSE event dicts."""
    yield {"event": "phase", "data": {"phase": "received", "message": f"Image received ({len(image_bytes) // 1024} KB)"}}
    system = _load_prompt("layout_system.txt")
    comp_list = ", ".join(f"{c['instanceName']} ({c['type']})" for c in components)
    user = (
        f"These components were identified in the schematic:\n{comp_list}\n\n"
        "For each component, describe:\n"
        "- region: which area (top-left, top-center, top-right, center-left, center, center-right, bottom-left, bottom-center, bottom-right)\n"
        "- nearby: which other components are adjacent and in which direction\n\n"
        'Output as JSON array:\n'
        '[{"instanceName": "U1", "region": "center", "nearby": [{"name": "R5", "direction": "above"}]}, ...]'
    )
    raw_content = None
    try:
        async for event in chat_with_vision_stream(VISION_MODEL, system, user, image_bytes):
            if event["phase"] == "done_raw":
                raw_content = event["content"]
            else:
                yield {"event": "phase", "data": event}

        yield {"event": "phase", "data": {"phase": "parsing", "message": "Parsing response..."}}
        result = _extract_json(raw_content)
        layout = result if isinstance(result, list) else result.get("layout", [])
        yield {"event": "done", "data": {"layout": layout}}
    except (json.JSONDecodeError, ValueError):
        yield {"event": "error", "data": {"message": "AI returned an unparseable response. Try again."}}
    except Exception as e:
        import httpx as _httpx
        if isinstance(e, _httpx.ConnectError):
            yield {"event": "error", "data": {"message": "Cannot connect to Ollama at localhost:11434"}}
        elif isinstance(e, _httpx.ReadTimeout):
            yield {"event": "error", "data": {"message": "Ollama timed out after 10 minutes"}}
        else:
            yield {"event": "error", "data": {"message": f"Unexpected error: {e}"}}


async def describe_wires_stream(image_bytes: bytes, components: list[dict], pin_info: dict) -> AsyncGenerator[dict, None]:
    """Streaming variant of describe_wires. Yields SSE event dicts."""
    yield {"event": "phase", "data": {"phase": "received", "message": f"Image received ({len(image_bytes) // 1024} KB)"}}
    system = _load_prompt("wires_system.txt")
    comp_lines = []
    for c in components:
        pins = pin_info.get(c["type"], [])
        pin_names = ", ".join(p["name"] for p in pins)
        comp_lines.append(f"- {c['instanceName']} ({c['type']}): pins [{pin_names}]")
    comp_text = "\n".join(comp_lines)
    user = (
        f"These components are in the schematic:\n{comp_text}\n\n"
        "Describe every wire connection:\n"
        "- Which component pin connects to which other component pin\n"
        "- Any ground connections (which pin connects to ground)\n"
        "- Any net labels (which pin has a label and what is it)\n\n"
        'Output as JSON:\n'
        '{"connections": [{"from": {"component": "R5", "pin": "2"}, "to": {"component": "U1", "pin": "In-"}}], '
        '"grounds": [{"component": "V3", "pin": "-"}], '
        '"labels": [{"component": "U1", "pin": "OUT", "label": "OUT"}]}'
    )
    raw_content = None
    try:
        async for event in chat_with_vision_stream(VISION_MODEL, system, user, image_bytes):
            if event["phase"] == "done_raw":
                raw_content = event["content"]
            else:
                yield {"event": "phase", "data": event}

        yield {"event": "phase", "data": {"phase": "parsing", "message": "Parsing response..."}}
        result = _extract_json(raw_content)
        wire_desc = result if isinstance(result, dict) else {"connections": [], "grounds": [], "labels": []}
        yield {"event": "done", "data": {"wire_descriptions": wire_desc}}
    except (json.JSONDecodeError, ValueError):
        yield {"event": "error", "data": {"message": "AI returned an unparseable response. Try again."}}
    except Exception as e:
        import httpx as _httpx
        if isinstance(e, _httpx.ConnectError):
            yield {"event": "error", "data": {"message": "Cannot connect to Ollama at localhost:11434"}}
        elif isinstance(e, _httpx.ReadTimeout):
            yield {"event": "error", "data": {"message": "Ollama timed out after 10 minutes"}}
        else:
            yield {"event": "error", "data": {"message": f"Unexpected error: {e}"}}
```

- [ ] **Step 4: Run tests**

Run:
```bash
cd backend && python -m pytest tests/test_vision_stream.py -v
```
Expected: PASS

- [ ] **Step 5: Run all backend tests**

Run:
```bash
cd backend && python -m pytest tests/ -v
```
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/vision.py backend/tests/test_vision_stream.py
git commit -m "feat: add streaming vision functions for SSE progress"
```

---

### Task 3: Health Check + Streaming Wizard Endpoints

**Files:**
- Modify: `backend/api/wizard_routes.py`
- Modify: `backend/tests/test_wizard_routes.py`

- [ ] **Step 1: Write failing tests**

Replace `backend/tests/test_wizard_routes.py` with:

```python
import pytest
from unittest.mock import patch, AsyncMock
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


@pytest.mark.asyncio
async def test_health_ollama_ok():
    """Health check returns ok when Ollama is reachable and model exists."""
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"models": [{"name": "qwen3-vl:8b"}]}
    mock_resp.raise_for_status = lambda: None

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("api.wizard_routes.httpx.AsyncClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/wizard/health/ollama")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_health_ollama_unreachable():
    """Health check returns error when Ollama is not running."""
    import httpx as _httpx

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=_httpx.ConnectError("refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("api.wizard_routes.httpx.AsyncClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/wizard/health/ollama")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "Cannot reach Ollama" in data["error"]


@pytest.mark.asyncio
async def test_identify_stream_returns_sse_content_type():
    """Streaming endpoint returns text/event-stream."""
    async def _fake_stream(image_bytes):
        yield {"event": "phase", "data": {"phase": "received", "message": "Image received (0 KB)"}}
        yield {"event": "done", "data": {"components": []}}

    with patch("api.wizard_routes.identify_components_stream", side_effect=_fake_stream):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/wizard/identify/stream",
                files={"file": ("test.png", b"fake", "image/png")},
            )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "event: phase" in resp.text
    assert "event: done" in resp.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && python -m pytest tests/test_wizard_routes.py::test_health_ollama_ok -v
```
Expected: FAIL (endpoint doesn't exist)

- [ ] **Step 3: Implement health check and streaming endpoints**

Replace `backend/api/wizard_routes.py` with:

```python
import json
from pathlib import Path

import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import StreamingResponse

from services.vision import (
    identify_components, read_directives, describe_layout, describe_wires,
    identify_components_stream, read_directives_stream,
    describe_layout_stream, describe_wires_stream,
)
from services.layout import compute_layout
from services.wire_router import compute_wires

router = APIRouter(prefix="/api/wizard")

DICTIONARY_DIR = Path(__file__).parent.parent.parent / "dictionary"
VISION_MODEL = "qwen3-vl:8b"


def _load_dictionary() -> dict:
    return json.loads(
        (DICTIONARY_DIR / "components.json").read_text(encoding="utf-8")
    )


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ── Health check ─────────────────────────────────────────────────────────────


@router.get("/health/ollama")
async def health_ollama():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            resp.raise_for_status()
            models = resp.json().get("models", [])
            names = [m.get("name", "") for m in models]
            if any(VISION_MODEL in n for n in names):
                return {"ok": True, "model": VISION_MODEL}
            return {"ok": False, "error": f"Model {VISION_MODEL} not found. Run: ollama pull {VISION_MODEL}"}
    except httpx.ConnectError:
        return {"ok": False, "error": "Cannot reach Ollama. Start it with: ollama serve"}
    except Exception as e:
        return {"ok": False, "error": f"Ollama health check failed: {e}"}


# ── Original (non-streaming) endpoints ───────────────────────────────────────


@router.post("/identify")
async def wizard_identify(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    image_bytes = await file.read()
    components = await identify_components(image_bytes)
    return {"components": components}


@router.post("/directives")
async def wizard_directives(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    image_bytes = await file.read()
    directives = await read_directives(image_bytes)
    return {"directives": directives}


@router.post("/layout")
async def wizard_layout(
    file: UploadFile = File(...),
    components_json: str = Form(""),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    image_bytes = await file.read()
    components = json.loads(components_json) if components_json else []

    layout_desc = await describe_layout(image_bytes, components)

    dictionary = _load_dictionary()
    comp_sizes = {}
    for comp_id, comp_data in dictionary["components"].items():
        comp_sizes[comp_id] = {
            "width": comp_data["symbol"]["width"],
            "height": comp_data["symbol"]["height"],
        }

    positions = compute_layout(layout_desc, comp_sizes)
    return {"layout": layout_desc, "positions": positions}


@router.post("/wires")
async def wizard_wires(
    file: UploadFile = File(...),
    components_json: str = Form(""),
    positions_json: str = Form(""),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    image_bytes = await file.read()
    components = json.loads(components_json) if components_json else []
    positions = json.loads(positions_json) if positions_json else {}

    dictionary = _load_dictionary()
    pin_defs = {}
    for comp_id, comp_data in dictionary["components"].items():
        pin_defs[comp_id] = comp_data.get("pins", [])

    wire_desc = await describe_wires(image_bytes, components, pin_defs)

    comp_map = {}
    for comp in components:
        name = comp["instanceName"]
        if name in positions:
            comp_map[name] = {
                "x": positions[name]["x"],
                "y": positions[name]["y"],
                "type": comp["type"],
            }

    wire_result = compute_wires(comp_map, pin_defs, wire_desc)

    return {
        "wire_descriptions": wire_desc,
        "wires": [{"x1": w[0], "y1": w[1], "x2": w[2], "y2": w[3]} for w in wire_result.wires],
        "flags": wire_result.flags,
    }


# ── Streaming endpoints ─────────────────────────────────────────────────────


async def _stream_events(event_gen):
    """Convert an async generator of event dicts to SSE text chunks."""
    async for event in event_gen:
        yield _format_sse(event["event"], event["data"])


@router.post("/identify/stream")
async def wizard_identify_stream(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    image_bytes = await file.read()
    return StreamingResponse(
        _stream_events(identify_components_stream(image_bytes)),
        media_type="text/event-stream",
    )


@router.post("/directives/stream")
async def wizard_directives_stream(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    image_bytes = await file.read()
    return StreamingResponse(
        _stream_events(read_directives_stream(image_bytes)),
        media_type="text/event-stream",
    )


@router.post("/layout/stream")
async def wizard_layout_stream(
    file: UploadFile = File(...),
    components_json: str = Form(""),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    image_bytes = await file.read()
    components = json.loads(components_json) if components_json else []

    async def _layout_stream():
        layout_data = None
        async for event in describe_layout_stream(image_bytes, components):
            yield event
            if event["event"] == "done":
                layout_data = event["data"]["layout"]

        if layout_data is not None:
            yield {"event": "phase", "data": {"phase": "computing", "message": "Computing grid positions..."}}
            dictionary = _load_dictionary()
            comp_sizes = {}
            for comp_id, comp_data in dictionary["components"].items():
                comp_sizes[comp_id] = {
                    "width": comp_data["symbol"]["width"],
                    "height": comp_data["symbol"]["height"],
                }
            positions = compute_layout(layout_data, comp_sizes)
            yield {"event": "done", "data": {"layout": layout_data, "positions": positions}}

    return StreamingResponse(
        _stream_events(_layout_stream()),
        media_type="text/event-stream",
    )


@router.post("/wires/stream")
async def wizard_wires_stream(
    file: UploadFile = File(...),
    components_json: str = Form(""),
    positions_json: str = Form(""),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    image_bytes = await file.read()
    components = json.loads(components_json) if components_json else []
    positions = json.loads(positions_json) if positions_json else {}

    dictionary = _load_dictionary()
    pin_defs = {}
    for comp_id, comp_data in dictionary["components"].items():
        pin_defs[comp_id] = comp_data.get("pins", [])

    async def _wires_stream():
        wire_desc_data = None
        async for event in describe_wires_stream(image_bytes, components, pin_defs):
            yield event
            if event["event"] == "done":
                wire_desc_data = event["data"]["wire_descriptions"]

        if wire_desc_data is not None:
            yield {"event": "phase", "data": {"phase": "routing", "message": "Computing wire routes..."}}
            comp_map = {}
            for comp in components:
                name = comp["instanceName"]
                if name in positions:
                    comp_map[name] = {
                        "x": positions[name]["x"],
                        "y": positions[name]["y"],
                        "type": comp["type"],
                    }
            wire_result = compute_wires(comp_map, pin_defs, wire_desc_data)
            yield {"event": "done", "data": {
                "wire_descriptions": wire_desc_data,
                "wires": [{"x1": w[0], "y1": w[1], "x2": w[2], "y2": w[3]} for w in wire_result.wires],
                "flags": wire_result.flags,
            }}

    return StreamingResponse(
        _stream_events(_wires_stream()),
        media_type="text/event-stream",
    )
```

**Important note:** The `/layout/stream` and `/wires/stream` endpoints emit TWO `done` events — the first from the vision function (with layout/wire descriptions), then after local computation, a second `done` with the final result (positions/wires). The frontend should use the LAST `done` event as the result. This is handled by the `_layout_stream` and `_wires_stream` inner generators which intercept the first `done`, run compute, and emit a replacement `done`.

Wait — that's not right. The inner generator intercepts the `done` from the vision stream, does NOT forward it, and instead emits a new `done` with the full result. Let me fix the logic: the inner generators should NOT yield the intermediate `done` from the vision stream. Let me correct:

Actually, re-reading the code: the `_layout_stream` generator yields ALL events from `describe_layout_stream` (including its `done`), then yields another `done` after computing positions. That means two `done` events reach the client. The frontend would resolve the promise on the first `done` and miss the positions.

The fix: in `_layout_stream`, skip the vision stream's `done` event and only emit the final computed `done`. Same for `_wires_stream`.

Here is the corrected inner generator for `/layout/stream`:

```python
    async def _layout_stream():
        layout_data = None
        async for event in describe_layout_stream(image_bytes, components):
            if event["event"] == "done":
                layout_data = event["data"]["layout"]
            else:
                yield event

        if layout_data is not None:
            yield {"event": "phase", "data": {"phase": "computing", "message": "Computing grid positions..."}}
            dictionary = _load_dictionary()
            comp_sizes = {}
            for comp_id, comp_data in dictionary["components"].items():
                comp_sizes[comp_id] = {
                    "width": comp_data["symbol"]["width"],
                    "height": comp_data["symbol"]["height"],
                }
            positions = compute_layout(layout_data, comp_sizes)
            yield {"event": "done", "data": {"layout": layout_data, "positions": positions}}
```

And the corrected inner generator for `/wires/stream`:

```python
    async def _wires_stream():
        wire_desc_data = None
        async for event in describe_wires_stream(image_bytes, components, pin_defs):
            if event["event"] == "done":
                wire_desc_data = event["data"]["wire_descriptions"]
            else:
                yield event

        if wire_desc_data is not None:
            yield {"event": "phase", "data": {"phase": "routing", "message": "Computing wire routes..."}}
            comp_map = {}
            for comp in components:
                name = comp["instanceName"]
                if name in positions:
                    comp_map[name] = {
                        "x": positions[name]["x"],
                        "y": positions[name]["y"],
                        "type": comp["type"],
                    }
            wire_result = compute_wires(comp_map, pin_defs, wire_desc_data)
            yield {"event": "done", "data": {
                "wire_descriptions": wire_desc_data,
                "wires": [{"x1": w[0], "y1": w[1], "x2": w[2], "y2": w[3]} for w in wire_result.wires],
                "flags": wire_result.flags,
            }}
```

Use these corrected versions in the full file above — the `if event["event"] == "done":` branch captures the data without yielding the intermediate done event.

- [ ] **Step 4: Run tests**

Run:
```bash
cd backend && python -m pytest tests/test_wizard_routes.py -v
```
Expected: All tests PASS

- [ ] **Step 5: Run all backend tests**

Run:
```bash
cd backend && python -m pytest tests/ -v
```
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/api/wizard_routes.py backend/tests/test_wizard_routes.py
git commit -m "feat: add SSE streaming wizard endpoints and Ollama health check"
```

---

### Task 4: useWizardStream Hook

**Files:**
- Create: `frontend/src/hooks/useWizardStream.ts`

- [ ] **Step 1: Create the hook**

Create `frontend/src/hooks/useWizardStream.ts`:

```typescript
import { useState, useRef, useCallback } from "react";

export interface WizardLogEntry {
  timestamp: number;
  phase: string;
  message: string;
  isError?: boolean;
}

interface UseWizardStreamReturn {
  execute: (url: string, formData: FormData) => Promise<unknown>;
  log: WizardLogEntry[];
  currentPhase: string | null;
  elapsed: number;
  isStreaming: boolean;
  error: string | null;
  clearLog: () => void;
}

function parseSSE(text: string): { event: string; data: string }[] {
  const events: { event: string; data: string }[] = [];
  const blocks = text.split("\n\n");
  for (const block of blocks) {
    if (!block.trim()) continue;
    let event = "message";
    let data = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) {
        event = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        data = line.slice(6);
      }
    }
    if (data) {
      events.push({ event, data });
    }
  }
  return events;
}

export function useWizardStream(): UseWizardStreamReturn {
  const [log, setLog] = useState<WizardLogEntry[]>([]);
  const [currentPhase, setCurrentPhase] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const startTimeRef = useRef<number>(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearLog = useCallback(() => {
    setLog([]);
    setCurrentPhase(null);
    setElapsed(0);
    setError(null);
  }, []);

  const execute = useCallback(
    (url: string, formData: FormData): Promise<unknown> => {
      return new Promise((resolve, reject) => {
        setIsStreaming(true);
        setError(null);
        startTimeRef.current = Date.now();
        setElapsed(0);

        timerRef.current = setInterval(() => {
          setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000));
        }, 1000);

        const stopTimer = () => {
          if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
          }
          setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000));
          setIsStreaming(false);
        };

        fetch(url, { method: "POST", body: formData })
          .then(async (resp) => {
            if (!resp.ok) {
              stopTimer();
              const msg = `Request failed: ${resp.status}`;
              setError(msg);
              setLog((prev) => [
                ...prev,
                {
                  timestamp: Date.now() - startTimeRef.current,
                  phase: "error",
                  message: msg,
                  isError: true,
                },
              ]);
              reject(new Error(msg));
              return;
            }

            const reader = resp.body?.getReader();
            if (!reader) {
              stopTimer();
              const msg = "No response stream available";
              setError(msg);
              reject(new Error(msg));
              return;
            }

            const decoder = new TextDecoder();
            let buffer = "";
            let result: unknown = null;

            try {
              while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const events = parseSSE(buffer);

                // Keep any incomplete trailing block
                const lastDoubleNewline = buffer.lastIndexOf("\n\n");
                if (lastDoubleNewline !== -1) {
                  buffer = buffer.slice(lastDoubleNewline + 2);
                }

                for (const evt of events) {
                  const data = JSON.parse(evt.data);

                  if (evt.event === "phase") {
                    const ts = Date.now() - startTimeRef.current;
                    setCurrentPhase(data.phase);
                    setLog((prev) => [
                      ...prev,
                      { timestamp: ts, phase: data.phase, message: data.message },
                    ]);
                  } else if (evt.event === "done") {
                    result = data;
                    const ts = Date.now() - startTimeRef.current;
                    setCurrentPhase(null);
                    setLog((prev) => [
                      ...prev,
                      { timestamp: ts, phase: "complete", message: "Step complete" },
                    ]);
                  } else if (evt.event === "error") {
                    const ts = Date.now() - startTimeRef.current;
                    setError(data.message);
                    setCurrentPhase(null);
                    setLog((prev) => [
                      ...prev,
                      {
                        timestamp: ts,
                        phase: "error",
                        message: data.message,
                        isError: true,
                      },
                    ]);
                  }
                }
              }
            } catch (readErr) {
              stopTimer();
              const msg =
                readErr instanceof Error ? readErr.message : String(readErr);
              setError(msg);
              reject(new Error(msg));
              return;
            }

            stopTimer();

            if (result === null) {
              // error was already set via SSE error event
              reject(new Error("No result received"));
            } else {
              resolve(result);
            }
          })
          .catch((fetchErr) => {
            stopTimer();
            const msg =
              fetchErr instanceof Error ? fetchErr.message : String(fetchErr);
            setError(msg);
            setLog((prev) => [
              ...prev,
              {
                timestamp: Date.now() - startTimeRef.current,
                phase: "error",
                message: msg,
                isError: true,
              },
            ]);
            reject(fetchErr);
          });
      });
    },
    []
  );

  return { execute, log, currentPhase, elapsed, isStreaming, error, clearLog };
}
```

- [ ] **Step 2: Verify frontend builds**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds with no TypeScript errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useWizardStream.ts
git commit -m "feat: add useWizardStream hook for SSE consumption"
```

---

### Task 5: GenerateWizard Integration

**Files:**
- Modify: `frontend/src/components/GenerateWizard.tsx`

- [ ] **Step 1: Update GenerateWizard.tsx**

Replace the entire file `frontend/src/components/GenerateWizard.tsx` with the following. Key changes from the original:
- Imports and uses `useWizardStream` hook instead of `api.ts` functions
- Adds pre-flight Ollama health check on mount
- Adds Activity Log panel between body and footer
- Replaces `loading` boolean with `stream.isStreaming`
- Replaces `error` string with `stream.error`
- "Next" button shows current phase message instead of "Loading..."

```tsx
import { useState, useCallback, useEffect, useRef } from "react";
import type { Dictionary, WizardComponent } from "../types/schematic";
import { useWizardStream } from "../hooks/useWizardStream";

const BASE_URL = "http://localhost:8000/api/wizard";

interface GenerateWizardProps {
  imageFile: File;
  dictionary: Dictionary | null;
  onAddComponent: (
    type: string,
    name: string,
    value: string,
    pos: { x: number; y: number },
    value2?: string
  ) => void;
  onAddWire: (from: { x: number; y: number }, to: { x: number; y: number }) => void;
  onAddFlag: (name: string, pos: { x: number; y: number }) => void;
  onAddText: (content: string, pos: { x: number; y: number }) => void;
  onClose: () => void;
}

type Step = 1 | 2 | 3 | 4 | 5 | 6;

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function GenerateWizard({
  imageFile,
  dictionary,
  onAddComponent,
  onAddWire,
  onAddFlag,
  onAddText,
  onClose,
}: GenerateWizardProps) {
  const [step, setStep] = useState<Step>(1);
  const [minimized, setMinimized] = useState(false);
  const stream = useWizardStream();
  const logEndRef = useRef<HTMLDivElement>(null);

  // Pre-flight health check
  const [healthWarning, setHealthWarning] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${BASE_URL}/health/ollama`)
      .then((r) => r.json())
      .then((data) => {
        if (!data.ok) setHealthWarning(data.error);
      })
      .catch(() => setHealthWarning("Cannot reach backend at localhost:8000"));
  }, []);

  // Auto-scroll log
  const [logExpanded, setLogExpanded] = useState(false);
  useEffect(() => {
    if (stream.isStreaming && !logExpanded) setLogExpanded(true);
  }, [stream.isStreaming, logExpanded]);
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [stream.log.length]);

  // Step 1: canvas
  const [canvasWidth, setCanvasWidth] = useState(880);
  const [canvasHeight, setCanvasHeight] = useState(680);

  // Step 2: components
  const [components, setComponents] = useState<WizardComponent[]>([]);

  // Step 3: directives
  const [directives, setDirectives] = useState<string[]>([]);

  // Step 4: positions
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});

  // Summary
  const [wireCount, setWireCount] = useState(0);
  const [flagCount, setFlagCount] = useState(0);

  const componentTypes = dictionary ? Object.keys(dictionary.components) : [];

  // ── Step transitions ────────────────────────────────────────────────────────

  const goStep1to2 = useCallback(async () => {
    const formData = new FormData();
    formData.append("file", imageFile);
    try {
      const result = await stream.execute(`${BASE_URL}/identify/stream`, formData) as { components: WizardComponent[] };
      setComponents(
        result.components.map((c) => ({ ...c, confirmed: false }))
      );
      setStep(2);
    } catch {
      // error already set in stream state
    }
  }, [imageFile, stream]);

  const goStep2to3 = useCallback(async () => {
    const formData = new FormData();
    formData.append("file", imageFile);
    try {
      const result = await stream.execute(`${BASE_URL}/directives/stream`, formData) as { directives: string[] };
      setDirectives(result.directives);
      setStep(3);
    } catch {
      // error already set in stream state
    }
  }, [imageFile, stream]);

  const goStep3to4 = useCallback(async () => {
    const confirmed = components.filter((c) => c.confirmed !== false);
    const formData = new FormData();
    formData.append("file", imageFile);
    formData.append("components_json", JSON.stringify(confirmed));
    try {
      const result = await stream.execute(`${BASE_URL}/layout/stream`, formData) as {
        positions: Record<string, { x: number; y: number }>;
      };
      setPositions(result.positions);

      confirmed.forEach((comp) => {
        const pos = result.positions[comp.instanceName] ?? { x: 400, y: 300 };
        onAddComponent(comp.type, comp.instanceName, comp.value, pos, comp.value2);
      });

      directives.forEach((d, i) => {
        onAddText(d, { x: 50, y: 50 + i * 32 });
      });

      setStep(4);
    } catch {
      // error already set in stream state
    }
  }, [imageFile, components, directives, onAddComponent, onAddText, stream]);

  const goStep4to5 = useCallback(async () => {
    const confirmed = components.filter((c) => c.confirmed !== false);
    const formData = new FormData();
    formData.append("file", imageFile);
    formData.append("components_json", JSON.stringify(confirmed));
    formData.append("positions_json", JSON.stringify(positions));
    try {
      const result = await stream.execute(`${BASE_URL}/wires/stream`, formData) as {
        wires: { x1: number; y1: number; x2: number; y2: number }[];
        flags: { name: string; x: number; y: number }[];
      };

      result.wires.forEach((w) => {
        onAddWire({ x: w.x1, y: w.y1 }, { x: w.x2, y: w.y2 });
      });
      result.flags.forEach((f) => {
        onAddFlag(f.name, { x: f.x, y: f.y });
      });

      setWireCount(result.wires.length);
      setFlagCount(result.flags.length);
      setStep(6);
    } catch {
      // error already set in stream state
    }
  }, [imageFile, components, positions, onAddWire, onAddFlag, stream]);

  // ── Component row helpers ───────────────────────────────────────────────────

  const updateComp = (idx: number, updates: Partial<WizardComponent>) => {
    setComponents((prev) =>
      prev.map((c, i) => (i === idx ? { ...c, ...updates } : c))
    );
  };

  const deleteComp = (idx: number) => {
    setComponents((prev) => prev.filter((_, i) => i !== idx));
  };

  const confirmComp = (idx: number) => {
    updateComp(idx, { confirmed: true });
  };

  const addMissingComp = () => {
    setComponents((prev) => [
      ...prev,
      { type: componentTypes[0] ?? "res", instanceName: `R${prev.length + 1}`, value: "1k", confirmed: false },
    ]);
  };

  // ── Directives helpers ──────────────────────────────────────────────────────

  const updateDirective = (idx: number, val: string) => {
    setDirectives((prev) => prev.map((d, i) => (i === idx ? val : d)));
  };

  const deleteDirective = (idx: number) => {
    setDirectives((prev) => prev.filter((_, i) => i !== idx));
  };

  const addDirective = () => {
    setDirectives((prev) => [...prev, ".tran 1m"]);
  };

  // ── Button label ──────────────────────────────────────────────────────────

  const getButtonLabel = () => {
    if (stream.isStreaming) {
      if (stream.currentPhase) {
        const labels: Record<string, string> = {
          received: "Processing...",
          sending: "Sending to AI...",
          generating: "AI is analyzing...",
          parsing: "Parsing results...",
          computing: "Computing layout...",
          routing: "Computing wires...",
        };
        return labels[stream.currentPhase] ?? "Processing...";
      }
      return "Processing...";
    }
    if (step === 4) return "Trace Wires";
    return "Next \u2192";
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  if (minimized) {
    return (
      <div
        style={{
          position: "fixed",
          bottom: 24,
          left: "50%",
          transform: "translateX(-50%)",
          zIndex: 2000,
          background: "var(--bg-panel)",
          border: "1px solid var(--color-border)",
          borderRadius: 24,
          padding: "8px 20px",
          display: "flex",
          alignItems: "center",
          gap: 12,
          boxShadow: "0 4px 16px rgba(0,0,0,0.25)",
          cursor: "default",
        }}
      >
        <span style={{ fontSize: 13, color: "var(--color-text)" }}>
          Generate Wizard — Step {step} of 5
          {stream.isStreaming && ` (${formatTime(stream.elapsed)})`}
        </span>
        <button
          onClick={() => setMinimized(false)}
          style={{
            padding: "2px 10px",
            borderRadius: 12,
            border: "1px solid var(--color-border)",
            background: "var(--bg-canvas)",
            color: "var(--color-text)",
            cursor: "pointer",
            fontSize: 12,
          }}
        >
          Show
        </button>
        <button
          onClick={onClose}
          style={{
            padding: "2px 8px",
            borderRadius: 12,
            border: "1px solid var(--color-border)",
            background: "var(--bg-canvas)",
            color: "var(--color-text)",
            cursor: "pointer",
            fontSize: 12,
          }}
        >
          ✕
        </button>
      </div>
    );
  }

  const stepLabels = ["Canvas", "Identify", "Directives", "Layout", "Wires"];

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1500,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.45)",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          background: "var(--bg-panel)",
          color: "var(--color-text)",
          border: "1px solid var(--color-border)",
          borderRadius: 8,
          width: 620,
          maxWidth: "95vw",
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 8px 32px rgba(0,0,0,0.35)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            padding: "10px 16px",
            borderBottom: "1px solid var(--color-border)",
            gap: 8,
          }}
        >
          <strong style={{ flex: 1, fontSize: 15 }}>Generate from Image</strong>
          <button
            onClick={() => setMinimized(true)}
            title="Minimize"
            style={{
              background: "none",
              border: "1px solid var(--color-border)",
              borderRadius: 4,
              padding: "2px 8px",
              cursor: "pointer",
              color: "var(--color-text)",
              fontSize: 12,
            }}
          >
            —
          </button>
          <button
            onClick={onClose}
            title="Close"
            style={{
              background: "none",
              border: "1px solid var(--color-border)",
              borderRadius: 4,
              padding: "2px 8px",
              cursor: "pointer",
              color: "var(--color-text)",
              fontSize: 12,
            }}
          >
            ✕
          </button>
        </div>

        {/* Step indicator */}
        {step <= 5 && (
          <div
            style={{
              display: "flex",
              padding: "8px 16px",
              gap: 4,
              borderBottom: "1px solid var(--color-border)",
              background: "var(--bg-canvas)",
            }}
          >
            {stepLabels.map((label, i) => {
              const s = (i + 1) as Step;
              const active = s === step;
              const done = s < step;
              return (
                <div
                  key={label}
                  style={{
                    flex: 1,
                    textAlign: "center",
                    fontSize: 11,
                    padding: "4px 2px",
                    borderRadius: 4,
                    background: done
                      ? "var(--color-success, #4caf50)"
                      : active
                      ? "var(--color-accent, #1976d2)"
                      : "var(--bg-panel)",
                    color: active || done ? "#fff" : "var(--color-text-muted)",
                    fontWeight: active ? "bold" : "normal",
                    border: "1px solid var(--color-border)",
                  }}
                >
                  {done ? "\u2713 " : ""}{label}
                </div>
              );
            })}
          </div>
        )}

        {/* Body */}
        <div style={{ flex: 1, overflow: "auto", padding: 16 }}>
          {/* Health warning */}
          {healthWarning && (
            <div
              style={{
                marginBottom: 12,
                padding: "8px 12px",
                background: "#fff3e0",
                color: "#e65100",
                border: "1px solid #e65100",
                borderRadius: 4,
                fontSize: 12,
              }}
            >
              {healthWarning}
            </div>
          )}

          {/* Error from stream */}
          {stream.error && (
            <div
              style={{
                marginBottom: 12,
                padding: "8px 12px",
                background: "var(--color-error-bg, #ffebee)",
                color: "var(--color-error, #c62828)",
                border: "1px solid var(--color-error, #c62828)",
                borderRadius: 4,
                fontSize: 13,
              }}
            >
              {stream.error}
            </div>
          )}

          {/* ── Step 1: Canvas ── */}
          {step === 1 && (
            <div>
              <p style={{ marginTop: 0, fontSize: 13 }}>
                Set the canvas size for the generated schematic.
              </p>
              <div style={{ display: "flex", gap: 16, alignItems: "flex-end" }}>
                <label style={{ fontSize: 13 }}>
                  Width (px)
                  <br />
                  <input
                    type="number"
                    value={canvasWidth}
                    onChange={(e) => setCanvasWidth(Number(e.target.value))}
                    style={{
                      marginTop: 4,
                      padding: "4px 8px",
                      border: "1px solid var(--color-border)",
                      borderRadius: 4,
                      background: "var(--bg-canvas)",
                      color: "var(--color-text)",
                      width: 100,
                    }}
                  />
                </label>
                <label style={{ fontSize: 13 }}>
                  Height (px)
                  <br />
                  <input
                    type="number"
                    value={canvasHeight}
                    onChange={(e) => setCanvasHeight(Number(e.target.value))}
                    style={{
                      marginTop: 4,
                      padding: "4px 8px",
                      border: "1px solid var(--color-border)",
                      borderRadius: 4,
                      background: "var(--bg-canvas)",
                      color: "var(--color-text)",
                      width: 100,
                    }}
                  />
                </label>
              </div>
              <p style={{ fontSize: 12, color: "var(--color-text-muted)", marginTop: 8 }}>
                Image: <em>{imageFile.name}</em> — Next step will identify components.
              </p>
            </div>
          )}

          {/* ── Step 2: Identify Components ── */}
          {step === 2 && (
            <div>
              <p style={{ marginTop: 0, fontSize: 13 }}>
                Review identified components. Edit type, name, or value, then confirm each row.
              </p>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ background: "var(--bg-canvas)" }}>
                      <th style={thStyle}>Type</th>
                      <th style={thStyle}>Name</th>
                      <th style={thStyle}>Value</th>
                      <th style={thStyle}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {components.map((comp, idx) => (
                      <tr
                        key={idx}
                        style={{
                          background: comp.confirmed
                            ? "var(--color-success-bg, #e8f5e9)"
                            : "transparent",
                        }}
                      >
                        <td style={tdStyle}>
                          <select
                            value={comp.type}
                            onChange={(e) => updateComp(idx, { type: e.target.value })}
                            style={{
                              padding: "2px 4px",
                              border: "1px solid var(--color-border)",
                              borderRadius: 3,
                              background: "var(--bg-canvas)",
                              color: "var(--color-text)",
                              fontSize: 12,
                              maxWidth: 120,
                            }}
                          >
                            {componentTypes.map((t) => (
                              <option key={t} value={t}>
                                {dictionary?.components[t]?.displayName ?? t}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td style={tdStyle}>
                          <input
                            value={comp.instanceName}
                            onChange={(e) => updateComp(idx, { instanceName: e.target.value })}
                            style={inputStyle}
                          />
                        </td>
                        <td style={tdStyle}>
                          <input
                            value={comp.value}
                            onChange={(e) => updateComp(idx, { value: e.target.value })}
                            style={inputStyle}
                          />
                        </td>
                        <td style={{ ...tdStyle, display: "flex", gap: 4 }}>
                          <button
                            onClick={() => confirmComp(idx)}
                            title="Confirm"
                            style={{
                              padding: "2px 6px",
                              background: comp.confirmed
                                ? "var(--color-success, #4caf50)"
                                : "var(--bg-panel)",
                              border: "1px solid var(--color-border)",
                              borderRadius: 3,
                              cursor: "pointer",
                              color: comp.confirmed ? "#fff" : "var(--color-text)",
                            }}
                          >
                            ✓
                          </button>
                          <button
                            onClick={() => deleteComp(idx)}
                            title="Delete"
                            style={{
                              padding: "2px 6px",
                              background: "var(--bg-panel)",
                              border: "1px solid var(--color-border)",
                              borderRadius: 3,
                              cursor: "pointer",
                              color: "var(--color-error, #c62828)",
                            }}
                          >
                            ✕
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button
                onClick={addMissingComp}
                style={{
                  marginTop: 8,
                  padding: "4px 12px",
                  border: "1px solid var(--color-border)",
                  borderRadius: 4,
                  background: "var(--bg-canvas)",
                  color: "var(--color-text)",
                  cursor: "pointer",
                  fontSize: 12,
                }}
              >
                + Add Missing
              </button>
            </div>
          )}

          {/* ── Step 3: Directives ── */}
          {step === 3 && (
            <div>
              <p style={{ marginTop: 0, fontSize: 13 }}>
                Edit simulation directives. These will be added as text to the schematic.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {directives.map((d, idx) => (
                  <div key={idx} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <input
                      value={d}
                      onChange={(e) => updateDirective(idx, e.target.value)}
                      style={{
                        flex: 1,
                        padding: "4px 8px",
                        border: "1px solid var(--color-border)",
                        borderRadius: 4,
                        background: "var(--bg-canvas)",
                        color: "var(--color-text)",
                        fontSize: 13,
                        fontFamily: "monospace",
                      }}
                    />
                    <button
                      onClick={() => deleteDirective(idx)}
                      style={{
                        padding: "4px 8px",
                        border: "1px solid var(--color-border)",
                        borderRadius: 4,
                        background: "var(--bg-panel)",
                        color: "var(--color-error, #c62828)",
                        cursor: "pointer",
                      }}
                    >
                      ✕
                    </button>
                  </div>
                ))}
                {directives.length === 0 && (
                  <p style={{ fontSize: 12, color: "var(--color-text-muted)", margin: 0 }}>
                    No directives detected.
                  </p>
                )}
              </div>
              <button
                onClick={addDirective}
                style={{
                  marginTop: 8,
                  padding: "4px 12px",
                  border: "1px solid var(--color-border)",
                  borderRadius: 4,
                  background: "var(--bg-canvas)",
                  color: "var(--color-text)",
                  cursor: "pointer",
                  fontSize: 12,
                }}
              >
                + Add Directive
              </button>
            </div>
          )}

          {/* ── Step 4: Layout ── */}
          {step === 4 && (
            <div>
              <p style={{ marginTop: 0, fontSize: 13 }}>
                Components have been placed in the editor. You can minimize this modal to drag
                components to their final positions.
              </p>
              <div
                style={{
                  padding: 12,
                  border: "1px solid var(--color-border)",
                  borderRadius: 4,
                  background: "var(--bg-canvas)",
                  fontSize: 12,
                }}
              >
                <strong>{components.filter((c) => c.confirmed !== false).length}</strong>{" "}
                components placed in editor.
              </div>
              <p style={{ fontSize: 12, color: "var(--color-text-muted)", marginTop: 8 }}>
                Click <em>Minimize</em> (—) to interact with the canvas, then come back to continue.
              </p>
            </div>
          )}

          {/* ── Step 5: Wires (processing) ── */}
          {step === 5 && (
            <div style={{ textAlign: "center", padding: 24 }}>
              <p style={{ fontSize: 13, margin: 0 }}>Tracing wires...</p>
            </div>
          )}

          {/* ── Done ── */}
          {step === 6 && (
            <div>
              <p style={{ marginTop: 0, fontSize: 15, fontWeight: "bold" }}>
                Generation complete!
              </p>
              <ul style={{ fontSize: 13, lineHeight: 1.7 }}>
                <li>
                  <strong>{components.filter((c) => c.confirmed !== false).length}</strong>{" "}
                  components placed
                </li>
                <li>
                  <strong>{wireCount}</strong> wires traced
                </li>
                <li>
                  <strong>{flagCount}</strong> flags added
                </li>
                <li>
                  <strong>{directives.length}</strong> directives added
                </li>
              </ul>
              <p style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                Review the schematic in the editor. Use Undo if you need to roll back.
              </p>
            </div>
          )}
        </div>

        {/* Activity Log */}
        {stream.log.length > 0 && (
          <div
            style={{
              borderTop: "1px solid var(--color-border)",
              background: "var(--bg-canvas)",
            }}
          >
            <div
              onClick={() => setLogExpanded((v) => !v)}
              style={{
                display: "flex",
                alignItems: "center",
                padding: "6px 16px",
                cursor: "pointer",
                fontSize: 11,
                fontWeight: "bold",
                color: "var(--color-text-muted)",
                userSelect: "none",
              }}
            >
              <span>{logExpanded ? "\u25BC" : "\u25B6"} Activity Log</span>
              <span style={{ flex: 1 }} />
              {stream.isStreaming && (
                <span style={{ fontFamily: "monospace", fontSize: 12, color: "var(--color-text)" }}>
                  {formatTime(stream.elapsed)}
                </span>
              )}
            </div>
            {logExpanded && (
              <div
                style={{
                  maxHeight: 120,
                  overflowY: "auto",
                  padding: "0 16px 8px",
                  fontFamily: "monospace",
                  fontSize: 11,
                  lineHeight: 1.6,
                }}
              >
                {stream.log.map((entry, i) => (
                  <div
                    key={i}
                    style={{
                      color: entry.isError
                        ? "var(--color-error, #c62828)"
                        : "var(--color-text)",
                      display: "flex",
                      gap: 8,
                    }}
                  >
                    <span style={{ color: "var(--color-text-muted)", flexShrink: 0 }}>
                      [{formatTime(Math.floor(entry.timestamp / 1000))}]
                    </span>
                    <span>{entry.message}</span>
                    {stream.isStreaming && i === stream.log.length - 1 && !entry.isError && entry.phase !== "complete" && (
                      <span
                        style={{
                          display: "inline-block",
                          width: 6,
                          height: 6,
                          borderRadius: "50%",
                          background: "var(--color-accent, #1976d2)",
                          alignSelf: "center",
                          animation: "pulse 1.5s ease-in-out infinite",
                        }}
                      />
                    )}
                  </div>
                ))}
                <div ref={logEndRef} />
              </div>
            )}
          </div>
        )}

        {/* Footer / navigation */}
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
            padding: "10px 16px",
            borderTop: "1px solid var(--color-border)",
          }}
        >
          {step === 6 ? (
            <button
              onClick={onClose}
              style={primaryBtnStyle}
            >
              Close
            </button>
          ) : (
            <>
              <button
                onClick={onClose}
                style={secondaryBtnStyle}
                disabled={stream.isStreaming}
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (step === 1) goStep1to2();
                  else if (step === 2) goStep2to3();
                  else if (step === 3) goStep3to4();
                  else if (step === 4) goStep4to5();
                }}
                disabled={stream.isStreaming}
                style={primaryBtnStyle}
              >
                {getButtonLabel()}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Shared inline styles ─────────────────────────────────────────────────────

const thStyle: React.CSSProperties = {
  padding: "4px 8px",
  borderBottom: "1px solid var(--color-border)",
  textAlign: "left",
  fontWeight: "bold",
};

const tdStyle: React.CSSProperties = {
  padding: "4px 6px",
  borderBottom: "1px solid var(--color-border)",
};

const inputStyle: React.CSSProperties = {
  padding: "2px 6px",
  border: "1px solid var(--color-border)",
  borderRadius: 3,
  background: "var(--bg-canvas)",
  color: "var(--color-text)",
  fontSize: 12,
  width: "100%",
  boxSizing: "border-box",
};

const primaryBtnStyle: React.CSSProperties = {
  padding: "6px 18px",
  background: "var(--color-accent, #1976d2)",
  color: "#fff",
  border: "none",
  borderRadius: 4,
  cursor: "pointer",
  fontSize: 13,
  fontWeight: "bold",
};

const secondaryBtnStyle: React.CSSProperties = {
  padding: "6px 14px",
  background: "var(--bg-canvas)",
  color: "var(--color-text)",
  border: "1px solid var(--color-border)",
  borderRadius: 4,
  cursor: "pointer",
  fontSize: 13,
};
```

- [ ] **Step 2: Add pulse animation to index.css**

Add to the end of `frontend/src/index.css`:

```css
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
```

- [ ] **Step 3: Verify frontend builds**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds with no TypeScript errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/GenerateWizard.tsx frontend/src/index.css
git commit -m "feat: integrate SSE streaming into wizard with activity log panel"
```

---

### Task 6: Final Integration Test

**Files:** None (verification only)

- [ ] **Step 1: Run all backend tests**

Run:
```bash
cd backend && python -m pytest tests/ -v
```
Expected: All tests PASS

- [ ] **Step 2: Run frontend build**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds

- [ ] **Step 3: Commit any fixes**

If any tests or build failed, fix the issues and commit:
```bash
git add -A
git commit -m "fix: resolve integration issues from SSE progress feature"
```
