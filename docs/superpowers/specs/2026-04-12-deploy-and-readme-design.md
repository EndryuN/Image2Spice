# Deploy UX & README Polish — Design

**Date:** 2026-04-12
**Status:** Approved (pending user review of this spec)
**Scope:** Local launch UX (single terminal both OSes), in-app Exit button, `ground truth/` reorganization, `.env` hygiene, `/docs` gitignore policy, README rewrite, rough sketch of future hosted deployment.

---

## 1. Motivation

The current local-run flow on Windows spawns three terminal windows (parent `start.bat` + child `image2spice-backend` cmd + child `image2spice-frontend` cmd). Closing the parent window via the X button orphans the children. The Linux `start.sh` already runs in a single terminal with PID-tracked cleanup, so the asymmetry is Windows-only.

There is no in-app way to stop the servers — users must Ctrl+C in the launcher window or kill processes manually. The README documents the dev workflow well but lacks a polished "first-time user" path.

The repo also has hygiene issues:
- `.env` contains live API keys (currently gitignored, never committed — verified via `git log --all -- .env`).
- `ground truth/` has inconsistent capitalization, a stray loose `.png` at the root, a nested `Output/images/` subfolder, and mixes inputs and outputs in confusing ways.
- `docs/` contains both meaningful artifacts (specs, plans) and scratch material (`slides.html`, `presentation.md`) that the user does not want tracked.

This spec bundles all of these into one cohesive polish pass plus a rough deployment sketch for future hosted access.

---

## 2. Goals

- **One terminal** to run image2spice on both Windows and Linux/macOS.
- **In-app Exit button** that gracefully tears down both servers via a backend endpoint.
- **Symmetric teardown** — Ctrl+C in the launcher OR Exit button in the UI both result in zero leftover processes.
- **`ground truth/` normalized** to a clean two-folder layout (`source/`, `output/`).
- **`.env` hygiene** — live keys removed from `.env`, committed `.env.example` template added, `.env` stays gitignored.
- **`/docs` selectively gitignored** — slides/presentation untracked, `superpowers/` specs and plans remain tracked.
- **README rewritten** as a detailed first-time-user guide that documents both Windows and Linux launchers and explains stopping the app.
- **Rough deployment sketch** for hosting image2spice on a public URL with per-session isolation (future work, not implemented in this plan).

## 3. Non-Goals

- Hosted deployment is **not** implemented in this plan — only sketched in §10 as future work.
- No multi-user state, accounts, or authentication.
- No database, no server-side persistence.
- No new vision providers — `OPENAI_API_KEY` and `CLAUDE_API_KEY` remain in `.env.example` because `backend/api/routes.py` already reads them, but no provider integration changes are made here.
- No changes to the wizard pipeline, schematic editor, dictionary, or `.asc` generator.

---

## 4. Single-Terminal Launchers

### 4.1 Windows — `start.bat` rewrite

The current script uses `start "title" cmd /c ...` to spawn child terminal windows. Replace with `start /b` so backend and frontend run as **background processes inside the parent cmd**, with their stdout/stderr interleaving in the one window.

**New flow:**

1. Preserve the existing preamble: Ollama health-check, port-kill loop for ports 8000 and 5173.
2. Launch backend with `start /b` and capture its PID:
   - Use a small inline trick: `for /f "tokens=2" %%a in ('tasklist /v /fo csv ^| findstr "uvicorn"') do set BACKEND_PID=%%a` after a short `timeout /t 2`.
   - Alternatively, write a one-line Python helper invoked from the .bat that launches uvicorn and prints its PID. Pick whichever ends up cleaner during implementation.
3. Wait 2–3 seconds for backend readiness, then launch frontend the same way and capture its PID.
4. `start http://localhost:5173` to open the browser.
5. Enter a **watcher loop**:
   ```
   :waitloop
   tasklist /FI "PID eq %BACKEND_PID%" 2>nul | findstr /i "%BACKEND_PID%" >nul
   if errorlevel 1 goto cleanup
   timeout /t 1 /nobreak >nul
   goto waitloop
   ```
6. `:cleanup` — kill the frontend PID, kill anything still listening on 5173 (defense in depth), echo "Stopped.", `exit /b 0`.
7. Ctrl+C in the parent cmd jumps directly to cleanup via `if errorlevel` after the loop.

