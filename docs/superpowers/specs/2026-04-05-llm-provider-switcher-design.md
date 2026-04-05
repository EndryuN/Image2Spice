# LLM Provider Switcher + Component Value Hints

**Date:** 2026-04-05
**Status:** Approved
**Goal:** Let users switch between local Ollama and OpenRouter for VLM calls, and show value hints in the wizard.

---

## Problem

- Local Ollama with qwen3-vl:8b takes 60-400+ seconds per wizard step due to VRAM loading and slow inference
- OpenRouter offers free vision models (Qwen 3.6 Plus) that respond in ~5 seconds
- Users need a way to switch providers without code changes
- Component value inputs in the wizard have no guidance on expected formats

## Approach

Add a provider switcher UI to the toolbar and a unified LLM client on the backend. Add placeholder hints to the value input in the wizard's Identify step.

**Files changed:** `llm_client.py` (new), `vision.py`, `wizard_routes.py`, `App.tsx`, `Toolbar.tsx`, `LlmStatus.tsx` (new), `GenerateWizard.tsx`, `api.ts`, `schematic.ts`
**Files untouched:** `ollama_client.py` (kept for backwards compat), `layout.py`, `wire_router.py`, `asc_generator.py`, `schemas.py`

---

## Section 1: Unified LLM Client

### New file: `backend/services/llm_client.py`

Replaces direct use of `ollama_client.py` in vision.py. Supports two providers.

```python
async def chat_with_vision(
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_bytes: bytes,
    provider: str = "local",        # "local" or "openrouter"
    api_key: str | None = None,     # required for openrouter
) -> str:
```

**Local provider (Ollama):**
- Same as current `ollama_client.chat_with_vision`
- POST to `http://localhost:11434/api/chat`
- Ollama-native format: `images: [base64]` in the user message
- Timeout: 600s

**OpenRouter provider:**
- POST to `https://openrouter.ai/api/v1/chat/completions`
- OpenAI-compatible format:
  - `Authorization: Bearer {api_key}`
  - `HTTP-Referer: http://localhost:5173` (required by OpenRouter)
  - `X-Title: image2asc` (optional, for OpenRouter dashboard)
  - Messages use OpenAI vision format: `content: [{type: "image_url", image_url: {url: "data:image/png;base64,..."}}]`
- `temperature: 0.1`, `stream: false`
- Timeout: 120s (much faster than local)
- On non-200: raise `ValueError` with response body for structured error handling

**Default models:**
- Local: `qwen3-vl:8b`
- OpenRouter: `qwen/qwen3.6-plus:free`

### Changes to vision.py

Replace import:
```python
# Old: from services.ollama_client import chat_with_vision
# New: from services.llm_client import chat_with_vision
```

Each vision function gains `provider` and `api_key` parameters, passed through to `chat_with_vision`:

```python
async def identify_components(image_bytes, provider="local", api_key=None) -> list[dict]:
async def read_directives(image_bytes, provider="local", api_key=None) -> list[str]:
async def describe_layout(image_bytes, components, provider="local", api_key=None) -> list[dict]:
async def describe_wires(image_bytes, components, pin_info, provider="local", api_key=None) -> dict:
```

The VISION_MODEL constant becomes provider-dependent:
```python
VISION_MODELS = {
    "local": "qwen3-vl:8b",
    "openrouter": "qwen/qwen3.6-plus:free",
}
```

If a custom model is provided, use it. Otherwise fall back to the default for the provider.

### Changes to wizard_routes.py

Each wizard endpoint accepts an optional `provider_json` form field:

```python
provider_json: str = Form("{}")
```

Parsed to extract `provider`, `api_key`, and `model`. Passed to vision functions.

```python
provider_config = json.loads(provider_json) if provider_json else {}
provider = provider_config.get("provider", "local")
api_key = provider_config.get("apiKey")
model = provider_config.get("model")
```

---

## Section 2: Frontend Provider Switcher

### New component: `LlmStatus.tsx`

A small clickable chip in the toolbar's right side. Displays current provider + model.

**Collapsed state (chip):**
```
[Local: qwen3-vl:8b ▾]
```

**Expanded state (dropdown):**
```
┌─────────────────────────────┐
│ Provider:                   │
│ (●) Local   ( ) OpenRouter  │
│                             │
│ Model: [qwen3-vl:8b      ] │
│                             │
│ [if OpenRouter:]            │
│ API Key: [•••••••••••     ] │
└─────────────────────────────┘
```

- Radio buttons for provider selection
- Model input (text field, defaults to appropriate model for provider)
- API key input (password field, only shown for OpenRouter)
- Dropdown closes on click-outside

**Props:**
```typescript
interface LlmStatusProps {
  provider: LlmProvider;
  onProviderChange: (provider: LlmProvider) => void;
}

interface LlmProvider {
  provider: "local" | "openrouter";
  model: string;
  apiKey?: string;
}
```

### Changes to App.tsx

- New state: `const [llmProvider, setLlmProvider] = useState<LlmProvider>({ provider: "local", model: "qwen3-vl:8b" })`
- Pass `llmProvider` and `setLlmProvider` to `Toolbar` (for `LlmStatus`)
- Pass `llmProvider` to `GenerateWizard`

### Changes to Toolbar.tsx

- Accept `llmProvider` and `onProviderChange` props
- Render `<LlmStatus>` on the right side of the toolbar (with `marginLeft: "auto"`)

### Changes to GenerateWizard.tsx

- Accept `llmProvider` prop
- Pass it to each `wizard*()` API call

### Changes to api.ts

Each wizard function includes `providerConfig` in the form data:

```typescript
export async function wizardIdentify(file: File, providerConfig?: LlmProvider) {
  const formData = new FormData();
  formData.append("file", file);
  if (providerConfig) formData.append("provider_json", JSON.stringify(providerConfig));
  ...
}
```

Same pattern for `wizardDirectives`, `wizardLayout`, `wizardWires`.

### Changes to types/schematic.ts

Add `LlmProvider` type:

```typescript
export interface LlmProvider {
  provider: "local" | "openrouter";
  model: string;
  apiKey?: string;
}
```

---

## Section 3: Component Value Hints

Add `placeholder` attribute to the Value input in the wizard's Identify step.

**Hint map (in GenerateWizard.tsx):**

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

Applied to the Value `<input>` in the component table:
```tsx
<input
  value={comp.value}
  placeholder={VALUE_HINTS[comp.type] ?? ""}
  onChange={...}
/>
```

---

## Testing Strategy

- **llm_client.py**: Unit tests for both providers. Mock httpx calls. Verify Ollama payload format vs OpenRouter payload format. Test missing API key error for OpenRouter.
- **vision.py**: Existing tests still pass (they test `_extract_json` which is unchanged). Add test that provider/api_key params are accepted.
- **wizard_routes.py**: Test that `provider_json` form field is parsed correctly. Existing image-rejection tests still pass.
- **Frontend**: `npm run build` verifies TypeScript compilation.

## Out of Scope

- API key persistence (localStorage, cookies, etc.)
- Multiple provider presets
- Model capability validation
- Cost estimation for paid OpenRouter models
- Streaming responses
