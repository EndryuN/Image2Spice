# Deploy UX & README Polish — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make image2spice runnable in a single terminal on both Windows and Linux/macOS, add an in-app Exit button that gracefully tears down both servers, normalize `ground truth/`, clean `.env` hygiene, untrack scratch docs, and rewrite the README as a detailed first-time-user guide.

**Architecture:** Backend gains a `POST /api/shutdown` endpoint that signals SIGTERM to itself after the response flushes. Both `start.bat` and `start.sh` run backend + frontend as backgrounded processes inside the parent terminal with a watcher loop that detects backend death and tears down the frontend. The frontend toolbar gains a red Exit button that calls `/api/shutdown` and shows a "stopped" screen. Repo hygiene: `.env.example` template tracked, `.env` gitignored, `ground truth/` flattened to `source/` and `output/`, `/docs/` untracked except `superpowers/`.

**Tech Stack:** FastAPI (backend), React 19 + Vite (frontend), pytest (backend tests), Windows .bat + bash .sh launchers.

**Spec:** `docs/superpowers/specs/2026-04-12-deploy-and-readme-design.md`

---

## File Structure

**Files to create:**
- `frontend/src/components/StoppedScreen.tsx` — full-viewport "stopped" message
- `.env.example` — three-heading template (committed)
- `docs/superpowers/plans/2026-04-12-deploy-and-readme-polish.md` — this plan

**Files to modify:**
- `backend/api/routes.py` — add `/api/shutdown` endpoint
- `backend/tests/test_routes.py` — add unit test for `/api/shutdown`
- `frontend/src/lib/api.ts` — add `apiShutdown()` helper
- `frontend/src/components/Toolbar.tsx` — add red Exit button + `onExit` prop
- `frontend/src/App.tsx` — add `stopped` state + `handleExit`, conditional render of `<StoppedScreen />`
- `frontend/src/styles/theme.css` — add `--color-danger` light/dark
- `start.bat` — rewrite for single-terminal + watcher loop
- `start.sh` — small adjustment for symmetric backend-death cleanup
- `.env` — clear values, keep three headings (gitignored — done locally only, NOT committed)
- `.gitignore` — add `/docs/` negation pattern keeping `superpowers/` tracked
- `README.md` — full rewrite per spec §10

**File moves (via `git mv` to preserve history):**
- `ground truth/Source/*.svg` → `ground truth/source/`
- `ground truth/images/*.png` → `ground truth/source/`
- `ground truth/Output/images/*` → `ground truth/source/`
- `ground truth/bjtampcircuit.png` → `ground truth/source/bjtampcircuit.png`
- `ground truth/Output/*.asc` → `ground truth/output/`
- `Screenshot 2026-04-12 035429.png` → `app-screenshot.png`

**Files to untrack (via `git rm --cached`):**
- `docs/slides.html`
- `docs/presentation.md`

---

## Task 1: Backend `/api/shutdown` endpoint

**Files:**
- Modify: `backend/api/routes.py`
- Modify: `backend/tests/test_routes.py`

- [ ] **Step 1: Read the existing `routes.py` to understand its structure**

Read `backend/api/routes.py` and confirm it already imports `os`, has `_ENV_KEYS` defined, and uses `router = APIRouter(prefix="/api")`.

- [ ] **Step 2: Read the existing `test_routes.py` to follow its test patterns**

Read `backend/tests/test_routes.py`. Note whether it uses `TestClient` or `httpx.AsyncClient`, and how existing tests for `/api/health` or `/api/env-keys` are structured. Mirror that pattern in step 4.

- [ ] **Step 3: Write the failing test**

Add to `backend/tests/test_routes.py` (append at the end of the file):

```python
def test_shutdown_returns_shutting_down(monkeypatch):
    """POST /api/shutdown returns the shutdown signal and schedules SIGTERM."""
    from fastapi.testclient import TestClient
    from main import app

    scheduled = []

    def fake_call_later(delay, callback):
        scheduled.append((delay, callback))

    import asyncio
    monkeypatch.setattr(
        asyncio,
        "get_event_loop",
        lambda: type("FakeLoop", (), {"call_later": staticmethod(fake_call_later)})(),
    )

    client = TestClient(app)
    response = client.post("/api/shutdown")

    assert response.status_code == 200
    assert response.json() == {"shutting_down": True}
    assert len(scheduled) == 1
    delay, _callback = scheduled[0]
    assert delay == 0.1
```

- [ ] **Step 4: Run test to verify it fails**

```bash
cd backend
python -m pytest tests/test_routes.py::test_shutdown_returns_shutting_down -v
```