**Net result:** one cmd window, interleaved logs, clean teardown via three paths (Ctrl+C, closing the X, or the in-app Exit button → backend dies → watcher loop tears down frontend).

### 4.2 Linux/macOS — `start.sh` adjustments

`start.sh` already runs in a single terminal with `&` backgrounding and a SIGINT/SIGTERM trap. Two small additions:

1. After the existing `wait` (which currently waits for both PIDs), restructure to wait specifically on the backend PID. When `wait $BACKEND_PID` returns (because the backend was killed via `/api/shutdown` or Ctrl+C), the trap or a follow-up cleanup call kills the frontend PID and exits.
2. Make the Ollama check non-fatal (it already is via `if !`, just confirm the wording matches Windows).

The structure becomes symmetric with Windows: backend death triggers frontend cleanup, regardless of what killed the backend.

### 4.3 Cross-platform expectations

- Both scripts run in **one terminal**, with backend + frontend logs interleaved.
- Both scripts open the default browser to `http://localhost:5173` automatically.
- Both scripts respond to Ctrl+C by tearing down both servers cleanly.
- Both scripts respond to backend shutdown (via the new `/api/shutdown` endpoint) by tearing down the frontend and exiting.

---

## 5. Backend — `/api/shutdown` Endpoint

**Location:** new route in `backend/api/routes.py`, alongside the existing `/api/health`, `/api/env-keys`, `/api/llm-status`.

**Implementation sketch:**

```python
import asyncio
import os
import signal

@router.post("/shutdown")
async def shutdown():
    """Gracefully stop the backend. Called by the frontend Exit button.

    Schedules SIGTERM after the response flushes so the client receives
    a 200 before the connection drops. Uvicorn handles SIGTERM as a
    graceful shutdown, the launcher script's watcher loop notices the
    PID is gone, and the frontend is torn down too.
    """
    loop = asyncio.get_event_loop()
    loop.call_later(0.1, lambda: os.kill(os.getpid(), signal.SIGTERM))
    return {"shutting_down": True}
```

**Why SIGTERM and not `os._exit`:**
- Uvicorn handles SIGTERM as a graceful shutdown, running its lifespan teardown.
- On Linux, the launcher's `wait $BACKEND_PID` returns naturally and the cleanup trap fires.
- On Windows, the launcher's watcher loop detects the missing PID via `tasklist`.
- `os._exit` would skip lifespan teardown and may not propagate to the launcher's wait/poll cleanly.

**Why `call_later(0.1, ...)`:** lets the FastAPI response actually flush so the frontend gets `200 {"shutting_down": true}` before the socket closes. Without it the frontend sees a connection error and can't show the "stopped" UI cleanly.

**No auth on the endpoint:** the backend binds to `localhost` only and CORS is locked to `localhost:5173`, so only the local browser can reach it. This matches the rest of the API surface.

**Hosted-mode guard (future):** when the env var `IMAGE2SPICE_HOSTED=1` is set, the endpoint returns `403`. Documented here, implemented as part of the future deployment work in §11. Not included in the current plan.

**Test:** unit test in `backend/tests/test_routes.py` that mocks `os.kill` and asserts the endpoint returns `{"shutting_down": True}` and that `os.kill` is scheduled with `SIGTERM`.

---

## 6. Frontend — Exit Button

### 6.1 Placement & styling

End of `frontend/src/components/Toolbar.tsx`, after the `<LlmStatus />` component, separated by the existing vertical divider pattern.

Styled red-ish to signal a destructive action. Use a new CSS variable `--color-danger` added to `frontend/src/styles/theme.css` (with light/dark variants — e.g., `#d32f2f` light, `#ef5350` dark).

### 6.2 Behavior

Per the user requirement: **assumes the user wants to exit — no confirm dialog.**

