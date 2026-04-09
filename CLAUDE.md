# CLAUDE.md — image2asc

Convert LTspice circuit schematic screenshots into `.asc` files using a local vision model (qwen3-vl:8b via Ollama) and a multi-step wizard pipeline.

---

## Architecture

```
Image -> Wizard (4 steps via Ollama) -> SchematicIR -> deterministic asc_generator -> .asc
                                              |
                                     SVG visual editor (review/adjust)
                                              |
                                       Export .asc
```

**Pipeline steps (wizard):**
1. `POST /api/wizard/identify` — vision model lists components from image
2. `POST /api/wizard/directives` — vision model reads SPICE directives
3. `POST /api/wizard/layout` — vision model describes spatial layout; `layout.py` maps to grid coords
4. `POST /api/wizard/wires` — vision model describes connections; `wire_router.py` computes coordinates

**Key design decisions:**
- The refinement LLM service was intentionally removed — `.asc` generation is fully deterministic via `asc_generator.py`
- No text-only LLM is needed; `qwen3:14b` is not used at runtime
- All vision calls go through `services/ollama_client.py` with a 600s timeout

---

## Directory Structure

```
image2asc/
  backend/
    main.py                   # FastAPI app, CORS for localhost:5173
    api/
      routes.py               # /api/dictionary, /api/refine, /api/validate
      wizard_routes.py        # /api/wizard/{identify,directives,layout,wires}
    services/
      ollama_client.py        # Shared Ollama HTTP client (localhost:11434)
      vision.py               # Wizard vision calls, VISION_MODEL = "qwen3-vl:8b"
      asc_generator.py        # Deterministic SchematicIR -> .asc text
      asy_parser.py           # .asy file parser + build_dictionary_from_asy()
      layout.py               # Spatial description -> grid coordinates (16px snap)
      wire_router.py          # Wire description -> coordinate segments
      validator.py            # .asc syntax validation
    prompts/                  # System prompt .txt files for each wizard step
    scripts/
      rebuild_dictionary.py   # Regenerate dictionary/components.json from .asy files
    tests/                    # pytest test files (one per service module)
    requirements.txt
  frontend/
    src/
      App.tsx                 # Root component, layout, wizard orchestration
      components/
        Editor.tsx            # SVG schematic editor (select/wire modes)
        Toolbar.tsx           # Upload, Generate, Export, Undo/Redo, Grid, Theme
        ComponentPalette.tsx  # Draggable component sidebar
        PropertyPanel.tsx     # Selected item property editor
        AscPreview.tsx        # Live .asc text preview
        ScreenshotPanel.tsx   # Source image display
        GenerateWizard.tsx    # Step-by-step generation modal
      hooks/
        useSchematic.ts       # Schematic CRUD + undo/redo history
        useHistory.ts         # Undo/redo stack implementation
        useTheme.ts           # Dark/light theme toggle (data-theme on :root)
      lib/
        api.ts                # Backend API client functions
        ascGenerator.ts       # Client-side .asc generation (mirrors backend)
        gridSnap.ts           # 16px LTspice grid snapping
      types/schematic.ts      # TypeScript type definitions
      styles/theme.css        # CSS custom properties for light and dark themes
      index.css               # Global styles, imports theme.css
  dictionary/
    components.json           # 13 LTspice component definitions (from .asy files)
    directives.json           # SPICE directive definitions
  docs/superpowers/specs/     # Design specs for reference
  start.bat                   # Windows: starts backend + frontend + opens browser
  kill-port.bat               # Windows: free ports 8000 and/or 5173
```

---

## Running the Project

**Prerequisite:** Ollama must be running (`ollama serve`) with the vision model pulled:
```bash
ollama pull qwen3-vl:8b
```

**Backend** (run from `backend/` — imports are relative):
```bash
cd backend
python -m uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm run dev
```

Open http://localhost:5173

**One-shot Windows startup** (no `--reload`, opens browser automatically):
```bash
start.bat
```

---

## Key Commands