Expected: FAIL with `404 Not Found` (endpoint doesn't exist yet).

- [ ] **Step 5: Implement the endpoint**

Add to `backend/api/routes.py`:

1. Add imports near the top (after existing imports):

```python
import asyncio
import signal
```

2. Add at the end of the file (after the last existing route):

```python
@router.post("/shutdown")
async def shutdown():
    """Gracefully stop the backend. Called by the frontend Exit button.

    Schedules SIGTERM after the response flushes so the client receives
    a 200 before the connection drops. Uvicorn handles SIGTERM as a
    graceful shutdown; the launcher script's watcher loop notices the
    PID is gone and tears down the frontend.
    """
    loop = asyncio.get_event_loop()
    loop.call_later(0.1, lambda: os.kill(os.getpid(), signal.SIGTERM))
    return {"shutting_down": True}
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd backend
python -m pytest tests/test_routes.py::test_shutdown_returns_shutting_down -v
```

Expected: PASS.

- [ ] **Step 7: Run the full backend test suite to confirm nothing broke**

```bash
cd backend
python -m pytest tests/ -v
```

Expected: all tests pass (the new test plus all previously passing tests).

- [ ] **Step 8: Commit**

```bash
git add backend/api/routes.py backend/tests/test_routes.py
git commit -m "feat(backend): add /api/shutdown endpoint for in-app exit

Schedules SIGTERM after response flushes so uvicorn shuts down
gracefully and the launcher's watcher loop can tear down the frontend."
```

---

## Task 2: Frontend `apiShutdown()` helper

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Read `api.ts` to understand the existing helper pattern**

Read `frontend/src/lib/api.ts`. Note how existing functions structure their `fetch` calls, what base URL they use, and how they handle errors.

- [ ] **Step 2: Add the `apiShutdown` helper**

Append to `frontend/src/lib/api.ts`:

```typescript
export async function apiShutdown(): Promise<void> {
  await fetch("/api/shutdown", { method: "POST" });
}
```

If the file uses an explicit base URL constant (e.g., `API_BASE`), use that instead of the bare `/api/shutdown` path — match the existing pattern from the file you read in Step 1.

- [ ] **Step 3: Verify TypeScript still compiles**

```bash
cd frontend
npm run build
```

Expected: build succeeds with no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(frontend): add apiShutdown helper"
```

---

## Task 3: Frontend `StoppedScreen` component

**Files:**
- Create: `frontend/src/components/StoppedScreen.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/StoppedScreen.tsx`:

```typescript
export function StoppedScreen() {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--bg-app)",
        color: "var(--color-text)",
        fontFamily: "system-ui, sans-serif",
        gap: 16,
      }}
    >
      <h1 style={{ margin: 0, fontSize: 32 }}>image2spice has stopped</h1>
      <p style={{ margin: 0, opacity: 0.7 }}>You can close this tab.</p>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript still compiles**

```bash
cd frontend
npm run build
```

Expected: build succeeds with no new errors.

If `--bg-app` is not the correct variable name in `theme.css`, replace it with `--bg-base` or whatever the body background variable is — read `frontend/src/styles/theme.css` to confirm before substituting.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/StoppedScreen.tsx
git commit -m "feat(frontend): add StoppedScreen component"
```

---

## Task 4: Add `--color-danger` to theme.css

**Files:**
- Modify: `frontend/src/styles/theme.css`

- [ ] **Step 1: Read `theme.css` to understand the variable structure**

Read `frontend/src/styles/theme.css`. Note where light-mode variables are defined (likely under `:root` or `[data-theme="light"]`) and where dark-mode variables are defined (likely under `[data-theme="dark"]`).

- [ ] **Step 2: Add `--color-danger` to both themes**

In the light-mode block, add:

```css
--color-danger: #d32f2f;
--color-danger-hover: #b71c1c;
```

In the dark-mode block, add:

```css
--color-danger: #ef5350;
--color-danger-hover: #f44336;
```

Place each pair next to other color variables in the same block — match the existing variable ordering convention.

- [ ] **Step 3: Verify build still passes**

```bash
cd frontend
npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/styles/theme.css
git commit -m "feat(frontend): add --color-danger theme variable"
```

---

## Task 5: Add Exit button to Toolbar

**Files:**
- Modify: `frontend/src/components/Toolbar.tsx`

- [ ] **Step 1: Add `onExit` to `ToolbarProps`**

In `frontend/src/components/Toolbar.tsx`, modify the `ToolbarProps` interface to add:

```typescript
onExit: () => void;
```

Place it as the last property of the interface, after `onProviderChange`.

- [ ] **Step 2: Add `onExit` to the destructured props**

In the `Toolbar` function signature, add `onExit` to the destructured parameters list (last item).

- [ ] **Step 3: Add the Exit button JSX**

After the `<LlmStatus ... />` line at the end of the toolbar JSX, add:

```typescript
<div style={{ width: 1, height: 24, background: "var(--color-border)" }} />
<button
  onClick={onExit}
  title="Stop the backend and frontend servers"
  style={{
    background: "var(--color-danger)",
    color: "white",
    border: "none",
    padding: "4px 12px",
    borderRadius: 4,
    cursor: "pointer",
  }}
>
  Exit
</button>
```

- [ ] **Step 4: Verify TypeScript still compiles**

```bash
cd frontend
npm run build
```

Expected: build will FAIL because `App.tsx` doesn't yet pass `onExit`. That's fine — Task 6 wires it up. If you're running Tasks 5 and 6 in parallel sub-agents, the order matters: do Task 6 first or merge the commits before building.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Toolbar.tsx
git commit -m "feat(frontend): add Exit button to toolbar"
```