1. Click → `apiShutdown()` called from `frontend/src/lib/api.ts`
2. On `200` response → `App.tsx` sets a `stopped` boolean state, which causes the editor area (and toolbar) to be replaced by a centered `<StoppedScreen />` message: *"image2spice has stopped. You can close this tab."*
3. On error → still set `stopped = true` (the backend may already be gone, which from the user's perspective is equivalent to "exited successfully")
4. The frontend dev server itself keeps running until the launcher's watcher loop kills it — typically within ~2 seconds of the backend dying. If the user reloads the page in that window they'll see a stale frontend with a broken API. Acceptable for v1; could add a beforeunload warning in a follow-up.

### 6.3 Wiring

**Files touched:**

- `frontend/src/lib/api.ts` — add `apiShutdown(): Promise<void>` (one-line `fetch` POST to `/api/shutdown`)
- `frontend/src/components/Toolbar.tsx` — new prop `onExit: () => void`, new red Exit button at the end
- `frontend/src/App.tsx` — new state `stopped: boolean`, new `handleExit()` that calls `apiShutdown()` then `setStopped(true)`, conditional render of `<StoppedScreen />` when `stopped`
- `frontend/src/styles/theme.css` — add `--color-danger` light + dark
- `frontend/src/components/StoppedScreen.tsx` (new) — a tiny component, ~15 lines, centered text on a full-viewport background

**Total estimated:** ~50 lines across 5 files, no new dependencies.

---

## 7. `ground truth/` Reorganization

### 7.1 Target layout

```
ground truth/
  source/         # all input images (.png, .jpg, .svg) merged here
  output/         # all .asc reference files
```

### 7.2 Migration moves (use `git mv` to preserve history)

**Into `source/`:**
- `bjtampcircuit.png` (currently at `ground truth/` root)
- `images/01_circuit.png` ... `images/08_circuit.png` (8 files)
- `Output/images/05-temperature-monitor.png` ... `Output/images/35-lm386-amplifier.jpg` (7 files)
- `Source/05-rc-circuit.svg` ... `Source/25-741-opamp-transistor-level.svg` (10 files)

**Into `output/`:**
- `Output/04_cicuit.asc`
- `Output/05-rc-circuit.asc`
- `Output/25.asc`

**Folders removed after move:** `ground truth/Source/`, `ground truth/images/`, `ground truth/Output/`, `ground truth/Output/images/`.

### 7.3 Collision check

Verified no name collisions across the four current folders. SVG names (`05-rc-circuit.svg`) and .asc names (`05-rc-circuit.asc`) share stems but differ in extension, so they coexist in their respective destinations.

### 7.4 Code references

Verified that no Python or TypeScript code references the literal path `ground truth/Source/` or `ground truth/Output/`. The only references to `ground truth` are in CLAUDE.md and the README. CLAUDE.md does not mention the subfolder names. README will be updated as part of §9.

---

## 8. `.env` Hygiene

### 8.1 Current state

`.env` (gitignored, never committed) contains live `OPENAI_API_KEY` and `CLAUDE_API_KEY` values. These keys are read by `backend/api/routes.py` lines 16–20 and exposed via `/api/env-keys`. The codebase also references `OPENROUTER_API_KEY`, which is not currently set.

### 8.2 Target state

**`.env.example` (new, tracked, committed):**

```
OPENAI_API_KEY=
CLAUDE_API_KEY=
OPENROUTER_API_KEY=
```

**`.env` (existing, gitignored, NOT tracked):** values cleared in place to match the template — same three headings, empty values. Live keys removed from disk. User regenerates and rotates via their provider dashboards.

**`.gitignore`:** `.env` line is already present and stays. No changes to gitignore for `.env` itself.

### 8.3 First-time setup

Add to README §5 (First-time setup): `cp .env.example .env` (or `copy .env.example .env` on Windows), then fill in the one provider key you want to use.

---

## 9. `/docs` Gitignore Policy

**User intent:** stop tracking `docs/slides.html` and `docs/presentation.md` (scratch material) without losing tracked specs and plans under `docs/superpowers/`.

**`.gitignore` additions:**

```
# Untrack /docs by default, but keep superpowers specs and plans
/docs/
!/docs/superpowers/
!/docs/superpowers/**
```

**`git rm --cached` operations** (one-time):

```
git rm --cached docs/slides.html docs/presentation.md
```

This untracks the two scratch files without deleting them from disk. The negation pattern keeps `docs/superpowers/specs/` and `docs/superpowers/plans/` tracked.

**Verification step in the implementation plan:** after the change, run `git ls-files docs/` and confirm only `docs/superpowers/...` paths are listed.

---

## 10. README Rewrite

### 10.1 Structure

Top-to-bottom outline:

1. **Title + 1-line pitch + screenshot** — keep current
2. **How It Works** — keep current ASCII diagram
3. **Quick Start (TL;DR)** — 3 commands max, both OSes side-by-side
4. **Prerequisites** — Python 3.10+, Node 18+, one of (Ollama / OpenRouter / OpenAI / Claude)
5. **First-time setup** *(new)* — clone, copy `.env.example` to `.env`, fill one provider key, install backend deps, install frontend deps
6. **Running the app** — three sub-sections:
   - **Windows (one terminal)** — `start.bat`, what to expect (interleaved logs, browser auto-opens, Exit button or Ctrl+C to stop)
   - **Linux/macOS (one terminal)** — `./start.sh`, `chmod +x` note, same expectations
   - **Manual (two terminals — dev mode with hot reload)** — existing `uvicorn --reload` + `npm run dev` flow, called out as the dev workflow
7. **Stopping the app** *(new)* — three ways: Exit button in toolbar, Ctrl+C in launcher terminal, kill-port fallback if wedged
8. **Usage** — keep current step list, lightly polished
9. **Configuration / Providers** — explain four providers, where to put keys (`.env` vs UI), recommended models
10. **Project structure** — keep, update for new `ground truth/` layout
11. **API endpoints** — keep, add `POST /api/shutdown`
12. **Tests** — keep
13. **Troubleshooting** — keep + add: "Exit button doesn't work" → check backend, "Frontend keeps running after Ctrl+C" → file an issue
14. **Hardware requirements** — keep
15. **Future: deploy your own** *(new, brief)* — one paragraph pointing forward to §11 of this design doc

### 10.2 Tone & length

- **Audience:** developer who has cloned a repo before but may not have used Ollama, uvicorn, or Vite specifically.
- **Every command** says **which directory to run it from**.
- **Every code block** is copy-pasteable, no placeholder values mid-command.
- **Length target:** ~350 lines (current is 217). Increase is in First-time setup, Running, Stopping, Configuration.

---

## 11. Future Work — Hosted Deployment (Sketch)

**Not implemented in this plan.** Sketched here so the path is recorded.

### 11.1 Goal

image2spice accessible at a public URL where each visitor gets their own session without interfering with others.

### 11.2 Architecture

```
                            ┌──────────────────────┐
                            │  Vercel/Cloudflare   │
   user browser  ───────►   │  Pages (frontend)    │
   (state lives here:       │  static React build  │
    image, schematic,       └──────────┬───────────┘
    API key, history)                  │
                                       │ /api/* calls
                                       ▼
                            ┌──────────────────────┐
                            │  Fly.io / Render     │
                            │  (FastAPI backend)   │
                            │  stateless container │
                            └──────────┬───────────┘
                                       │
                              ┌────────┴────────┐
                              ▼                 ▼
                         OpenRouter         OpenAI/Claude
                         (user's key)       (user's key)
```

### 11.3 "Per session" interpretation

The backend is already mostly stateless — no database, no user accounts, no server-side schematic storage. Each wizard call is `(image + form fields) → JSON`.

"Per session" therefore means **browser-side state**:
- Each visitor's React app is its own session: schematic, undo history, uploaded image, API keys all live in browser memory + `localStorage`.
- Backend is **fully stateless** — no cross-request memory, no shared globals.
- Concurrent users hit the backend simultaneously; isolation comes from the fact that requests are independent.
- No login, no accounts, no DB.

### 11.4 Platform recommendation

- **Frontend:** Cloudflare Pages or Vercel (free tier, global CDN, GitHub auto-deploy).
- **Backend:** Fly.io or Render (free tier; FastAPI in a Dockerfile; sleep-on-idle is fine since cold start is ~5s and the user explicitly clicks "Generate").
- **Vision provider:** **OpenRouter / OpenAI / Claude only** in hosted mode — Ollama is excluded (would require a paid GPU host). User pastes their own API key in the existing `LlmStatus` UI; **the server never stores keys**, they're sent per-request from the browser.

### 11.5 Changes required (for the future deployment work)

1. **Dockerfile** for backend (`python:3.11-slim`, copy `backend/`, `uvicorn main:app --host 0.0.0.0 --port 8000`).
2. **Build-time env var** `VITE_API_BASE_URL` so the frontend points at the deployed backend instead of `localhost:8000`.
3. **CORS** in `backend/main.py` — add the production frontend origin (or use a regex for preview deploys).
4. **Hide Exit button + disable `/api/shutdown`** when `IMAGE2SPICE_HOSTED=1` — exit/shutdown only makes sense in local mode.
5. **Rate limiting** on wizard endpoints (e.g., `slowapi`) since the server is public.
6. **Disable `/api/env-keys`** in hosted mode — would leak server-side key state.
7. **Health check** — `/api/health` already exists; Fly.io/Render will use it.
8. **README:** add a "Deploy your own" section pointing at a `deploy/` folder with `Dockerfile`, `fly.toml`, and a one-paragraph guide.

These items become a separate spec when the user is ready to host the app. Not in scope for the current implementation plan.

---

## 12. Implementation Order

The implementation plan (separate document) will execute these in roughly this order, parallelizing where independent:

1. **Backend `/api/shutdown`** + unit test (independent — backend only)
2. **Frontend Exit button** + `apiShutdown()` + `StoppedScreen` (independent — frontend only)
3. **`start.bat` rewrite** with watcher loop (independent — Windows only)
4. **`start.sh` adjustment** for symmetric backend-death cleanup (independent — Linux only)
5. **`ground truth/` reorg** via `git mv` (independent — file moves only)
6. **`.env` cleanup** + `.env.example` creation (independent — config only)
7. **`/docs` gitignore + git rm --cached** (independent — config only)
8. **README rewrite** (depends on 1–7 being substantively defined so the README accurately reflects them)
9. **Manual smoke test** on Windows: `start.bat`, click Exit in UI, confirm clean teardown.
10. **Manual smoke test** on Linux (or WSL): `./start.sh`, click Exit in UI, confirm clean teardown.

Items 1–7 can be parallelized via sub-agents. Items 8–10 are sequential at the end.

---

## 13. Testing

### Backend (pytest)

- New test in `backend/tests/test_routes.py`:
  - `test_shutdown_returns_shutting_down` — POST `/api/shutdown`, mock `asyncio.get_event_loop().call_later`, assert response is `{"shutting_down": True}` and that `call_later` was scheduled with `os.kill` + `SIGTERM`.

### Frontend

- No automated tests (project convention — `npm run build` is the only check).
- Run `npm run build` after the Exit button changes to confirm TypeScript compiles.
- Run `npm run lint` to confirm no new lint errors.

### Manual smoke tests

- **Windows:** double-click `start.bat`, confirm one terminal opens, browser opens to `localhost:5173`, click Exit in the toolbar, confirm both servers die and the terminal exits with no leftover `python.exe` or `node.exe` processes (`tasklist | findstr -i "uvicorn node"`).
- **Linux:** `./start.sh`, same steps using `ps aux | grep -E "uvicorn|node"` to verify cleanup.
- **Both OSes:** also test Ctrl+C in the launcher terminal as a teardown path. Same cleanup expectations.

---

## 14. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| `start /b` PID capture on Windows is fiddly (no direct equivalent of `$!`) | Fall back to a tiny Python helper that launches uvicorn and prints its PID. Pick during implementation. |
| `os.kill(SIGTERM)` on Windows may not be handled by uvicorn the same as on Linux | Test during implementation. Fallback: use `signal.CTRL_BREAK_EVENT` or `os._exit` on Windows specifically. |
| Frontend dev server (`vite`) doesn't always die cleanly on parent SIGTERM | Watcher loop kills by port (5173) as a final defense. |
| User's `.env` rotation forgotten — leaked keys from this conversation context | This spec explicitly notes the rotation step. Implementation plan adds it as a manual checklist item before any commit. |
| `git rm --cached` accidentally untracks specs/plans | Use exact paths (`docs/slides.html`, `docs/presentation.md`) — never `-r docs/`. Negation pattern in `.gitignore` is the final safety net. |

---

## 15. Open Questions

None as of approval. All scope decisions resolved during brainstorming:

- Single-terminal approach: patched batch (Option 1)
- Exit-flow plumbing: backend `/api/shutdown` + launcher watcher (Option A)
- File reorg scope: `ground truth/` only, not source code
- `.env` strategy: `.env.example` tracked, `.env` gitignored (Option A)
- `/docs` gitignore: negation pattern keeping `superpowers/` tracked (Option A)