| Task | Command | Working directory |
|------|---------|-------------------|
| Start backend (dev) | `python -m uvicorn main:app --reload --port 8000` | `backend/` |
| Start frontend | `npm run dev` | `frontend/` |
| Run all tests | `python -m pytest tests/ -v` | `backend/` |
| Run one test file | `python -m pytest tests/test_vision.py -v` | `backend/` |
| Frontend build check | `npm run build` | `frontend/` |
| Frontend lint | `npm run lint` | `frontend/` |
| Rebuild dictionary | `python scripts/rebuild_dictionary.py` | `backend/` |
| Free port 8000 | `kill-port.bat` | project root |

---

## Tests

- **Backend:** pytest, 7 test files in `backend/tests/`, run from `backend/` directory
- **Frontend:** no tests — use `npm run build` to verify TypeScript + Vite compilation
- Tests that call Ollama vision endpoints are mocked; no live Ollama needed for the test suite
- pytest-asyncio is configured; async test functions are supported

---

## Development Conventions

**Backend:**
- Run and import from `backend/` directory — all imports are relative: `from services.xxx import yyy`
- Service modules are pure functions/async functions; no global state
- New wizard steps go in `wizard_routes.py`; non-wizard API routes go in `routes.py`
- Prompts are `.txt` files in `backend/prompts/`, loaded via `_load_prompt(filename)`
- JSON extraction from LLM responses uses `vision._extract_json()` (handles markdown fences)

**Frontend:**
- React 19 + Vite 8 + TypeScript 5.9
- All colors must use CSS custom properties — never hardcode hex/rgb values in components
  - Use: `var(--color-text)`, `var(--bg-panel)`, `var(--color-border)`, `var(--color-component)`, etc.
  - Full list of variables is in `frontend/src/styles/theme.css`
- Theme is toggled by setting `data-theme="dark"|"light"` on `:root` via `useTheme` hook
- Grid snap is 16px everywhere (LTspice native unit)
- Component names follow the pattern: `frontend/src/components/PascalCase.tsx`

**Dictionary:**
- `components.json` is generated from LTspice `.asy` files — do not hand-edit SVG paths or pin positions
- To regenerate: install LTspice, then run `python scripts/rebuild_dictionary.py` from `backend/`
- LTspice symbol files live at `%LOCALAPPDATA%\LTspice\lib\sym\` on Windows
- Override with env var: `LTSPICE_SYM_DIR=<path> python scripts/rebuild_dictionary.py`

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/dictionary` | Component + directive definitions |
| POST | `/api/refine` | Convert JSON IR to .asc (deterministic) |
| POST | `/api/validate` | Validate .asc syntax |
| POST | `/api/wizard/identify` | Vision: list components from image |
| POST | `/api/wizard/directives` | Vision: read SPICE directives from image |
| POST | `/api/wizard/layout` | Vision: spatial layout -> grid coordinates |
| POST | `/api/wizard/wires` | Vision: connections -> wire segments |

Wizard endpoints accept `multipart/form-data` with `file` (image) and optional JSON form fields.

---

## Common Gotchas

- **Ollama must be running** before starting the backend — vision endpoints will 500 if Ollama is unreachable
- **Import paths:** backend must be invoked from `backend/` directory, not the project root. `from services.vision import ...` breaks if cwd is wrong
- **Port conflicts:** use `kill-port.bat` to free 8000/5173 on Windows; `start.bat` does this automatically
- **Timeout:** first Ollama call is slow (model loading into VRAM). Client timeout is 600s in `ollama_client.py` — increase if needed
- **CORS:** backend only allows `http://localhost:5173`. If frontend port changes, update `main.py`
- **Dictionary rebuild requires LTspice installed:** `.asy` files are not bundled in the repo; `dictionary/components.json` is committed and only needs rebuilding after LTspice updates or new component additions
- **`refinement.py` is a dead module** — it exists in git history but the service was intentionally removed. Do not re-add LLM-based refinement; use `asc_generator.py` instead
- **Windows paths in scripts:** `rebuild_dictionary.py` uses `os.path.expandvars` for `%LOCALAPPDATA%`; this only works on Windows
- **`qwen3:14b` is not used at runtime** — README mentions it but it was part of the removed refinement stage
