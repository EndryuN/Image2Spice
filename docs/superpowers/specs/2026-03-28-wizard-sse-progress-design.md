# Wizard SSE Progress Tracking — Design Spec

**Date:** 2026-03-28
**Goal:** Replace the silent "Loading..." state in the Generate Wizard with real-time SSE progress events streamed from the backend, plus an activity log panel inside the wizard modal.

---

## Problem

The Generate Wizard stalls visibly after Step 1 (Canvas) when clicking "Next". The `wizardIdentify()` call hits `POST /api/wizard/identify`, which sends the image to Ollama's Qwen3-VL 8B model. This can take 30-120+ seconds (especially on first model load), but the frontend shows only "Loading..." with no progress, elapsed time, or error detail. Users cannot tell if the system is working or frozen.

## Approach

**Per-step SSE streaming.** Each wizard step gets a companion streaming endpoint that emits phase-level progress events over Server-Sent Events. The frontend consumes these via `fetch()` + `ReadableStream` and renders them in an activity log panel inside the wizard modal. A pre-flight health check warns if Ollama is unreachable before the user starts.

---

## Backend

### New Ollama Client Method

`chat_with_vision_stream()` in `services/ollama_client.py` — same signature as `chat_with_vision()` but uses `stream: True` in the Ollama payload. It is an async generator that yields dicts. During the call it yields phase events; the final yield is the complete accumulated response text:

- Yields `{"phase": "sending", "message": "Sending to Ollama..."}` — before the HTTP call
- Yields `{"phase": "generating", "message": "AI is analyzing..."}` — when the first token arrives from the stream
- Yields `{"phase": "done_raw", "content": "<full response text>"}` — after the stream completes, with all tokens concatenated

The caller (streaming vision function) iterates over all yields, forwards phase events to the SSE stream, and uses the final `done_raw` yield to parse the JSON result. This method does not expose individual tokens to the frontend. It uses streaming solely to detect when the model starts generating vs. still loading.

### Health Check Endpoint

`GET /api/health/ollama` in `wizard_routes.py`:

- Calls `GET http://localhost:11434/api/tags` with a 5s timeout
- Checks if `qwen3-vl:8b` is in the returned model list
- Returns `{"ok": true, "model": "qwen3-vl:8b"}` on success
- Returns `{"ok": false, "error": "Cannot reach Ollama..."}` or `{"ok": false, "error": "Model qwen3-vl:8b not found..."}` on failure

### Streaming Vision Functions

`services/vision.py` gets streaming variants of each function. Each is an async generator yielding SSE event dicts:

- `identify_components_stream(image_bytes)`
- `read_directives_stream(image_bytes)`
- `describe_layout_stream(image_bytes, components)`
- `describe_wires_stream(image_bytes, components, pin_info)`

Each yields events in order:
1. `{event: "phase", data: {phase: "received", message: "Image received (N KB)"}}`
2. `{event: "phase", data: {phase: "sending", message: "Sending to Ollama..."}}`
3. `{event: "phase", data: {phase: "generating", message: "AI is analyzing..."}}`
4. `{event: "phase", data: {phase: "parsing", message: "Parsing response..."}}`
5. `{event: "done", data: <result payload>}` — the actual components/directives/layout/wires result
6. On error: `{event: "error", data: {message: "Human-readable error"}}` instead of step 5

### Streaming Wizard Endpoints

Four new endpoints in `wizard_routes.py`:

- `POST /api/wizard/identify/stream`
- `POST /api/wizard/directives/stream`
- `POST /api/wizard/layout/stream`
- `POST /api/wizard/wires/stream`

Each accepts the same `multipart/form-data` as the non-streaming variant, but returns `StreamingResponse(media_type="text/event-stream")`. The response body is the SSE event stream from the corresponding streaming vision function.

SSE wire format:
```
event: phase
data: {"phase": "received", "message": "Image received (245 KB)"}

event: phase
data: {"phase": "sending", "message": "Sending to Ollama..."}

event: phase
data: {"phase": "generating", "message": "AI is analyzing..."}

event: phase
data: {"phase": "parsing", "message": "Parsing response..."}

event: done
data: {"components": [...]}

```

On error:
```
event: error
data: {"message": "Cannot connect to Ollama at localhost:11434"}

```

### Error Mapping

The streaming endpoints catch specific exceptions and emit human-readable error events:

| Exception | Error message |
|---|---|
| `httpx.ConnectError` | "Cannot connect to Ollama at localhost:11434" |
| `httpx.ReadTimeout` | "Ollama timed out after 10 minutes — the model may be too large for available VRAM" |
| `json.JSONDecodeError` / `ValueError` from `_extract_json` | "AI returned an unparseable response. Try again." |
| Any other exception | "Unexpected error: {str(e)}" |

