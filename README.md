# image2spice

Convert LTspice circuit schematic screenshots into `.asc` files using a vision model and a multi-step wizard pipeline. Supports local inference via Ollama or cloud inference via [OpenRouter](https://openrouter.ai/).

![LTspice schematic example](preview.png)

## How It Works

```
Image -> Wizard (4 steps via Ollama or OpenRouter) -> SchematicIR -> deterministic asc_generator -> .asc
                                                            |
                                                   SVG visual editor (review/adjust)
                                                            |
                                                     Export .asc
```

1. Upload an LTspice screenshot
2. The wizard runs four vision-model steps:
   - **Identify** - lists components from the image
   - **Directives** - reads SPICE directives
   - **Layout** - describes spatial layout, maps to grid coordinates
   - **Wires** - describes connections, computes wire segments
3. A deterministic generator converts the intermediate representation to `.asc`
4. Review in the visual editor - drag components, draw wires, edit properties
5. Export the final `.asc` file and open it in LTspice

## Prerequisites

- [Python 3.10+](https://www.python.org/downloads/)
- [Node.js 18+](https://nodejs.org/)
- One of the following vision model providers:

### Option A: Local (Ollama)

Install [Ollama](https://ollama.com/) and pull the vision model:

```bash
ollama pull qwen3-vl:8b    # Vision model (~6 GB)
```

### Option B: Cloud (OpenRouter)

Get a free API key from [openrouter.ai](https://openrouter.ai/). No local GPU required.

The recommended model is **`google/gemma-4-26b-a4b-it:free`** (selected by default). If rate-limited, the app automatically falls back to `google/gemma-4-31b-it:free` and `nvidia/nemotron-nano-12b-v2-vl:free`.

`.asc` generation is fully deterministic - no text-only LLM is needed for either provider.

## Setup

### Backend

```bash
cd backend
pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

## Running

### Option 1: Separate terminals

```bash
# Terminal 1 - Backend (API server)
cd backend
python -m uvicorn main:app --reload --port 8000

# Terminal 2 - Frontend (dev server)
cd frontend
npm run dev
```

Open http://localhost:5173 in your browser.

### Option 2: One-shot Windows startup

```bash
start.bat
```

Starts backend + frontend and opens the browser automatically.

> If port 8000 or 5173 is in use, run `kill-port.bat` to free them.

## Usage

1. **Choose provider** - Click the status indicator in the toolbar to switch between Local (Ollama) and OpenRouter. For OpenRouter, enter your API key and click "Connect"
2. **Upload** - Click "Upload Image" and select an LTspice screenshot (PNG recommended)
3. **Generate** - Click "Generate" to run the wizard (takes 30-120s depending on provider/hardware)
4. **Edit** - Use the visual editor to fix any issues:
   - **Select mode** - Click components to select, drag to move
   - **Wire mode** - Click two points to draw a wire
   - **Component palette** - Add new components from the sidebar
   - **Property panel** - Edit instance names, values, and rotations
   - **Zoom/Pan** - Scroll to zoom, middle-click drag to pan
   - **Undo/Redo** - Ctrl+Z / Ctrl+Y
5. **Export** - Click "Export .asc" to download the file

## Project Structure

```
image2spice/
  backend/
    main.py                   # FastAPI app, CORS for localhost:5173
    api/
      routes.py               # /api/dictionary, /api/refine, /api/validate
      wizard_routes.py        # /api/wizard/{identify,directives,layout,wires}
    services/
      ollama_client.py        # Shared Ollama HTTP client (localhost:11434)
      llm_client.py           # Unified vision client (Ollama + OpenRouter)
      vision.py               # Wizard vision calls, provider-aware
      asc_generator.py        # Deterministic SchematicIR -> .asc text
      asy_parser.py           # .asy file parser + build_dictionary_from_asy()
      layout.py               # Spatial description -> grid coordinates (16px snap)
      wire_router.py          # Wire description -> coordinate segments
      validator.py            # .asc syntax validation
    prompts/                  # System prompt .txt files for each wizard step
    scripts/
      rebuild_dictionary.py   # Regenerate dictionary/components.json from .asy files
    tests/                    # pytest test files (one per service module)
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
        LlmStatus.tsx         # Provider switcher (Ollama / OpenRouter)
      hooks/
        useSchematic.ts       # Schematic CRUD + undo/redo history
        useHistory.ts         # Undo/redo stack implementation
        useTheme.ts           # Dark/light theme toggle
      lib/
        api.ts                # Backend API client functions
        ascGenerator.ts       # Client-side .asc generation (mirrors backend)
        gridSnap.ts           # 16px LTspice grid snapping
      types/schematic.ts      # TypeScript type definitions
      styles/theme.css        # CSS custom properties for light and dark themes
  dictionary/
    components.json           # 13 LTspice component definitions (from .asy files)
    directives.json           # SPICE directive definitions
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/llm-status` | Check provider connectivity (Ollama or OpenRouter) |
| GET | `/api/dictionary` | Component + directive definitions |
| POST | `/api/refine` | Convert JSON IR to .asc (deterministic) |
| POST | `/api/validate` | Validate .asc syntax |
| POST | `/api/wizard/identify` | Vision: list components from image |
| POST | `/api/wizard/directives` | Vision: read SPICE directives from image |
| POST | `/api/wizard/layout` | Vision: spatial layout -> grid coordinates |
| POST | `/api/wizard/wires` | Vision: connections -> wire segments |

Wizard endpoints accept `multipart/form-data` with `file` (image) and optional JSON form fields.

## Supported Components

| Category | Components |
|----------|-----------|
| Passive | Resistor, Capacitor, Inductor |
| Sources | Voltage Source, Current Source |
| Amplifiers | Op-Amp, Op-Amp (2-input) |
| Semiconductors | NPN, PNP, NMOS, PMOS, Diode, Zener |

## Running Tests

```bash
# Backend tests
cd backend
python -m pytest tests/ -v

# Frontend build check
cd frontend
npm run build
```

Tests that call Ollama vision endpoints are mocked - no live Ollama needed for the test suite.

## Troubleshooting

**Ollama must be running** (local mode) - Start `ollama serve` before the backend. Vision endpoints will 500 if Ollama is unreachable.

**OpenRouter rate limits** - Free-tier models have rate limits. The app automatically retries with backoff and falls back to alternative free models (`gemma-3-27b-it`, `gemma-3-12b-it`).

**Port conflicts** - Run `kill-port.bat` to free ports 8000 and 5173. `start.bat` does this automatically.

**Timeout errors** - The first Ollama call is slow (model loading into VRAM). Local timeout is 600s, OpenRouter timeout is 120s.

**CORS errors** - Backend only allows `http://localhost:5173`. If the frontend port changes, update `main.py`.

**Dictionary rebuild** - Requires LTspice installed. Run `python scripts/rebuild_dictionary.py` from `backend/`. LTspice symbol files live at `%LOCALAPPDATA%\LTspice\lib\sym\` on Windows.

## Hardware Requirements

**Local (Ollama):**
- **Minimum**: 8 GB VRAM GPU (model runs at Q4 quantization)
- **Recommended**: 12+ GB VRAM for faster inference
- Only one model (~6 GB VRAM) is needed at runtime

**Cloud (OpenRouter):**
- No GPU required - runs entirely in the cloud
- Free tier available with the recommended model
