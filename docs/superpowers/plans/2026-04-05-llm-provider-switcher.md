# LLM Provider Switcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users switch between local Ollama and OpenRouter for VLM calls, with a toolbar status chip and component value hints.

**Architecture:** New unified `llm_client.py` replaces direct Ollama usage. Frontend `LlmStatus.tsx` component in toolbar lets users pick provider/model/key. Provider config flows through wizard API calls as a `provider_json` form field. Value hints added as input placeholders.

**Tech Stack:** Python 3.11+, httpx, FastAPI, React 19, TypeScript 5.9

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/services/llm_client.py` | Unified LLM client (Ollama + OpenRouter) |
| Create | `backend/tests/test_llm_client.py` | Tests for both providers |
| Modify | `backend/services/vision.py` | Use llm_client, accept provider params |
| Modify | `backend/api/wizard_routes.py` | Parse provider_json, pass to vision |
| Modify | `backend/tests/test_wizard_routes.py` | Test provider_json parsing |
| Create | `frontend/src/components/LlmStatus.tsx` | Provider switcher dropdown chip |
| Modify | `frontend/src/types/schematic.ts` | Add LlmProvider type |
| Modify | `frontend/src/components/Toolbar.tsx` | Add LlmStatus to right side |
| Modify | `frontend/src/lib/api.ts` | Pass provider config in wizard calls |
| Modify | `frontend/src/components/GenerateWizard.tsx` | Accept + pass provider, add value hints |
| Modify | `frontend/src/App.tsx` | LlmProvider state, wire to Toolbar + Wizard |

---

### Task 1: Unified LLM Client

**Files:**
- Create: `backend/services/llm_client.py`
- Create: `backend/tests/test_llm_client.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_llm_client.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.llm_client import chat_with_vision


@pytest.mark.asyncio
async def test_local_provider_sends_ollama_format():
    mock_response = MagicMock()
    mock_response.json.return_value = {"message": {"content": "test response"}}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("services.llm_client.httpx.AsyncClient", return_value=mock_client):
        result = await chat_with_vision(
            model="qwen3-vl:8b",
            system_prompt="system",
            user_prompt="user",
            image_bytes=b"fake_image",
            provider="local",
        )

    assert result == "test response"
    call_args = mock_client.post.call_args
    assert "localhost:11434" in call_args[0][0]
    payload = call_args[1]["json"]
    assert payload["model"] == "qwen3-vl:8b"
    assert payload["messages"][1]["images"] is not None


@pytest.mark.asyncio
async def test_openrouter_provider_sends_openai_format():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "openrouter response"}}]
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("services.llm_client.httpx.AsyncClient", return_value=mock_client):
        result = await chat_with_vision(
            model="qwen/qwen3.6-plus:free",
            system_prompt="system",
            user_prompt="user",
            image_bytes=b"fake_image",
            provider="openrouter",
            api_key="test-key-123",
        )

    assert result == "openrouter response"
    call_args = mock_client.post.call_args
    assert "openrouter.ai" in call_args[0][0]
    headers = call_args[1]["headers"]
    assert headers["Authorization"] == "Bearer test-key-123"
    payload = call_args[1]["json"]
    # OpenAI vision format: content is a list with image_url
    user_content = payload["messages"][1]["content"]
    assert isinstance(user_content, list)
    assert user_content[1]["type"] == "image_url"


@pytest.mark.asyncio
async def test_openrouter_missing_api_key_raises():
    with pytest.raises(ValueError, match="API key"):
        await chat_with_vision(
            model="qwen/qwen3.6-plus:free",
            system_prompt="system",
            user_prompt="user",
            image_bytes=b"fake_image",
            provider="openrouter",
            api_key=None,
        )