### Existing Endpoints

The non-streaming `POST /api/wizard/*` endpoints remain unchanged for backward compatibility and testing.

---

## Frontend

### `useWizardStream` Hook

New file: `frontend/src/hooks/useWizardStream.ts`

```ts
interface WizardLogEntry {
  timestamp: number;  // ms since step started
  phase: string;      // "received" | "sending" | "generating" | "parsing"
  message: string;
}

interface UseWizardStreamReturn {
  execute: (url: string, formData: FormData) => Promise<any>;
  log: WizardLogEntry[];
  currentPhase: string | null;
  elapsed: number;        // seconds since step started
  isStreaming: boolean;
  error: string | null;
  clearLog: () => void;
}
```

**`execute(url, formData)`:** Opens a `fetch(url, {method: "POST", body: formData})` connection, reads the response body as a `ReadableStream`, parses SSE events, appends to `log`, updates `currentPhase`. Starts an interval timer that increments `elapsed` every second. Returns a promise that resolves with the `done` event's data, or rejects with the `error` event's message.

**Log persistence:** The `log` array accumulates across multiple `execute()` calls within the same wizard session. `clearLog()` resets it (called when the wizard opens).

**SSE parsing:** Reads chunks from the stream, splits on `\n\n`, extracts `event:` and `data:` fields. Handles chunks that split across event boundaries.

### GenerateWizard.tsx Changes

**Pre-flight health check:** On mount, the component calls `GET /api/health/ollama`. If the check fails, a warning banner appears at the top of the wizard (below the step indicator, above step content). This is a non-blocking warning — the "Next" button stays enabled.

**Step transition functions:** `goStep1to2`, `goStep2to3`, `goStep3to4`, `goStep4to5` switch from calling `api.ts` functions to calling `stream.execute()` with the corresponding `/stream` endpoint URL. The existing `loading` state is replaced by `stream.isStreaming`. Error state comes from `stream.error`.

**Log panel:** Rendered between the step body content and the footer buttons. Structure:

```
┌─────────────────────────────────────────────┐
│  Step content (inputs, tables, etc.)        │
├─────────────────────────────────────────────┤
│  > Activity Log                      01:23  │
│  [00:00] Image received (245 KB)            │
│  [00:01] Sending to Ollama...               │
│  [00:03] AI is analyzing...             *   │
│  [00:47] Parsing response...                │
│  [00:47] Found 7 components                 │
├─────────────────────────────────────────────┤
│                          Cancel    Next ->  │
└─────────────────────────────────────────────┘
```

- Max height: ~120px, overflow-y scroll, auto-scrolls to bottom on new entries
- Collapsed by default. Expands automatically when streaming starts.
- Collapsible via clicking the "Activity Log" header.
- Elapsed timer (`mm:ss`) in the top-right of the log panel header. Resets per step.
- Active phase gets a pulsing dot indicator.
- Log accumulates across all steps within the wizard session.
- Monospace font for log entries. Timestamps in `--color-text-muted`. Errors in `--color-error`.
- Uses existing CSS custom properties for all styling (`--bg-canvas`, `--color-text-muted`, `--color-border`).

**"Next" button:** Shows "Loading..." replaced by the current phase message (e.g., "AI is analyzing...") while streaming. Re-enables after error so user can retry.

### api.ts

No changes. Existing non-streaming functions remain for backward compatibility.

---

## Testing

### Backend Tests

Add to `backend/tests/test_wizard_routes.py`:

- Test SSE streaming endpoints return `text/event-stream` content type
- Test that phase events arrive in correct order (mocked Ollama)
- Test error event when Ollama is unreachable
- Test `/api/health/ollama` returns correct status for reachable/unreachable Ollama

### Frontend

No unit tests (consistent with existing frontend testing strategy). Verify via `npm run build` for TypeScript compilation.

---

## File Changes

**New files:**
- `frontend/src/hooks/useWizardStream.ts`

**Modified files:**
- `backend/services/ollama_client.py` — add `chat_with_vision_stream()`
- `backend/services/vision.py` — add streaming variants of 4 vision functions
- `backend/api/wizard_routes.py` — add 4 streaming endpoints + health check
- `frontend/src/components/GenerateWizard.tsx` — use `useWizardStream`, add log panel, add pre-flight check
- `backend/tests/test_wizard_routes.py` — add streaming and health check tests

**No new dependencies.** `httpx` supports streaming, FastAPI has `StreamingResponse`, frontend uses native `fetch` + `ReadableStream`.