---

## Task 6: Wire `handleExit` and `<StoppedScreen />` in App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Read `App.tsx` to understand its structure**

Read `frontend/src/App.tsx`. Note where existing state hooks live (`useState`), where `<Toolbar />` is rendered, and what the top-level JSX structure looks like.

- [ ] **Step 2: Add the import for `StoppedScreen`**

Add to the imports section at the top:

```typescript
import { StoppedScreen } from "./components/StoppedScreen";
import { apiShutdown } from "./lib/api";
```

(If `apiShutdown` is already imported via a barrel re-export, skip the second line.)

- [ ] **Step 3: Add `stopped` state**

Inside the `App` function, near the other `useState` calls, add:

```typescript
const [stopped, setStopped] = useState(false);
```

- [ ] **Step 4: Add `handleExit` function**

Inside the `App` function, after the other handler functions, add:

```typescript
const handleExit = async () => {
  try {
    await apiShutdown();
  } catch {
    // Backend may already be down — treat as successful exit
  }
  setStopped(true);
};
```

- [ ] **Step 5: Conditionally render `<StoppedScreen />` at the top of the return**

At the start of the `return` statement of the `App` function, add:

```typescript
if (stopped) {
  return <StoppedScreen />;
}
```

- [ ] **Step 6: Pass `onExit` to `<Toolbar />`**

In the `<Toolbar ... />` element, add the prop:

```typescript
onExit={handleExit}
```

- [ ] **Step 7: Verify TypeScript builds and lint passes**

```bash
cd frontend
npm run build
npm run lint
```

Expected: both succeed.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): wire Exit button to /api/shutdown and stopped screen"
```

---

## Task 7: Adjust `start.sh` for symmetric backend-death cleanup

**Files:**
- Modify: `start.sh`

- [ ] **Step 1: Read the current `start.sh` to confirm structure**

Read `start.sh`. Confirm it has `BACKEND_PID=$!`, `FRONTEND_PID=$!`, a `cleanup` function, a `trap cleanup SIGINT SIGTERM`, and ends with `wait`.

- [ ] **Step 2: Replace the bare `wait` with backend-PID-specific wait + frontend cleanup**

Find the existing line at the bottom:

```bash
wait
```

Replace it with:

```bash
# Wait specifically on the backend. If backend dies (Ctrl+C OR /api/shutdown
# triggered SIGTERM from inside the process), tear down the frontend too.
wait $BACKEND_PID 2>/dev/null || true
echo
echo "Backend stopped — shutting down frontend..."
kill $FRONTEND_PID 2>/dev/null || true
wait $FRONTEND_PID 2>/dev/null || true
echo "Stopped."
exit 0
```

- [ ] **Step 3: Manual smoke test (Linux/macOS only — skip on Windows)**

If you're on Linux or macOS:

```bash
chmod +x start.sh
./start.sh
```

Expected: backend + frontend logs interleave in the one terminal, browser opens, then either:
- Press Ctrl+C → both die cleanly, "Stopped." printed
- OR `curl -X POST http://localhost:8000/api/shutdown` from another terminal → backend shuts down, frontend killed, "Stopped." printed

Verify no leftover processes: `ps aux | grep -E "uvicorn|vite"` should show nothing.

If on Windows, skip this step — Task 9 handles the Windows path.

- [ ] **Step 4: Commit**

```bash
git add start.sh
git commit -m "fix(start.sh): tear down frontend when backend dies"
```

---

## Task 8: Rewrite `start.bat` for single-terminal + watcher loop

**Files:**
- Modify: `start.bat`

- [ ] **Step 1: Replace the entire contents of `start.bat`**

Overwrite `start.bat` with:

```batch
@echo off
setlocal
echo Starting image2spice...
echo.

:: Check if Ollama is running (optional — OpenRouter/OpenAI/Claude can be used instead)
curl.exe -s --max-time 3 http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [*] Ollama is not running. You can use OpenRouter / OpenAI / Claude instead.
    echo     To use local models, start Ollama first: ollama serve
    echo.
)

:: Kill any existing processes on ports 8000 and 5173
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo Killing existing process on port 8000 (PID %%a)
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173 " ^| findstr "LISTENING"') do (
    echo Killing existing process on port 5173 (PID %%a)
    taskkill /PID %%a /F >nul 2>&1
)

:: Start backend in background (same console — logs interleave)
echo Starting backend on port 8000...
pushd "%~dp0backend"
start /b "" cmd /c "python -m uvicorn main:app --port 8000"
popd

:: Wait for backend to come up
timeout /t 3 /nobreak >nul

:: Start frontend in background (same console — logs interleave)
echo Starting frontend on port 5173...
pushd "%~dp0frontend"
start /b "" cmd /c "npm run dev"
popd

:: Wait for frontend
timeout /t 3 /nobreak >nul

echo.
echo image2spice is running!
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo.
echo Click "Exit" in the app or press Ctrl+C here to stop both servers.
echo.

:: Open browser
start "" http://localhost:5173

:: Watcher loop — poll the backend port. When it stops listening,
:: tear down the frontend and exit.
:waitloop
netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul
if errorlevel 1 goto cleanup
timeout /t 2 /nobreak >nul
goto waitloop

:cleanup
echo.
echo Backend stopped — shutting down frontend...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
:: Defense: also kill anything still on 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
echo Stopped.
endlocal
exit /b 0
```