@pytest.mark.asyncio
async def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown provider"):
        await chat_with_vision(
            model="model",
            system_prompt="system",
            user_prompt="user",
            image_bytes=b"fake_image",
            provider="azure",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_llm_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.llm_client'`

- [ ] **Step 3: Write llm_client.py**

Create `backend/services/llm_client.py`:

```python
from __future__ import annotations

import base64

import httpx

OLLAMA_BASE_URL = "http://localhost:11434"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


async def chat_with_vision(
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_bytes: bytes,
    provider: str = "local",
    api_key: str | None = None,
) -> str:
    """Send an image + text prompt to a vision model.

    Supports two providers:
    - "local": Ollama at localhost:11434 (Ollama-native format)
    - "openrouter": OpenRouter API (OpenAI-compatible format)
    """
    if provider == "local":
        return await _call_ollama(model, system_prompt, user_prompt, image_bytes)
    elif provider == "openrouter":
        if not api_key:
            raise ValueError("API key is required for OpenRouter provider")
        return await _call_openrouter(model, system_prompt, user_prompt, image_bytes, api_key)
    else:
        raise ValueError(f"Unknown provider: {provider}")


async def _call_ollama(
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_bytes: bytes,
) -> str:
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
        "stream": False,
        "options": {"temperature": 0.1},
    }
    async with httpx.AsyncClient(timeout=600.0) as client:
        resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]


async def _call_openrouter(
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_bytes: bytes,
    api_key: str,
) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                        },
                    },
                ],
            },
        ],
        "temperature": 0.1,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:5173",
        "X-Title": "image2asc",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
        )
        if resp.status_code != 200:
            raise ValueError(f"OpenRouter error ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_llm_client.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/llm_client.py backend/tests/test_llm_client.py
git commit -m "feat: add unified LLM client supporting Ollama and OpenRouter"
```

---

### Task 2: Update vision.py to Use llm_client

**Files:**
- Modify: `backend/services/vision.py`

- [ ] **Step 1: Update imports and model config**

In `backend/services/vision.py`, replace line 6:
```python
from services.ollama_client import chat_with_vision
```
with:
```python
from services.llm_client import chat_with_vision
```

Replace line 16:
```python
VISION_MODEL = "qwen3-vl:8b"
```
with:
```python
VISION_MODELS = {
    "local": "qwen3-vl:8b",
    "openrouter": "qwen/qwen3.6-plus:free",
}
```

- [ ] **Step 2: Update all four vision functions to accept provider params**

Replace `identify_components` (line 42-57):
```python
async def identify_components(
    image_bytes: bytes,
    provider: str = "local",
    api_key: str | None = None,
    model: str | None = None,
) -> list[dict]:
    """Step 2: Identify components in the image."""
    system = _load_prompt("identify_system.txt")
    user = (
        "List every component in this schematic. For each, provide:\n"
        "- type (one of: res, cap, ind, voltage, current, opamp2, opamp, npn, pnp, nmos, pmos, diode, zener)\n"
        "- instanceName (the label, e.g. R1, U1, V3)\n"
        "- value (the displayed value)\n"
        "- value2 (only for voltage sources with a second value, otherwise omit)\n\n"
        'Output as JSON array:\n[{"type": "res", "instanceName": "R1", "value": "1k"}, ...]'
    )
    vision_model = model or VISION_MODELS.get(provider, VISION_MODELS["local"])
    response = await chat_with_vision(vision_model, system, user, image_bytes, provider=provider, api_key=api_key)
    raw = _extract_json(response)
    items = raw if isinstance(raw, list) else raw.get("components", [])
    parsed = IdentifyResponse.model_validate({"components": items})
    return [c.model_dump() for c in parsed.components]
```

Replace `read_directives` (line 60-72):
```python
async def read_directives(
    image_bytes: bytes,
    provider: str = "local",
    api_key: str | None = None,
    model: str | None = None,
) -> list[str]:
    """Step 3: Read SPICE directives from the image."""
    system = _load_prompt("directives_system.txt")
    user = (
        "List every SPICE directive visible in this schematic.\n"
        'Output as a JSON array of strings:\n'
        '[".param RINP=1k PSV=15", ".tran 0.005"]'
    )
    vision_model = model or VISION_MODELS.get(provider, VISION_MODELS["local"])
    response = await chat_with_vision(vision_model, system, user, image_bytes, provider=provider, api_key=api_key)
    raw = _extract_json(response)
    items = raw if isinstance(raw, list) else raw.get("directives", [])
    parsed = DirectivesResponse.model_validate({"directives": items})
    return parsed.directives
```

Replace `describe_layout` (line 75-91):
```python
async def describe_layout(
    image_bytes: bytes,
    components: list[dict],
    provider: str = "local",
    api_key: str | None = None,
    model: str | None = None,
) -> list[dict]:
    """Step 4: Describe spatial layout."""
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
    vision_model = model or VISION_MODELS.get(provider, VISION_MODELS["local"])
    response = await chat_with_vision(vision_model, system, user, image_bytes, provider=provider, api_key=api_key)
    raw = _extract_json(response)
    items = raw if isinstance(raw, list) else raw.get("layout", [])
    parsed = LayoutResponse.model_validate({"layout": items})
    return [item.model_dump() for item in parsed.layout]
```

Replace `describe_wires` (line 94-119):
```python
async def describe_wires(
    image_bytes: bytes,
    components: list[dict],
    pin_info: dict,
    provider: str = "local",
    api_key: str | None = None,
    model: str | None = None,
) -> dict:
    """Step 5: Describe wire connections."""
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
    vision_model = model or VISION_MODELS.get(provider, VISION_MODELS["local"])
    response = await chat_with_vision(vision_model, system, user, image_bytes, provider=provider, api_key=api_key)
    raw = _extract_json(response)
    if not isinstance(raw, dict):
        raw = {"connections": [], "grounds": [], "labels": []}
    parsed = WiresResponse.model_validate(raw)
    return parsed.model_dump(by_alias=True)
```

- [ ] **Step 3: Run existing vision tests**

Run: `cd backend && python -m pytest tests/test_vision.py -v`
Expected: All PASS (they test `_extract_json` which is unchanged)

- [ ] **Step 4: Commit**

```bash
git add backend/services/vision.py
git commit -m "feat: update vision.py to use unified llm_client with provider params"
```

---

### Task 3: Update wizard_routes.py to Parse Provider Config

**Files:**
- Modify: `backend/api/wizard_routes.py`
- Modify: `backend/tests/test_wizard_routes.py`

- [ ] **Step 1: Add helper to parse provider config**

In `backend/api/wizard_routes.py`, add after the `_require_image` function (after line 27):

```python
def _parse_provider(provider_json: str) -> tuple[str, str | None, str | None]:
    """Parse provider_json form field into (provider, api_key, model)."""
    config = json.loads(provider_json) if provider_json else {}
    return (
        config.get("provider", "local"),
        config.get("apiKey"),
        config.get("model"),
    )
```

- [ ] **Step 2: Update all four endpoints to accept and use provider_json**

Replace `wizard_identify` (lines 30-38):
```python
@router.post("/identify")
async def wizard_identify(
    file: UploadFile = File(...),
    provider_json: str = Form("{}"),
):
    _require_image(file)
    image_bytes = await file.read()
    provider, api_key, model = _parse_provider(provider_json)
    try:
        components = await identify_components(image_bytes, provider=provider, api_key=api_key, model=model)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(400, detail={"error": "Component identification failed", "details": str(exc)})
    return {"components": components}
```

Replace `wizard_directives` (lines 41-49):
```python
@router.post("/directives")
async def wizard_directives(
    file: UploadFile = File(...),
    provider_json: str = Form("{}"),
):
    _require_image(file)
    image_bytes = await file.read()
    provider, api_key, model = _parse_provider(provider_json)
    try:
        directives = await read_directives(image_bytes, provider=provider, api_key=api_key, model=model)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(400, detail={"error": "Directive reading failed", "details": str(exc)})
    return {"directives": directives}
```

Replace `wizard_layout` (lines 52-77):
```python
@router.post("/layout")
async def wizard_layout(
    file: UploadFile = File(...),
    components_json: str = Form(""),
    provider_json: str = Form("{}"),
):
    _require_image(file)
    image_bytes = await file.read()
    components = json.loads(components_json) if components_json else []
    provider, api_key, model = _parse_provider(provider_json)

    try:
        layout_desc = await describe_layout(image_bytes, components, provider=provider, api_key=api_key, model=model)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(400, detail={"error": "Layout description failed", "details": str(exc)})

    dictionary = _load_dictionary()
    comp_sizes = {}
    for comp_id, comp_data in dictionary["components"].items():
        bounds = comp_data.get("geometry", {}).get("bounds")
        comp_sizes[comp_id] = {
            "width": comp_data["symbol"]["width"],
            "height": comp_data["symbol"]["height"],
            "bounds": bounds,
        }

    positions = compute_layout(layout_desc, comp_sizes)
    return {"layout": layout_desc, "positions": positions}
```

Replace `wizard_wires` (lines 80-141):
```python
@router.post("/wires")
async def wizard_wires(
    file: UploadFile = File(...),
    components_json: str = Form(""),
    positions_json: str = Form(""),
    provider_json: str = Form("{}"),
):
    _require_image(file)
    image_bytes = await file.read()
    components = json.loads(components_json) if components_json else []
    positions = json.loads(positions_json) if positions_json else {}
    provider, api_key, model = _parse_provider(provider_json)

    dictionary = _load_dictionary()
    pin_defs = {}
    component_bounds = {}
    for comp_id, comp_data in dictionary["components"].items():
        pin_defs[comp_id] = comp_data.get("pins", [])
        bounds = comp_data.get("geometry", {}).get("bounds")
        if bounds:
            component_bounds[comp_id] = bounds

    try:
        wire_desc = await describe_wires(image_bytes, components, pin_defs, provider=provider, api_key=api_key, model=model)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(400, detail={"error": "Wire tracing failed", "details": str(exc)})

    # Normalize pin names in wire descriptions
    for conn in wire_desc.get("connections", []):
        for key in ("from", "to"):
            ep = conn.get(key)
            if ep:
                comp_name = ep["component"]
                comp_entry = next((c for c in components if c["instanceName"] == comp_name), None)
                if comp_entry:
                    ep["pin"] = normalize_pin(comp_entry["type"], ep["pin"])

    for gnd in wire_desc.get("grounds", []):
        comp_entry = next((c for c in components if c["instanceName"] == gnd["component"]), None)
        if comp_entry:
            gnd["pin"] = normalize_pin(comp_entry["type"], gnd["pin"])

    for lbl in wire_desc.get("labels", []):
        comp_entry = next((c for c in components if c["instanceName"] == lbl["component"]), None)
        if comp_entry:
            lbl["pin"] = normalize_pin(comp_entry["type"], lbl["pin"])

    comp_map = {}
    for comp in components:
        name = comp["instanceName"]
        if name in positions:
            comp_map[name] = {
                "x": positions[name]["x"],
                "y": positions[name]["y"],
                "type": comp["type"],
            }

    wire_result = compute_wires(comp_map, pin_defs, wire_desc, component_bounds)

    return {
        "wire_descriptions": wire_desc,
        "wires": [{"x1": w[0], "y1": w[1], "x2": w[2], "y2": w[3]} for w in wire_result.wires],
        "flags": wire_result.flags,
    }
```

- [ ] **Step 3: Run existing wizard route tests**

Run: `cd backend && python -m pytest tests/test_wizard_routes.py -v`
Expected: All 4 tests PASS (existing tests don't send provider_json, so default "{}" is used)

- [ ] **Step 4: Commit**

```bash
git add backend/api/wizard_routes.py
git commit -m "feat: accept provider_json in wizard endpoints for LLM switching"
```

---

### Task 4: Frontend — LlmProvider Type + API Changes

**Files:**
- Modify: `frontend/src/types/schematic.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add LlmProvider type**

Append to the end of `frontend/src/types/schematic.ts`:

```typescript
export interface LlmProvider {
  provider: "local" | "openrouter";
  model: string;
  apiKey?: string;
}
```

- [ ] **Step 2: Update api.ts wizard functions to accept providerConfig**

Replace all four wizard functions in `frontend/src/lib/api.ts`:

```typescript
export async function wizardIdentify(file: File, providerConfig?: LlmProvider): Promise<{ components: WizardComponent[] }> {
  const formData = new FormData();
  formData.append("file", file);
  if (providerConfig) formData.append("provider_json", JSON.stringify(providerConfig));
  const resp = await fetch(`${BASE_URL}/wizard/identify`, { method: "POST", body: formData });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail?.error ?? body?.detail ?? `Identify failed: ${resp.status}`);
  }
  return resp.json();
}