- [ ] **Step 2: Manual smoke test (Windows only — skip on Linux/macOS)**

If you're on Windows:

1. Double-click `start.bat` (or run from cmd: `start.bat`)
2. Confirm: **one** cmd window opens, no extra child windows, backend + frontend logs interleave
3. Confirm: browser opens to `http://localhost:5173`
4. In the browser, click the new red **Exit** button in the toolbar
5. Confirm: the cmd window prints "Backend stopped — shutting down frontend..." then "Stopped." and exits within ~3 seconds
6. Verify no leftover processes:
   ```cmd
   tasklist | findstr /i "python node uvicorn"
   ```
   Expected: no output (or only unrelated processes).
7. Repeat with **Ctrl+C** as the teardown trigger instead of the Exit button. Same expectations.

If on Linux/macOS, skip this step — Task 7 handled that path.

- [ ] **Step 3: Commit**

```bash
git add start.bat
git commit -m "fix(start.bat): single-terminal launch with watcher loop teardown"
```

---

## Task 9: Reorganize `ground truth/` into `source/` and `output/`

**Files:**
- Move: 22 files inside `ground truth/` (use `git mv`)

- [ ] **Step 1: Create the new target directories**

```bash
mkdir -p "ground truth/source"
mkdir -p "ground truth/output"
```

(`mkdir -p` is the bash form. On Windows in cmd use `mkdir "ground truth\source"` and `mkdir "ground truth\output"`. From the bash shell that comes with Git for Windows, `mkdir -p` works.)

- [ ] **Step 2: Move all images into `source/`**

```bash
cd "ground truth"
git mv bjtampcircuit.png source/bjtampcircuit.png
git mv Source/05-rc-circuit.svg source/05-rc-circuit.svg
git mv Source/07-voltage-divider.svg source/07-voltage-divider.svg
git mv Source/09-rlc-series-circuit.svg source/09-rlc-series-circuit.svg
git mv Source/11-colpitts-oscillator.svg source/11-colpitts-oscillator.svg
git mv Source/13-wheatstone-bridge.svg source/13-wheatstone-bridge.svg
git mv Source/15-twin-t-oscillator.svg source/15-twin-t-oscillator.svg
git mv Source/17-dual-555-police-siren.svg source/17-dual-555-police-siren.svg
git mv Source/19-sine-square-triangle-generator.svg source/19-sine-square-triangle-generator.svg
git mv Source/22-npn-common-emitter.svg source/22-npn-common-emitter.svg
git mv Source/25-741-opamp-transistor-level.svg source/25-741-opamp-transistor-level.svg
git mv images/01_circuit.png source/01_circuit.png
git mv images/02_circuit.png source/02_circuit.png
git mv images/03_circuit.png source/03_circuit.png
git mv images/04_cicuit.png source/04_cicuit.png
git mv images/05_circuit.png source/05_circuit.png
git mv images/06_circuit.png source/06_circuit.png
git mv images/07_circuit.png source/07_circuit.png
git mv images/08_circuit.png source/08_circuit.png
git mv Output/images/05-temperature-monitor.png source/05-temperature-monitor.png
git mv Output/images/10-dual-led-flasher.png source/10-dual-led-flasher.png
git mv Output/images/15-triac-timer.png source/15-triac-timer.png
git mv Output/images/20-led-chaser.jpg source/20-led-chaser.jpg
git mv Output/images/25-transistor-equalizer.png source/25-transistor-equalizer.png
git mv Output/images/30-simple-inverter.png source/30-simple-inverter.png
git mv Output/images/35-lm386-amplifier.jpg source/35-lm386-amplifier.jpg
cd ..
```

- [ ] **Step 3: Move all `.asc` files into `output/`**

```bash
cd "ground truth"
git mv Output/04_cicuit.asc output/04_cicuit.asc
git mv Output/05-rc-circuit.asc output/05-rc-circuit.asc
git mv Output/25.asc output/25.asc
cd ..
```

- [ ] **Step 4: Remove the now-empty old directories**

```bash
cd "ground truth"
rmdir Source images Output/images Output 2>/dev/null || true
cd ..
```

(They should be empty after the moves. If `rmdir` fails because something is left, list the directory contents and investigate.)

- [ ] **Step 5: Verify the new layout**

```bash
ls -la "ground truth/source/" | wc -l
ls -la "ground truth/output/" | wc -l
ls -la "ground truth/"
```

Expected:
- `source/` contains 26 files (all images merged)
- `output/` contains 3 `.asc` files
- `ground truth/` root contains only the two new directories

- [ ] **Step 6: Confirm no code references the old paths**

```bash
git grep -n "ground truth/Source\|ground truth/Output\|ground truth/images\|ground truth\\\\Source\|ground truth\\\\Output\|ground truth\\\\images"
```

Expected: no matches (the spec already verified this; this is the implementation-time double-check).

- [ ] **Step 7: Commit**

```bash
git add -A "ground truth/"
git commit -m "chore: flatten ground truth/ into source/ and output/

Merge all images (.png, .jpg, .svg) into source/, all .asc reference
files into output/. Removes capitalization inconsistency, the loose
bjtampcircuit.png at the root, and the nested Output/images/ subfolder."
```

---

## Task 10: Create `.env.example` and clean local `.env`

**Files:**
- Create: `.env.example`
- Modify: `.env` (local only, NOT committed because it's gitignored)

- [ ] **Step 1: Create `.env.example`**

Create `.env.example` at the project root:

```
OPENAI_API_KEY=
CLAUDE_API_KEY=
OPENROUTER_API_KEY=
```

- [ ] **Step 2: Clean the local `.env` to match the template**

Overwrite `.env` (the existing gitignored file) with the same three empty headings:

```
OPENAI_API_KEY=
CLAUDE_API_KEY=
OPENROUTER_API_KEY=
```

This removes the live keys from disk. `.env` stays gitignored — it will not appear in `git status`.

- [ ] **Step 3: Verify `.env` is still gitignored**

```bash
git status
```

Expected: `.env.example` shows as untracked, but `.env` does NOT appear in the output (gitignore is still working).

```bash
git check-ignore -v .env
```

Expected: output mentions `.gitignore:14:.env  .env`.

- [ ] **Step 4: Commit only the template**

```bash
git add .env.example
git commit -m "chore: add .env.example template with provider key headings

OPENAI_API_KEY, CLAUDE_API_KEY, and OPENROUTER_API_KEY are read by
backend/api/routes.py via /api/env-keys. Local .env stays gitignored;
new contributors copy this template and fill in one provider key."
```

- [ ] **Step 5: REMINDER — rotate the leaked keys**

The original live `OPENAI_API_KEY` and `CLAUDE_API_KEY` from the local `.env` were transmitted into a previous Claude conversation. They were never committed (verified via `git log --all -- .env`), but they should still be **rotated** at the OpenAI and Anthropic dashboards before any further use. This is a manual user step — surface it as a final-summary item, not a script action.

---

## Task 11: Untrack `/docs` scratch files via `.gitignore` negation pattern

**Files:**
- Modify: `.gitignore`
- Untrack: `docs/slides.html`, `docs/presentation.md`

- [ ] **Step 1: Append the negation pattern to `.gitignore`**

Add to the end of `.gitignore`:

```
# Untrack /docs by default, but keep superpowers specs and plans
/docs/
!/docs/superpowers/
!/docs/superpowers/**
```

- [ ] **Step 2: Untrack the two scratch files (without deleting from disk)**

```bash
git rm --cached docs/slides.html docs/presentation.md
```

Expected output:
```
rm 'docs/slides.html'
rm 'docs/presentation.md'
```

Files remain on disk.

- [ ] **Step 3: Verify tracked files under `docs/` are now only the superpowers ones**

```bash
git ls-files docs/
```

Expected: every line starts with `docs/superpowers/`. No `docs/slides.html`, no `docs/presentation.md`.

- [ ] **Step 4: Verify `git status` doesn't try to add the now-ignored files**

```bash
git status docs/
```

Expected: `docs/slides.html` and `docs/presentation.md` should NOT appear as untracked. The `.gitignore` rule should hide them.

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore /docs except superpowers specs and plans

Untracks docs/slides.html and docs/presentation.md (kept on disk
locally) while preserving tracked specs and plans under
docs/superpowers/."
```

---

## Task 12: Rename app screenshot

**Files:**
- Move: `Screenshot 2026-04-12 035429.png` → `app-screenshot.png`

- [ ] **Step 1: Rename the file**

```bash
mv "Screenshot 2026-04-12 035429.png" app-screenshot.png
```

The file is currently untracked, so `git mv` is unnecessary — a plain `mv` followed by `git add` is fine.

- [ ] **Step 2: Verify both screenshot files are present**

```bash
ls -la *.png
```

Expected: `preview.png` (LTspice circuit example, existing) and `app-screenshot.png` (full UI screenshot, just renamed).

- [ ] **Step 3: Stage but don't commit yet**

```bash
git add app-screenshot.png
```

The commit happens together with the README rewrite in Task 13, since the README references this file.

---

## Task 13: Rewrite `README.md`

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read the current `README.md`**

Read `README.md` start to finish so you know what content to preserve and what to replace.

- [ ] **Step 2: Overwrite `README.md`**

Replace the entire contents of `README.md` with:

````markdown
# image2spice

Convert LTspice circuit schematic screenshots into `.asc` files using a vision model and a multi-step wizard pipeline. Supports local inference via [Ollama](https://ollama.com/) or cloud inference via [OpenRouter](https://openrouter.ai/), [OpenAI](https://platform.openai.com/), or [Claude](https://console.anthropic.com/).

![image2spice in action](app-screenshot.png)

## How It Works

```
Image -> Wizard (4 vision-model steps) -> SchematicIR -> deterministic generator -> .asc
                                                |
                                       SVG visual editor (review/adjust)
                                                |
                                          Export .asc
```

1. Upload an LTspice screenshot
2. The wizard runs four vision-model steps: **Identify** components, read **Directives**, describe **Layout**, trace **Wires**
3. A deterministic generator converts the intermediate representation to `.asc`
4. Review and adjust in the visual editor — drag components, draw wires, edit properties
5. Export the final `.asc` file and open it in LTspice

![LTspice schematic example](preview.png)

---

## Quick Start (TL;DR)

If you've already done first-time setup:

| Windows | Linux / macOS |
|---------|---------------|
| `start.bat` | `./start.sh` |

Both commands open one terminal, start backend + frontend, and open the app in your browser at `http://localhost:5173`. Click the red **Exit** button in the toolbar to stop everything cleanly. `Ctrl+C` in the terminal also works.

---

## Prerequisites

- **[Python 3.10+](https://www.python.org/downloads/)** (for the backend)
- **[Node.js 18+](https://nodejs.org/)** (for the frontend)
- **One vision provider** (pick at least one):
  - **[Ollama](https://ollama.com/)** — local, free, requires GPU. Pull the model: `ollama pull qwen3-vl:8b`
  - **[OpenRouter](https://openrouter.ai/)** — cloud, free tier available, no GPU needed
  - **[OpenAI](https://platform.openai.com/)** — cloud, paid
  - **[Claude](https://console.anthropic.com/)** — cloud, paid

---

## First-Time Setup

Run these commands once after cloning the repo.

### 1. Copy the environment template

```bash
# Linux / macOS
cp .env.example .env

# Windows (cmd)
copy .env.example .env
```

Open `.env` in a text editor and fill in **at least one** provider key:

```
OPENAI_API_KEY=
CLAUDE_API_KEY=
OPENROUTER_API_KEY=
```

You can leave the others blank. (Local Ollama doesn't need a key — leave all three blank if you only use Ollama.)

### 2. Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
cd ..
```

### 3. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 4. (Linux/macOS only) Make the launcher executable

```bash
chmod +x start.sh
```

You're ready to run the app.

---

## Running the App

### Windows — one terminal (recommended)

```bash
start.bat
```

What to expect:
- **One** cmd window opens. Backend and frontend logs interleave inside it — there are no extra child windows.
- The app opens automatically at `http://localhost:5173`.
- To stop: click the red **Exit** button in the toolbar, OR press `Ctrl+C` in the cmd window. Both servers tear down cleanly within ~3 seconds.

### Linux / macOS — one terminal (recommended)

```bash
./start.sh
```

What to expect:
- One terminal session runs both backend and frontend with interleaved logs.
- The app opens automatically at `http://localhost:5173` (via `xdg-open` on Linux, `open` on macOS).
- To stop: click the red **Exit** button in the toolbar, OR press `Ctrl+C` in the terminal.

### Manual (two terminals — for active development)

Use this when you want backend hot-reload via `--reload`:

```bash
# Terminal 1 — backend with auto-reload
cd backend
python -m uvicorn main:app --reload --port 8000

# Terminal 2 — frontend dev server
cd frontend
npm run dev
```

Open `http://localhost:5173` in your browser. Press `Ctrl+C` in each terminal to stop.

---

## Stopping the App

Three ways to stop image2spice cleanly:

1. **In-app Exit button** — click the red **Exit** in the toolbar. The frontend calls `/api/shutdown`, the backend exits gracefully, and the launcher script tears down the frontend.
2. **Ctrl+C in the launcher terminal** — works for both `start.bat` and `start.sh`. Both servers tear down.
3. **Manual fallback** — if something gets wedged, run the port-killer:
   - **Windows:** the kill loop is built into `start.bat`'s preamble — just rerun it.
   - **Linux/macOS:** `lsof -ti:8000 | xargs kill -9 ; lsof -ti:5173 | xargs kill -9`

---

## Usage

1. **Choose provider** — Click the status indicator in the toolbar to switch between Local (Ollama), OpenRouter, OpenAI, or Claude. For cloud providers, paste your API key (or it'll be auto-loaded from `.env`).
2. **Upload** — Click **Upload Image** and select an LTspice screenshot (PNG recommended).
3. **Generate** — Click **Generate** to run the four-step wizard. Takes 30–120 s depending on provider and hardware.
4. **Edit** — Use the visual editor:
   - **Select mode** — click components to select, drag to move
   - **Wire mode** — click two points to draw a wire
   - **Component palette** — add new components from the sidebar
   - **Property panel** — edit instance names, values, rotations
   - **Zoom/Pan** — scroll to zoom, middle-click drag to pan
   - **Undo/Redo** — `Ctrl+Z` / `Ctrl+Y`
5. **Export** — Click **Export .asc** to download the file. Open it in LTspice.
6. **Exit** — Click the red **Exit** button when done; the launcher will stop both servers.

---

## Configuration & Providers

Image2spice supports four vision providers. You can configure them either by editing `.env` (loaded once at backend startup) or by pasting an API key directly into the **LLM Status** widget in the toolbar (lives in browser memory only).

| Provider | `.env` key | Hardware | Cost |
|----------|-----------|----------|------|
| **Ollama (local)** | n/a | 8 GB+ VRAM GPU | Free |
| **OpenRouter** | `OPENROUTER_API_KEY` | None | Free tier available |
| **OpenAI** | `OPENAI_API_KEY` | None | Paid |
| **Claude** | `CLAUDE_API_KEY` | None | Paid |

**Recommended models:**
- **Ollama:** `qwen3-vl:8b` (~6 GB on disk)
- **OpenRouter:** `google/gemma-4-26b-a4b-it:free` (auto-fallback to other free models on rate-limit)
- **OpenAI:** `gpt-4o` or `gpt-4o-mini`
- **Claude:** `claude-sonnet-4-5` or `claude-opus-4-6`

---

## Project Structure

```
image2spice/
  backend/
    main.py                    # FastAPI app, CORS for localhost:5173
    api/
      routes.py                # /api/health, /api/dictionary, /api/refine,
                               # /api/validate, /api/env-keys, /api/llm-status,
                               # /api/shutdown
      wizard_routes.py         # /api/wizard/{identify,directives,layout,wires}
    services/
      ollama_client.py         # Shared Ollama HTTP client
      llm_client.py            # Unified vision client (Ollama / OpenRouter / OpenAI / Claude)
      vision.py                # Wizard vision calls
      asc_generator.py         # Deterministic SchematicIR -> .asc
      asy_parser.py            # .asy file parser
      layout.py                # Spatial -> grid coordinates (16 px snap)
      wire_router.py           # Wire description -> coordinate segments
      validator.py             # .asc syntax validation
    prompts/                   # System prompts (one per wizard step)
    scripts/
      rebuild_dictionary.py    # Regenerate dictionary/components.json from .asy files
    tests/                     # pytest test files
  frontend/
    src/
      App.tsx                  # Root component, layout, wizard orchestration
      components/
        Editor.tsx             # SVG schematic editor (select/wire modes)
        Toolbar.tsx            # Upload, Generate, Export, Undo/Redo, Grid, Theme, Exit
        ComponentPalette.tsx   # Draggable component sidebar
        PropertyPanel.tsx      # Selected item property editor
        AscPreview.tsx         # Live .asc text preview
        ScreenshotPanel.tsx    # Source image display
        GenerateWizard.tsx     # Step-by-step generation modal
        LlmStatus.tsx          # Provider switcher
        StoppedScreen.tsx      # Shown after Exit button is pressed
      hooks/                   # useSchematic, useHistory, useTheme
      lib/
        api.ts                 # Backend API client (includes apiShutdown)
        ascGenerator.ts        # Client-side .asc generation
        gridSnap.ts            # 16 px LTspice grid snapping
      types/schematic.ts       # TypeScript types
      styles/theme.css         # CSS custom properties (light + dark)
  dictionary/
    components.json            # 13 LTspice component definitions (from .asy files)
    directives.json            # SPICE directive definitions
  ground truth/
    source/                    # Test input images (.png, .jpg, .svg)
    output/                    # Reference .asc files
  start.bat                    # Windows launcher (single terminal)
  start.sh                     # Linux/macOS launcher (single terminal)
  .env.example                 # Provider key template (copy to .env)
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/env-keys` | Which providers have keys configured in `.env` |
| GET | `/api/llm-status` | Check provider connectivity |
| GET | `/api/dictionary` | Component + directive definitions |
| POST | `/api/refine` | Convert JSON IR to `.asc` (deterministic) |
| POST | `/api/validate` | Validate `.asc` syntax |
| POST | `/api/wizard/identify` | Vision: list components from image |
| POST | `/api/wizard/directives` | Vision: read SPICE directives |
| POST | `/api/wizard/layout` | Vision: spatial layout → grid coordinates |
| POST | `/api/wizard/wires` | Vision: connections → wire segments |
| POST | `/api/shutdown` | Gracefully stop the backend (used by Exit button) |

Wizard endpoints accept `multipart/form-data` with `file` (image) and optional JSON form fields.

---

## Supported Components

| Category | Components |
|----------|-----------|
| Passive | Resistor, Capacitor, Inductor |
| Sources | Voltage Source, Current Source |
| Amplifiers | Op-Amp, Op-Amp (2-input) |
| Semiconductors | NPN, PNP, NMOS, PMOS, Diode, Zener |

---

## Tests

```bash
# Backend tests
cd backend
python -m pytest tests/ -v

# Frontend build check (no automated tests — convention)
cd frontend
npm run build
```

Tests that call vision endpoints are mocked — no live Ollama or OpenRouter needed for the test suite.

---

## Troubleshooting

**Ollama must be running** (local mode only) — Start `ollama serve` before the backend. Wizard endpoints will return `500` if Ollama is unreachable. The launcher scripts warn you if Ollama isn't up but continue anyway, since cloud providers don't need it.

**OpenRouter rate limits** — Free-tier models have rate limits. The app retries with backoff and falls back to alternative free models automatically.

**Port conflicts** — Both `start.bat` and `start.sh` kill anything listening on ports 8000 and 5173 in their preamble.

**Timeout errors** — The first Ollama call is slow because the model loads into VRAM. Local timeout is 600 s, OpenRouter timeout is 120 s.

**CORS errors** — Backend only allows `http://localhost:5173`. If the frontend port changes, update `backend/main.py`.

**Exit button does nothing** — Check the cmd window / terminal for errors. The button calls `POST /api/shutdown`; if the backend is already down, the frontend still shows the "stopped" screen.

**Frontend keeps running after `Ctrl+C`** — That should not happen — the watcher loop in `start.bat` and the trap in `start.sh` both kill the frontend on backend death. If you see this, please open an issue with your OS and the launcher's output.

**Dictionary rebuild requires LTspice installed** — Run `python scripts/rebuild_dictionary.py` from `backend/`. LTspice symbol files live at `%LOCALAPPDATA%\LTspice\lib\sym\` on Windows.

---

## Hardware Requirements

**Local (Ollama):**
- **Minimum:** 8 GB VRAM GPU (model runs at Q4 quantization)
- **Recommended:** 12+ GB VRAM for faster inference
- Only one model (~6 GB VRAM) is loaded at runtime

**Cloud (OpenRouter / OpenAI / Claude):**
- No GPU required — runs entirely in the cloud
- OpenRouter has a free tier; OpenAI and Claude are pay-per-use

---

## Future: Deploy Your Own

A rough sketch for hosting image2spice on a public URL with per-session isolation lives in the design doc at `docs/superpowers/specs/2026-04-12-deploy-and-readme-design.md` (§11). The backend is already mostly stateless, so the path forward is: static frontend on Cloudflare Pages or Vercel, FastAPI backend on Fly.io or Render, vision provider via the user's own pasted API key. Not implemented yet — contributions welcome.
````

- [ ] **Step 3: Verify the README renders sensibly**

Open `README.md` in a markdown previewer (or push to a GitHub branch and check the preview). Confirm:
- The title and screenshot at the top render
- The Quick Start table renders
- The Project Structure code block doesn't overflow
- The API endpoints table renders
- All headings are at the right level (no skipped levels)

- [ ] **Step 4: Commit (together with the renamed screenshot)**

```bash
git add README.md app-screenshot.png
git commit -m "docs: rewrite README as detailed first-time-user guide

New sections: Quick Start, First-time setup, Running (Windows + Linux),
Stopping the app, Configuration. Documents the new Exit button and
single-terminal launchers. Adds app-screenshot.png alongside preview.png."
```

---

## Task 14: Final smoke tests + summary

**Files:** none — verification only.

- [ ] **Step 1: Run the full backend test suite one more time**

```bash
cd backend
python -m pytest tests/ -v
```

Expected: all tests pass, including the new `test_shutdown_returns_shutting_down`.

- [ ] **Step 2: Run frontend build + lint**

```bash
cd frontend
npm run build
npm run lint
```

Expected: both succeed.

- [ ] **Step 3: End-to-end manual test on your OS**

Pick the launcher for your OS:

**Windows:**
1. `start.bat` → confirm one cmd window, browser opens
2. Click **Upload Image**, pick a test image, click **Generate** (skip if no provider configured)
3. Click the red **Exit** button in the toolbar
4. Confirm the cmd window prints "Backend stopped — shutting down frontend..." then "Stopped." and exits
5. Run `tasklist | findstr /i "python node uvicorn"` — confirm no leftover processes

**Linux/macOS:**
1. `./start.sh` → confirm one terminal, browser opens
2. Click the red **Exit** button in the toolbar
3. Confirm "Backend stopped — shutting down frontend..." then "Stopped." prints
4. Run `ps aux | grep -E "uvicorn|vite"` — confirm no leftover processes

- [ ] **Step 4: Confirm git history is clean**

```bash
git log --oneline -20
git status
```

Expected: ~12 new commits from this plan, working tree clean.

- [ ] **Step 5: Surface the key-rotation reminder**

In the final summary message to the user, explicitly remind them:
> "The original `OPENAI_API_KEY` and `CLAUDE_API_KEY` from your local `.env` were transmitted into a Claude conversation context during the brainstorming session. They were never committed to git (verified). Please rotate both keys at https://platform.openai.com/api-keys and https://console.anthropic.com/settings/keys before any further use."

---

## Spec Coverage Checklist

| Spec Section | Plan Task |
|--------------|-----------|
| §4 Single-terminal launchers | Tasks 7 (start.sh), 8 (start.bat) |
| §5 Backend `/api/shutdown` | Task 1 |
| §6 Frontend Exit button | Tasks 2 (api), 3 (StoppedScreen), 4 (theme), 5 (Toolbar), 6 (App.tsx wiring) |
| §7 `ground truth/` reorg | Task 9 |
| §8 `.env` hygiene | Task 10 |
| §9 `/docs` gitignore policy | Task 11 |
| §10 README rewrite | Task 13 (with app-screenshot rename in Task 12) |
| §11 Deployment sketch | Documented in spec only — no implementation tasks (out of scope per spec §3) |
| §13 Testing | Task 14 (final smoke tests) — TDD steps already embedded in Tasks 1, 2, 3, 4, 6 |

All spec sections covered. §11 deliberately has no tasks because the spec marks it as future work.