export async function wizardDirectives(file: File, providerConfig?: LlmProvider): Promise<{ directives: string[] }> {
  const formData = new FormData();
  formData.append("file", file);
  if (providerConfig) formData.append("provider_json", JSON.stringify(providerConfig));
  const resp = await fetch(`${BASE_URL}/wizard/directives`, { method: "POST", body: formData });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail?.error ?? body?.detail ?? `Directives failed: ${resp.status}`);
  }
  return resp.json();
}

export async function wizardLayout(
  file: File,
  components: WizardComponent[],
  providerConfig?: LlmProvider,
): Promise<{ positions: Record<string, { x: number; y: number }> }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("components_json", JSON.stringify(components));
  if (providerConfig) formData.append("provider_json", JSON.stringify(providerConfig));
  const resp = await fetch(`${BASE_URL}/wizard/layout`, { method: "POST", body: formData });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail?.error ?? body?.detail ?? `Layout failed: ${resp.status}`);
  }
  return resp.json();
}

export async function wizardWires(
  file: File,
  components: WizardComponent[],
  positions: Record<string, { x: number; y: number }>,
  providerConfig?: LlmProvider,
): Promise<WizardWireResult> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("components_json", JSON.stringify(components));
  formData.append("positions_json", JSON.stringify(positions));
  if (providerConfig) formData.append("provider_json", JSON.stringify(providerConfig));
  const resp = await fetch(`${BASE_URL}/wizard/wires`, { method: "POST", body: formData });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail?.error ?? body?.detail ?? `Wires failed: ${resp.status}`);
  }
  return resp.json();
}
```

Add the import at the top of `api.ts`:
```typescript
import type { Dictionary, WizardComponent, WizardWireResult, LlmProvider } from "../types/schematic";
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds (api.ts changes are backwards compatible — providerConfig is optional)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/schematic.ts frontend/src/lib/api.ts
git commit -m "feat: add LlmProvider type and pass provider config in wizard API calls"
```

---

### Task 5: LlmStatus Component

**Files:**
- Create: `frontend/src/components/LlmStatus.tsx`

- [ ] **Step 1: Create LlmStatus.tsx**

Create `frontend/src/components/LlmStatus.tsx`:

```tsx
import { useState, useRef, useEffect } from "react";
import type { LlmProvider } from "../types/schematic";

interface LlmStatusProps {
  provider: LlmProvider;
  onProviderChange: (provider: LlmProvider) => void;
}

export function LlmStatus({ provider, onProviderChange }: LlmStatusProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const label =
    provider.provider === "local"
      ? `Local: ${provider.model}`
      : `OpenRouter: ${provider.model.split("/").pop()}`;

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          padding: "4px 10px",
          border: "1px solid var(--color-border)",
          borderRadius: 12,
          background: provider.provider === "openrouter" ? "var(--color-accent, #1976d2)" : "var(--bg-canvas)",
          color: provider.provider === "openrouter" ? "#fff" : "var(--color-text)",
          cursor: "pointer",
          fontSize: 11,
          whiteSpace: "nowrap",
        }}
      >
        {label} ▾
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            right: 0,
            marginTop: 4,
            padding: 12,
            background: "var(--bg-panel)",
            border: "1px solid var(--color-border)",
            borderRadius: 6,
            boxShadow: "0 4px 16px rgba(0,0,0,0.25)",
            zIndex: 3000,
            width: 280,
            display: "flex",
            flexDirection: "column",
            gap: 10,
            fontSize: 12,
          }}
        >
          <div>
            <div style={{ marginBottom: 4, fontWeight: "bold", color: "var(--color-text)" }}>Provider</div>
            <label style={{ marginRight: 16, cursor: "pointer", color: "var(--color-text)" }}>
              <input
                type="radio"
                name="provider"
                checked={provider.provider === "local"}
                onChange={() =>
                  onProviderChange({ provider: "local", model: "qwen3-vl:8b" })
                }
              />{" "}
              Local (Ollama)
            </label>
            <label style={{ cursor: "pointer", color: "var(--color-text)" }}>
              <input
                type="radio"
                name="provider"
                checked={provider.provider === "openrouter"}
                onChange={() =>
                  onProviderChange({
                    provider: "openrouter",
                    model: "qwen/qwen3.6-plus:free",
                    apiKey: provider.apiKey ?? "",
                  })
                }
              />{" "}
              OpenRouter
            </label>
          </div>

          <div>
            <div style={{ marginBottom: 4, fontWeight: "bold", color: "var(--color-text)" }}>Model</div>
            <input
              value={provider.model}
              onChange={(e) =>
                onProviderChange({ ...provider, model: e.target.value })
              }
              style={{
                width: "100%",
                padding: "4px 8px",
                border: "1px solid var(--color-border)",
                borderRadius: 4,
                background: "var(--bg-canvas)",
                color: "var(--color-text)",
                fontSize: 12,
                boxSizing: "border-box",
              }}
            />
          </div>

          {provider.provider === "openrouter" && (
            <div>
              <div style={{ marginBottom: 4, fontWeight: "bold", color: "var(--color-text)" }}>API Key</div>
              <input
                type="password"
                value={provider.apiKey ?? ""}
                onChange={(e) =>
                  onProviderChange({ ...provider, apiKey: e.target.value })
                }
                placeholder="sk-or-..."
                style={{
                  width: "100%",
                  padding: "4px 8px",
                  border: "1px solid var(--color-border)",
                  borderRadius: 4,
                  background: "var(--bg-canvas)",
                  color: "var(--color-text)",
                  fontSize: 12,
                  boxSizing: "border-box",
                }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/LlmStatus.tsx
git commit -m "feat: add LlmStatus provider switcher component"
```

---

### Task 6: Wire LlmStatus into Toolbar + App + GenerateWizard

**Files:**
- Modify: `frontend/src/components/Toolbar.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/GenerateWizard.tsx`

- [ ] **Step 1: Update Toolbar.tsx**

Add import at top of `frontend/src/components/Toolbar.tsx`:
```typescript
import { LlmStatus } from "./LlmStatus";
import type { LlmProvider } from "../types/schematic";
```

Add two new props to `ToolbarProps` interface:
```typescript
  llmProvider: LlmProvider;
  onProviderChange: (provider: LlmProvider) => void;
```

Add them to the destructured props in the function signature.

Add `<LlmStatus>` as the last child inside the toolbar div, before the closing `</div>`, with a spacer:
```tsx
      <div style={{ flex: 1 }} />
      <LlmStatus provider={llmProvider} onProviderChange={onProviderChange} />
```

- [ ] **Step 2: Update App.tsx**

Add import for `LlmProvider`:
```typescript
import type { Dictionary, LlmProvider } from "./types/schematic";
```

Add state after the other state declarations (after line 25):
```typescript
  const [llmProvider, setLlmProvider] = useState<LlmProvider>({ provider: "local", model: "qwen3-vl:8b" });
```

Pass to `Toolbar` (add after `onToggleTheme={toggleTheme}`):
```typescript
        llmProvider={llmProvider}
        onProviderChange={setLlmProvider}
```

Pass to `GenerateWizard` (add after `dictionary={dictionary}`):
```typescript
          llmProvider={llmProvider}
```

- [ ] **Step 3: Update GenerateWizard.tsx**

Add `LlmProvider` to the import from types:
```typescript
import type { Dictionary, WizardComponent, LlmProvider } from "../types/schematic";
```

Add to `GenerateWizardProps` interface:
```typescript
  llmProvider: LlmProvider;
```

Add to destructured props:
```typescript
  llmProvider,
```

Update all four wizard API calls to pass `llmProvider`:

In `goStep1to2` (the `wizardIdentify` call):
```typescript
      const result = await wizardIdentify(imageFile, llmProvider);
```

In `goStep2to3` (the `wizardDirectives` call):
```typescript
      const result = await wizardDirectives(imageFile, llmProvider);
```

In `goStep3to4` (the `wizardLayout` call):
```typescript
      const result = await wizardLayout(imageFile, confirmed, llmProvider);
```

In `goStep4to5` (the `wizardWires` call):
```typescript
      const result = await wizardWires(imageFile, confirmed, positions, llmProvider);
```

Update the `useCallback` dependency arrays to include `llmProvider`.

- [ ] **Step 4: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Toolbar.tsx frontend/src/App.tsx frontend/src/components/GenerateWizard.tsx
git commit -m "feat: wire LLM provider switcher through toolbar, app, and wizard"
```

---

### Task 7: Component Value Hints

**Files:**
- Modify: `frontend/src/components/GenerateWizard.tsx`

- [ ] **Step 1: Add VALUE_HINTS map**

In `frontend/src/components/GenerateWizard.tsx`, add after the `type Step = ...` line (after line 26):

```typescript
const VALUE_HINTS: Record<string, string> = {
  res: "e.g. 10k, 1M, 100, {param}",
  cap: "e.g. 100n, 1u, 10p",
  ind: "e.g. 10u, 1m, 100n",
  voltage: "e.g. 5, AC 1, PULSE(...), {param}",
  current: "e.g. 1m, AC 0.01",
  diode: "e.g. 1N4148, D",
  zener: "e.g. 1N4733, D",
  npn: "e.g. 2N2222, BC547",
  pnp: "e.g. 2N3906, BC557",
  nmos: "e.g. 2N7000, IRF540",
  pmos: "e.g. IRF9540",
  opamp: "e.g. LM358, UniversalOpamp2",
  opamp2: "e.g. LM358, ADA4627",
};
```

- [ ] **Step 2: Add placeholder to Value input**

Find the Value `<input>` in the component table (the one with `value={comp.value}` and `onChange={(e) => updateComp(idx, { value: e.target.value })}`).

Add the `placeholder` attribute:
```tsx
                          <input
                            value={comp.value}
                            placeholder={VALUE_HINTS[comp.type] ?? ""}
                            onChange={(e) => updateComp(idx, { value: e.target.value })}
                            style={inputStyle}
                          />
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/GenerateWizard.tsx
git commit -m "feat: add component value placeholder hints in wizard"
```

---

### Task 8: Full Test Suite + Build Verification

**Files:** None (verification only)

- [ ] **Step 1: Run all backend tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests PASS (should be 101+ tests)

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit if any fixups needed**

If any tests fail due to integration issues, fix and commit:
```bash
git add -A
git commit -m "fix: resolve integration issues from LLM provider switcher"
```
