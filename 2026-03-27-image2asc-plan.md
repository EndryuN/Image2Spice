# image2asc Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web app that converts LTspice schematic screenshots into .asc files using a hybrid vision+text AI pipeline with a visual node editor for corrections.

**Architecture:** Two-stage Ollama pipeline (Qwen3-VL 8B for image understanding, Qwen3:14b for .asc generation) behind a FastAPI backend, with a React+SVG frontend for visual editing. A shared JSON component dictionary ties all stages together.

**Tech Stack:** Python 3.10+, FastAPI, Ollama HTTP API, React 18, Vite, TypeScript, SVG

---

## File Map

```
image2asc/
  dictionary/
    components.json          -- Component type definitions (shared source of truth)
    directives.json          -- SPICE directive catalog
  backend/
    main.py                  -- FastAPI app, CORS, mount routes
    api/
      __init__.py
      routes.py              -- REST endpoints: generate, dictionary, refine, validate
    services/
      __init__.py
      ollama_client.py       -- Shared Ollama HTTP client
      vision.py              -- Vision stage: image -> JSON IR
      refinement.py          -- Text stage: JSON IR -> .asc
      asc_generator.py       -- Deterministic JSON IR -> .asc (no LLM)
      validator.py           -- .asc syntax validation
    prompts/
      vision_system.txt      -- System prompt for vision model
      refine_system.txt      -- System prompt for text model
    tests/
      __init__.py
      test_validator.py
      test_asc_generator.py
      test_vision.py
      test_refinement.py
      test_routes.py
    requirements.txt
  frontend/
    src/
      main.tsx               -- React entry point
      App.tsx                 -- Layout shell: 3-panel + toolbar
      types/
        schematic.ts         -- JSON IR types + dictionary types
      lib/
        api.ts               -- Backend API client
        ascGenerator.ts      -- Client-side JSON IR -> .asc text
        gridSnap.ts          -- Coordinate snap utilities
      components/
        Toolbar.tsx           -- Upload, Generate, Export buttons
        ImagePanel.tsx        -- Source image display
        Editor.tsx            -- SVG canvas: render + interact with schematic
        EditorControls.tsx    -- Zoom/pan controls overlay
        ComponentPalette.tsx  -- Draggable component sidebar
        PropertyPanel.tsx     -- Selected component property editor
        AscPreview.tsx        -- Read-only .asc text display
        WireDrawing.tsx       -- Wire drawing interaction layer
      hooks/
        useSchematic.ts       -- Central state: components, wires, flags, text
        useHistory.ts         -- Undo/redo stack
    package.json
    vite.config.ts
    tsconfig.json
    index.html
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `backend/main.py`, `backend/requirements.txt`, `backend/api/__init__.py`, `backend/services/__init__.py`, `backend/tests/__init__.py`
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`

- [ ] **Step 1: Create backend skeleton**

```bash
mkdir -p backend/api backend/services backend/tests backend/prompts
```

Create `backend/requirements.txt`:
```
fastapi==0.115.0
uvicorn[standard]==0.30.0
httpx==0.27.0
python-multipart==0.0.9
```

Create `backend/api/__init__.py`, `backend/services/__init__.py`, `backend/tests/__init__.py` as empty files.

Create `backend/main.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="image2asc")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 2: Verify backend starts**

Run:
```bash
cd backend && pip install -r requirements.txt && uvicorn main:app --port 8000 &
curl http://localhost:8000/api/health
```
Expected: `{"status":"ok"}`

Kill the server after verifying.

- [ ] **Step 3: Create frontend skeleton**

```bash
cd frontend && npm create vite@latest . -- --template react-ts
npm install
```

Replace `frontend/src/App.tsx`:
```tsx
function App() {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <header style={{ padding: 8, borderBottom: "1px solid #ccc" }}>
        image2asc
      </header>
      <main style={{ flex: 1, display: "flex" }}>
        <div style={{ flex: 1, borderRight: "1px solid #ccc" }}>Image</div>
        <div style={{ flex: 2, borderRight: "1px solid #ccc" }}>Editor</div>
        <div style={{ flex: 1 }}>Preview</div>
      </main>
      <footer style={{ padding: 4, borderTop: "1px solid #ccc", fontSize: 12 }}>
        Ready
      </footer>
    </div>
  );
}

export default App;
```

- [ ] **Step 4: Verify frontend starts**

Run:
```bash
cd frontend && npm run dev &
```
Expected: Vite dev server at http://localhost:5173 showing 3-panel layout.

Kill the server after verifying.

- [ ] **Step 5: Commit**

```bash
git add backend/ frontend/
git commit -m "feat: project scaffolding - FastAPI backend + React frontend"
```

---

### Task 2: Component Dictionary

**Files:**
- Create: `dictionary/components.json`
- Create: `dictionary/directives.json`

- [ ] **Step 1: Create components.json**

Create `dictionary/components.json`:
```json
{
  "components": {
    "res": {
      "id": "res",
      "category": "passive",
      "displayName": "Resistor",
      "symbol": {
        "width": 64,
        "height": 32,
        "svgPath": "M0,16 L8,16 L12,0 L20,32 L28,0 L36,32 L44,0 L52,32 L56,16 L64,16"
      },
      "pins": [
        { "name": "1", "position": [0, 16], "direction": "left" },
        { "name": "2", "position": [64, 16], "direction": "right" }
      ],
      "ascSyntax": {
        "symbolName": "res",
        "attributes": ["InstName", "Value"]
      },
      "rotations": ["R0", "R90", "R180", "R270", "M0", "M90"]
    },
    "cap": {
      "id": "cap",
      "category": "passive",
      "displayName": "Capacitor",
      "symbol": {
        "width": 32,
        "height": 48,
        "svgPath": "M16,0 L16,18 M0,18 L32,18 M0,30 L32,30 M16,30 L16,48"
      },
      "pins": [
        { "name": "1", "position": [16, 0], "direction": "up" },
        { "name": "2", "position": [16, 48], "direction": "down" }
      ],
      "ascSyntax": {
        "symbolName": "cap",
        "attributes": ["InstName", "Value"]
      },
      "rotations": ["R0", "R90", "R180", "R270", "M0", "M90"]
    },
    "ind": {
      "id": "ind",
      "category": "passive",
      "displayName": "Inductor",
      "symbol": {
        "width": 32,
        "height": 64,
        "svgPath": "M16,0 L16,8 A8,8 0 0,1 16,24 A8,8 0 0,1 16,40 A8,8 0 0,1 16,56 L16,64"
      },
      "pins": [
        { "name": "1", "position": [16, 0], "direction": "up" },
        { "name": "2", "position": [16, 64], "direction": "down" }
      ],
      "ascSyntax": {
        "symbolName": "ind",
        "attributes": ["InstName", "Value"]
      },
      "rotations": ["R0", "R90", "R180", "R270", "M0", "M90"]
    },
    "voltage": {
      "id": "voltage",
      "category": "sources",
      "displayName": "Voltage Source",
      "symbol": {
        "width": 48,
        "height": 96,
        "svgPath": "M24,0 L24,16 M24,96 L24,80 M24,48 m-32,0 a32,32 0 1,0 64,0 a32,32 0 1,0 -64,0"
      },
      "pins": [
        { "name": "+", "position": [24, 0], "direction": "up" },
        { "name": "-", "position": [24, 96], "direction": "down" }
      ],
      "ascSyntax": {
        "symbolName": "voltage",
        "attributes": ["InstName", "Value", "Value2"]
      },
      "rotations": ["R0", "R90", "R180", "R270", "M0", "M90"]
    },
    "current": {
      "id": "current",
      "category": "sources",
      "displayName": "Current Source",
      "symbol": {
        "width": 48,
        "height": 96,
        "svgPath": "M24,0 L24,16 M24,96 L24,80 M24,48 m-32,0 a32,32 0 1,0 64,0 a32,32 0 1,0 -64,0 M24,32 L24,64 M24,32 L18,40 M24,32 L30,40"
      },
      "pins": [
        { "name": "+", "position": [24, 0], "direction": "up" },
        { "name": "-", "position": [24, 96], "direction": "down" }
      ],
      "ascSyntax": {
        "symbolName": "current",
        "attributes": ["InstName", "Value"]
      },
      "rotations": ["R0", "R90", "R180", "R270", "M0", "M90"]
    },
    "opamp2": {
      "id": "opamp2",
      "category": "amplifiers",
      "displayName": "Op-Amp (2-input)",
      "symbol": {
        "width": 80,
        "height": 96,
        "svgPath": "M0,0 L80,48 L0,96 Z"
      },
      "pins": [
        { "name": "out", "position": [80, 48], "direction": "right" },
        { "name": "in+", "position": [0, 64], "direction": "left" },
        { "name": "in-", "position": [0, 32], "direction": "left" },
        { "name": "V+", "position": [32, 0], "direction": "up" },
        { "name": "V-", "position": [32, 96], "direction": "down" }
      ],
      "ascSyntax": {
        "symbolName": "opamp2",
        "attributes": ["InstName", "Value"]
      },
      "rotations": ["R0", "R90", "R180", "R270", "M0", "M90"]
    },
    "opamp": {
      "id": "opamp",
      "category": "amplifiers",
      "displayName": "Op-Amp (single supply)",
      "symbol": {
        "width": 80,
        "height": 96,
        "svgPath": "M0,0 L80,48 L0,96 Z"
      },
      "pins": [
        { "name": "out", "position": [80, 48], "direction": "right" },
        { "name": "in+", "position": [0, 64], "direction": "left" },
        { "name": "in-", "position": [0, 32], "direction": "left" }
      ],
      "ascSyntax": {
        "symbolName": "opamp",
        "attributes": ["InstName", "Value"]
      },
      "rotations": ["R0", "R90", "R180", "R270", "M0", "M90"]
    },
    "npn": {
      "id": "npn",
      "category": "semiconductors",
      "displayName": "NPN Transistor",
      "symbol": {
        "width": 48,
        "height": 64,
        "svgPath": "M0,32 L16,32 L16,8 L16,56 M16,16 L48,0 M16,48 L48,64"
      },
      "pins": [
        { "name": "C", "position": [48, 0], "direction": "up" },
        { "name": "B", "position": [0, 32], "direction": "left" },
        { "name": "E", "position": [48, 64], "direction": "down" }
      ],
      "ascSyntax": {
        "symbolName": "npn",
        "attributes": ["InstName", "Value"]
      },
      "rotations": ["R0", "R90", "R180", "R270", "M0", "M90"]
    },
    "pnp": {
      "id": "pnp",
      "category": "semiconductors",
      "displayName": "PNP Transistor",
      "symbol": {
        "width": 48,
        "height": 64,
        "svgPath": "M0,32 L16,32 L16,8 L16,56 M16,16 L48,0 M16,48 L48,64"
      },
      "pins": [
        { "name": "C", "position": [48, 64], "direction": "down" },
        { "name": "B", "position": [0, 32], "direction": "left" },
        { "name": "E", "position": [48, 0], "direction": "up" }
      ],
      "ascSyntax": {
        "symbolName": "pnp",
        "attributes": ["InstName", "Value"]
      },
      "rotations": ["R0", "R90", "R180", "R270", "M0", "M90"]
    },
    "nmos": {
      "id": "nmos",
      "category": "semiconductors",
      "displayName": "NMOS Transistor",
      "symbol": {
        "width": 48,
        "height": 64,
        "svgPath": "M0,32 L12,32 M16,8 L16,56 M16,16 L48,16 L48,0 M16,48 L48,48 L48,64 M16,32 L48,32"
      },
      "pins": [
        { "name": "D", "position": [48, 0], "direction": "up" },
        { "name": "G", "position": [0, 32], "direction": "left" },
        { "name": "S", "position": [48, 64], "direction": "down" }
      ],
      "ascSyntax": {
        "symbolName": "nmos",
        "attributes": ["InstName", "Value"]
      },
      "rotations": ["R0", "R90", "R180", "R270", "M0", "M90"]
    },
    "pmos": {
      "id": "pmos",
      "category": "semiconductors",
      "displayName": "PMOS Transistor",
      "symbol": {
        "width": 48,
        "height": 64,
        "svgPath": "M0,32 L12,32 M16,8 L16,56 M16,16 L48,16 L48,0 M16,48 L48,48 L48,64 M16,32 L48,32"
      },
      "pins": [
        { "name": "S", "position": [48, 0], "direction": "up" },
        { "name": "G", "position": [0, 32], "direction": "left" },
        { "name": "D", "position": [48, 64], "direction": "down" }
      ],
      "ascSyntax": {
        "symbolName": "pmos",
        "attributes": ["InstName", "Value"]
      },
      "rotations": ["R0", "R90", "R180", "R270", "M0", "M90"]
    },
    "diode": {
      "id": "diode",
      "category": "semiconductors",
      "displayName": "Diode",
      "symbol": {
        "width": 32,
        "height": 48,
        "svgPath": "M16,0 L16,12 M0,12 L32,12 L16,36 L0,12 M0,36 L32,36 M16,36 L16,48"
      },
      "pins": [
        { "name": "A", "position": [16, 0], "direction": "up" },
        { "name": "K", "position": [16, 48], "direction": "down" }
      ],
      "ascSyntax": {
        "symbolName": "diode",
        "attributes": ["InstName", "Value"]
      },
      "rotations": ["R0", "R90", "R180", "R270", "M0", "M90"]
    },
    "zener": {
      "id": "zener",
      "category": "semiconductors",
      "displayName": "Zener Diode",
      "symbol": {
        "width": 32,
        "height": 48,
        "svgPath": "M16,0 L16,12 M0,12 L32,12 L16,36 L0,12 M0,36 L32,36 M16,36 L16,48"
      },
      "pins": [
        { "name": "A", "position": [16, 0], "direction": "up" },
        { "name": "K", "position": [16, 48], "direction": "down" }
      ],
      "ascSyntax": {
        "symbolName": "zener",
        "attributes": ["InstName", "Value"]
      },
      "rotations": ["R0", "R90", "R180", "R270", "M0", "M90"]
    }
  }
}
```

- [ ] **Step 2: Create directives.json**

Create `dictionary/directives.json`:
```json
{
  "directives": {
    ".tran": {
      "syntax": ".tran <tstop>",
      "fullSyntax": ".tran <tstep> <tstop> [<tstart> [<tmaxstep>]] [startup] [steady]",
      "description": "Transient analysis"
    },
    ".ac": {
      "syntax": ".ac <type> <npts> <fstart> <fstop>",
      "description": "AC analysis",
      "typeOptions": ["dec", "oct", "lin"]
    },
    ".dc": {
      "syntax": ".dc <source> <start> <stop> <step>",
      "description": "DC sweep"
    },
    ".noise": {
      "syntax": ".noise V(<out>) <src> <type> <npts> <fstart> <fstop>",
      "description": "Noise analysis"
    },
    ".param": {
      "syntax": ".param <name>=<value> [<name>=<value>...]",
      "description": "Parameter definition"
    },
    ".lib": {
      "syntax": ".lib <filename>",
      "description": "Include SPICE library"
    },
    ".model": {
      "syntax": ".model <name> <type>([params])",
      "description": "Model definition"
    },
    ".include": {
      "syntax": ".include <filename>",
      "description": "Include file"
    },
    ".op": {
      "syntax": ".op",
      "description": "DC operating point"
    },
    ".meas": {
      "syntax": ".meas <analysisType> <name> <measurement>",
      "description": "Measurement"
    },
    ".ic": {
      "syntax": ".ic V(<node>)=<value>",
      "description": "Initial conditions"
    },
    ".options": {
      "syntax": ".options <option>=<value>",
      "description": "Simulation options"
    }
  },
  "valueFormats": {
    "AC": "AC <magnitude> [phase]",
    "PULSE": "PULSE(<V1> <V2> <Tdelay> <Trise> <Tfall> <Ton> <Tperiod> [<Ncycles>])",
    "SINE": "SINE(<Voffset> <Vamp> <Freq> [<Tdelay> <Theta> <Phi> <Ncycles>])",
    "PWL": "PWL(<t1> <v1> <t2> <v2> ...)"
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add dictionary/
git commit -m "feat: add component dictionary and SPICE directives catalog"
```

---

### Task 3: .asc Validator (TDD)

**Files:**
- Create: `backend/services/validator.py`
- Create: `backend/tests/test_validator.py`

- [ ] **Step 1: Write failing tests for the validator**

Create `backend/tests/test_validator.py`:
```python
import pytest
from services.validator import validate_asc, ValidationResult


def test_valid_minimal_asc():
    asc = "Version 4\nSHEET 1 880 680\n"
    result = validate_asc(asc)
    assert result.valid is True
    assert result.errors == []


def test_missing_version_line():
    asc = "SHEET 1 880 680\n"
    result = validate_asc(asc)
    assert result.valid is False
    assert any("Version 4" in e for e in result.errors)


def test_missing_sheet_line():
    asc = "Version 4\n"
    result = validate_asc(asc)
    assert result.valid is False
    assert any("SHEET" in e for e in result.errors)


def test_symbol_without_symattr():
    asc = "Version 4\nSHEET 1 880 680\nSYMBOL res 272 128 R90\n"
    result = validate_asc(asc)
    assert result.valid is False
    assert any("InstName" in e for e in result.errors)


def test_symbol_with_symattr():
    asc = (
        "Version 4\nSHEET 1 880 680\n"
        "SYMBOL res 272 128 R90\n"
        "SYMATTR InstName R1\n"
        "SYMATTR Value 1k\n"
    )
    result = validate_asc(asc)
    assert result.valid is True


def test_wire_with_valid_coordinates():
    asc = (
        "Version 4\nSHEET 1 880 680\n"
        "WIRE 416 144 336 144\n"
    )
    result = validate_asc(asc)
    assert result.valid is True


def test_wire_with_non_integer_coordinates():
    asc = (
        "Version 4\nSHEET 1 880 680\n"
        "WIRE 416.5 144 336 144\n"
    )
    result = validate_asc(asc)
    assert result.valid is False
    assert any("integer" in e.lower() for e in result.errors)


def test_flag_valid():
    asc = (
        "Version 4\nSHEET 1 880 680\n"
        "FLAG 160 272 0\n"
    )
    result = validate_asc(asc)
    assert result.valid is True


def test_text_directive():
    asc = (
        "Version 4\nSHEET 1 880 680\n"
        "TEXT 400 450 Left 2 !.tran 0.005\n"
    )
    result = validate_asc(asc)
    assert result.valid is True


def test_full_reference_asc():
    """Validate the actual reference .asc file content."""
    asc = (
        "Version 4\n"
        "SHEET 1 880 680\n"
        "SYMBOL opamp2 400 128 R0\n"
        "SYMATTR InstName U1\n"
        "SYMATTR Value ADA4627\n"
        "SYMBOL res 272 128 R90\n"
        "WINDOW 0 0 56 VBottom 2\n"
        "WINDOW 3 32 56 VBottom 2\n"
        "SYMATTR InstName R5\n"
        "SYMATTR Value 1000 noiseless\n"
        "WIRE 416 144 336 144\n"
        "FLAG 160 272 0\n"
        "FLAG 608 176 OUT\n"
        "TEXT 400 450 Left 2 !.param RINP=1k PSV=15\n"
        "TEXT 400 480 Left 2 !.tran 0.005\n"
    )
    result = validate_asc(asc)
    assert result.valid is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && python -m pytest tests/test_validator.py -v
```
Expected: All tests FAIL with `ModuleNotFoundError: No module named 'services.validator'`

- [ ] **Step 3: Implement the validator**

Create `backend/services/validator.py`:
```python
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_asc(content: str) -> ValidationResult:
    result = ValidationResult()
    lines = content.strip().split("\n")

    if not lines or not lines[0].startswith("Version 4"):
        result.valid = False
        result.errors.append("File must start with 'Version 4'")

    has_sheet = False
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("SHEET "):
            has_sheet = True
            _validate_sheet(line, result)

        elif line.startswith("SYMBOL "):
            _validate_symbol_block(lines, i, result)

        elif line.startswith("WIRE "):
            _validate_wire(line, result)

        elif line.startswith("FLAG "):
            _validate_flag(line, result)

        elif line.startswith("TEXT "):
            pass  # TEXT lines have varied formats, accept as-is

        i += 1

    if not has_sheet:
        result.valid = False
        result.errors.append("File must contain a SHEET line")

    return result


def _validate_sheet(line: str, result: ValidationResult):
    parts = line.split()
    if len(parts) != 4:
        result.valid = False
        result.errors.append(f"Invalid SHEET line: {line}")


def _validate_symbol_block(lines: list[str], symbol_idx: int, result: ValidationResult):
    parts = lines[symbol_idx].strip().split()
    if len(parts) != 5:
        result.valid = False
        result.errors.append(f"Invalid SYMBOL line: {lines[symbol_idx].strip()}")
        return

    rotation = parts[4]
    valid_rotations = {"R0", "R90", "R180", "R270", "M0", "M90", "M180", "M270"}
    if rotation not in valid_rotations:
        result.valid = False
        result.errors.append(f"Invalid rotation '{rotation}' in: {lines[symbol_idx].strip()}")

    has_instname = False
    j = symbol_idx + 1
    while j < len(lines):
        next_line = lines[j].strip()
        if next_line.startswith("SYMATTR InstName"):
            has_instname = True
            break
        elif next_line.startswith("SYMATTR ") or next_line.startswith("WINDOW "):
            j += 1
            continue
        else:
            break
        j += 1

    if not has_instname:
        result.valid = False
        result.errors.append(
            f"SYMBOL at line {symbol_idx + 1} missing SYMATTR InstName"
        )


def _validate_wire(line: str, result: ValidationResult):
    parts = line.split()
    if len(parts) != 5:
        result.valid = False
        result.errors.append(f"WIRE must have 4 integer coordinates: {line}")
        return

    for coord_str in parts[1:]:
        try:
            val = float(coord_str)
            if val != int(val):
                result.valid = False
                result.errors.append(
                    f"WIRE coordinates must be integers, got '{coord_str}': {line}"
                )
        except ValueError:
            result.valid = False
            result.errors.append(
                f"WIRE coordinate '{coord_str}' is not a number: {line}"
            )


def _validate_flag(line: str, result: ValidationResult):
    parts = line.split()
    if len(parts) < 4:
        result.valid = False
        result.errors.append(f"Invalid FLAG line: {line}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && python -m pytest tests/test_validator.py -v
```
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/validator.py backend/tests/test_validator.py
git commit -m "feat: add .asc syntax validator with TDD tests"
```

---

### Task 4: Deterministic .asc Generator (TDD)

**Files:**
- Create: `backend/services/asc_generator.py`
- Create: `backend/tests/test_asc_generator.py`

This converts JSON IR to .asc text deterministically (no LLM). Used both client-side and for validation.

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_asc_generator.py`:
```python
import pytest
from services.asc_generator import generate_asc, SchematicIR


def test_empty_schematic():
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    asc = generate_asc(ir)
    assert asc.startswith("Version 4\n")
    assert "SHEET 1 880 680" in asc


def test_single_resistor():
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    ir.add_component("res", "R1", "1k", 272, 128, "R90")
    asc = generate_asc(ir)
    assert "SYMBOL res 272 128 R90" in asc
    assert "SYMATTR InstName R1" in asc
    assert "SYMATTR Value 1k" in asc


def test_component_with_value2():
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    ir.add_component(
        "voltage", "V3", "PULSE(0 0.01 0 1u 1u 0.0005 0.001 100)",
        112, 288, "R0", value2="AC 0.01"
    )
    asc = generate_asc(ir)
    assert "SYMBOL voltage 112 288 R0" in asc
    assert "SYMATTR InstName V3" in asc
    assert "SYMATTR Value PULSE(0 0.01 0 1u 1u 0.0005 0.001 100)" in asc
    assert "SYMATTR Value2 AC 0.01" in asc


def test_wires():
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    ir.add_wire(416, 144, 336, 144)
    ir.add_wire(336, 144, 336, 176)
    asc = generate_asc(ir)
    assert "WIRE 416 144 336 144" in asc
    assert "WIRE 336 144 336 176" in asc


def test_flags():
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    ir.add_flag("0", 160, 272)
    ir.add_flag("OUT", 608, 176)
    asc = generate_asc(ir)
    assert "FLAG 160 272 0" in asc
    assert "FLAG 608 176 OUT" in asc


def test_text_directives():
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    ir.add_text(".param RINP=1k PSV=15", 400, 450)
    ir.add_text(".tran 0.005", 400, 480)
    asc = generate_asc(ir)
    assert "TEXT 400 450 Left 2 !.param RINP=1k PSV=15" in asc
    assert "TEXT 400 480 Left 2 !.tran 0.005" in asc


def test_section_ordering():
    """Sections must appear in order: version, sheet, symbols, wires, flags, text."""
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    ir.add_component("res", "R1", "1k", 100, 100, "R0")
    ir.add_wire(100, 100, 200, 100)
    ir.add_flag("0", 150, 150)
    ir.add_text(".tran 1", 300, 300)
    asc = generate_asc(ir)
    lines = asc.strip().split("\n")

    symbol_idx = next(i for i, l in enumerate(lines) if l.startswith("SYMBOL"))
    wire_idx = next(i for i, l in enumerate(lines) if l.startswith("WIRE"))
    flag_idx = next(i for i, l in enumerate(lines) if l.startswith("FLAG"))
    text_idx = next(i for i, l in enumerate(lines) if l.startswith("TEXT"))

    assert symbol_idx < wire_idx < flag_idx < text_idx


def test_full_reference_circuit():
    """Generate the reference amplifier noise circuit and validate it."""
    ir = SchematicIR(sheet_width=880, sheet_height=680)

    ir.add_component("opamp2", "U1", "ADA4627", 400, 128, "R0")
    ir.add_component("res", "R5", "1000 noiseless", 272, 128, "R90")
    ir.add_component("res", "R6", "20.5 noiseless", 160, 176, "R0")
    ir.add_component("res", "R4", "{RINP} noiseless", 272, 208, "R90")
    ir.add_component(
        "voltage", "V3", "PULSE(0 0.01 0 1u 1u 0.0005 0.001 100)",
        112, 288, "R0", value2="AC 0.01"
    )
    ir.add_component("voltage", "V1", "{PSV}", 640, 144, "R0")
    ir.add_component("voltage", "V2", "{PSV}", 640, 304, "R0")

    ir.add_wire(416, 144, 336, 144)
    ir.add_wire(336, 144, 336, 176)
    ir.add_wire(336, 176, 160, 176)
    ir.add_wire(416, 208, 336, 208)

    ir.add_flag("0", 160, 272)
    ir.add_flag("OUT", 608, 176)

    ir.add_text(".param RINP=1k PSV=15", 400, 450)
    ir.add_text(".tran 0.005", 400, 480)
    ir.add_text(".noise V(OUT) V3 dec 10 1 1Meg", 400, 510)

    asc = generate_asc(ir)

    # Validate the output
    from services.validator import validate_asc
    result = validate_asc(asc)
    assert result.valid is True, f"Validation errors: {result.errors}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && python -m pytest tests/test_asc_generator.py -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the generator**

Create `backend/services/asc_generator.py`:
```python
from dataclasses import dataclass, field


@dataclass
class Component:
    type: str
    instance_name: str
    value: str
    x: int
    y: int
    rotation: str
    value2: str | None = None
    windows: list[str] = field(default_factory=list)


@dataclass
class Wire:
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass
class Flag:
    name: str
    x: int
    y: int


@dataclass
class Text:
    content: str
    x: int
    y: int
    justify: str = "Left"
    font_size: int = 2


class SchematicIR:
    def __init__(self, sheet_width: int = 880, sheet_height: int = 680):
        self.sheet_width = sheet_width
        self.sheet_height = sheet_height
        self.components: list[Component] = []
        self.wires: list[Wire] = []
        self.flags: list[Flag] = []
        self.texts: list[Text] = []

    def add_component(
        self,
        comp_type: str,
        instance_name: str,
        value: str,
        x: int,
        y: int,
        rotation: str,
        value2: str | None = None,
    ):
        self.components.append(
            Component(comp_type, instance_name, value, x, y, rotation, value2)
        )

    def add_wire(self, x1: int, y1: int, x2: int, y2: int):
        self.wires.append(Wire(x1, y1, x2, y2))

    def add_flag(self, name: str, x: int, y: int):
        self.flags.append(Flag(name, x, y))

    def add_text(self, content: str, x: int, y: int):
        self.texts.append(Text(content, x, y))


def generate_asc(ir: SchematicIR) -> str:
    lines: list[str] = []

    lines.append("Version 4")
    lines.append(f"SHEET 1 {ir.sheet_width} {ir.sheet_height}")

    for comp in ir.components:
        lines.append(f"SYMBOL {comp.type} {comp.x} {comp.y} {comp.rotation}")
        for window in comp.windows:
            lines.append(window)
        lines.append(f"SYMATTR InstName {comp.instance_name}")
        lines.append(f"SYMATTR Value {comp.value}")
        if comp.value2 is not None:
            lines.append(f"SYMATTR Value2 {comp.value2}")

    for wire in ir.wires:
        lines.append(f"WIRE {wire.x1} {wire.y1} {wire.x2} {wire.y2}")

    for flag in ir.flags:
        lines.append(f"FLAG {flag.x} {flag.y} {flag.name}")

    for text in ir.texts:
        prefix = "!" if text.content.startswith(".") else ""
        lines.append(
            f"TEXT {text.x} {text.y} {text.justify} {text.font_size} {prefix}{text.content}"
        )

    lines.append("")  # trailing newline
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && python -m pytest tests/test_asc_generator.py -v
```
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/asc_generator.py backend/tests/test_asc_generator.py
git commit -m "feat: add deterministic .asc generator from SchematicIR"
```

---

### Task 5: Ollama Client + Vision Service

**Files:**
- Create: `backend/services/ollama_client.py`
- Create: `backend/services/vision.py`
- Create: `backend/prompts/vision_system.txt`
- Create: `backend/tests/test_vision.py`

- [ ] **Step 1: Create the shared Ollama HTTP client**

Create `backend/services/ollama_client.py`:
```python
import base64
import httpx

OLLAMA_BASE_URL = "http://localhost:11434"


async def chat_with_vision(
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
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]


async def chat_text(
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
```

- [ ] **Step 2: Create the vision system prompt**

Create `backend/prompts/vision_system.txt`:
```
You are an expert at analyzing LTspice circuit schematic screenshots.

LTspice schematics have these visual conventions:
- Gray background with blue components and wires
- Resistors: zigzag shapes labeled R1, R2, etc. with values like "1k", "100", "noiseless"
- Capacitors: two parallel lines
- Inductors: coil shapes
- Op-amps: triangle shapes with + and - inputs, labeled U1, U2, etc.
- Voltage sources: circles with + and - signs, labeled V1, V2, etc.
- Current sources: circles with an arrow inside
- Wires: straight blue lines connecting components
- Ground symbols: triangle pointing down, labeled "0"
- Net labels/flags: text labels at wire endpoints like "OUT", "VP", "VN"
- SPICE directives: text at bottom starting with . like ".tran", ".param", ".noise"

Your task: analyze the image and output a JSON object describing every component, wire, flag, and text directive you see.

Output ONLY valid JSON with this exact structure:
{
  "sheet": {"width": <int>, "height": <int>},
  "components": [
    {
      "type": "<res|cap|ind|voltage|current|opamp|opamp2|npn|pnp|nmos|pmos|diode|zener>",
      "instanceName": "<e.g. R1, U1, V1>",
      "value": "<component value>",
      "position": {"x": <int>, "y": <int>},
      "rotation": "<R0|R90|R180|R270>",
      "value2": "<optional, for voltage sources with AC value>"
    }
  ],
  "wires": [
    {"from": {"x": <int>, "y": <int>}, "to": {"x": <int>, "y": <int>}}
  ],
  "flags": [
    {"name": "<label or 0 for ground>", "position": {"x": <int>, "y": <int>}}
  ],
  "text": [
    {"content": "<directive text without !>", "position": {"x": <int>, "y": <int>}}
  ]
}

Use approximate coordinates based on the image layout. LTspice uses a grid with multiples of 16.
Position (0,0) is at the top-left. Typical sheet size is 880x680.
Be thorough - list EVERY component, wire, flag, and directive visible in the image.
```

- [ ] **Step 3: Implement the vision service**

Create `backend/services/vision.py`:
```python
import json
import re
from pathlib import Path

from services.ollama_client import chat_with_vision
from services.asc_generator import SchematicIR

VISION_MODEL = "qwen3-vl:8b"
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _extract_json(text: str) -> dict:
    """Extract JSON from model response, handling markdown code fences."""
    # Try to find JSON in code fences first
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())
    # Try parsing the whole response
    # Find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start : end + 1])
    raise ValueError(f"Could not extract JSON from response: {text[:200]}")


def _json_to_ir(data: dict) -> SchematicIR:
    sheet = data.get("sheet", {"width": 880, "height": 680})
    ir = SchematicIR(sheet_width=sheet["width"], sheet_height=sheet["height"])

    for comp in data.get("components", []):
        ir.add_component(
            comp_type=comp["type"],
            instance_name=comp["instanceName"],
            value=comp["value"],
            x=int(comp["position"]["x"]),
            y=int(comp["position"]["y"]),
            rotation=comp.get("rotation", "R0"),
            value2=comp.get("value2"),
        )

    for wire in data.get("wires", []):
        ir.add_wire(
            x1=int(wire["from"]["x"]),
            y1=int(wire["from"]["y"]),
            x2=int(wire["to"]["x"]),
            y2=int(wire["to"]["y"]),
        )

    for flag in data.get("flags", []):
        ir.add_flag(
            name=flag["name"],
            x=int(flag["position"]["x"]),
            y=int(flag["position"]["y"]),
        )

    for text in data.get("text", []):
        ir.add_text(
            content=text["content"],
            x=int(text["position"]["x"]),
            y=int(text["position"]["y"]),
        )

    return ir


async def analyze_image(image_bytes: bytes) -> tuple[SchematicIR, dict]:
    """Analyze an LTspice screenshot, return (SchematicIR, raw_json_dict)."""
    system_prompt = _load_prompt("vision_system.txt")
    user_prompt = "Analyze this LTspice schematic screenshot. Output the JSON representation of all components, wires, flags, and directives."

    response = await chat_with_vision(VISION_MODEL, system_prompt, user_prompt, image_bytes)
    raw_data = _extract_json(response)
    ir = _json_to_ir(raw_data)
    return ir, raw_data
```

- [ ] **Step 4: Write a unit test for JSON extraction and IR conversion**

Create `backend/tests/test_vision.py`:
```python
import pytest
from services.vision import _extract_json, _json_to_ir


def test_extract_json_from_code_fence():
    text = '```json\n{"sheet": {"width": 880, "height": 680}}\n```'
    result = _extract_json(text)
    assert result["sheet"]["width"] == 880


def test_extract_json_bare():
    text = '{"sheet": {"width": 880, "height": 680}}'
    result = _extract_json(text)
    assert result["sheet"]["width"] == 880


def test_extract_json_with_surrounding_text():
    text = 'Here is the analysis:\n{"sheet": {"width": 880, "height": 680}}\nDone.'
    result = _extract_json(text)
    assert result["sheet"]["width"] == 880


def test_extract_json_invalid():
    with pytest.raises(ValueError):
        _extract_json("no json here")


def test_json_to_ir_basic():
    data = {
        "sheet": {"width": 880, "height": 680},
        "components": [
            {
                "type": "res",
                "instanceName": "R1",
                "value": "1k",
                "position": {"x": 272, "y": 128},
                "rotation": "R90",
            }
        ],
        "wires": [{"from": {"x": 100, "y": 100}, "to": {"x": 200, "y": 100}}],
        "flags": [{"name": "0", "position": {"x": 150, "y": 150}}],
        "text": [{"content": ".tran 0.005", "position": {"x": 400, "y": 450}}],
    }
    ir = _json_to_ir(data)
    assert len(ir.components) == 1
    assert ir.components[0].instance_name == "R1"
    assert len(ir.wires) == 1
    assert len(ir.flags) == 1
    assert len(ir.texts) == 1


def test_json_to_ir_with_value2():
    data = {
        "sheet": {"width": 880, "height": 680},
        "components": [
            {
                "type": "voltage",
                "instanceName": "V3",
                "value": "PULSE(0 0.01 0 1u 1u 0.0005 0.001 100)",
                "position": {"x": 112, "y": 288},
                "rotation": "R0",
                "value2": "AC 0.01",
            }
        ],
        "wires": [],
        "flags": [],
        "text": [],
    }
    ir = _json_to_ir(data)
    assert ir.components[0].value2 == "AC 0.01"
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd backend && python -m pytest tests/test_vision.py -v
```
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/ollama_client.py backend/services/vision.py backend/prompts/vision_system.txt backend/tests/test_vision.py
git commit -m "feat: add Ollama client and vision service with prompt"
```

---

### Task 6: Refinement Service

**Files:**
- Create: `backend/services/refinement.py`
- Create: `backend/prompts/refine_system.txt`
- Create: `backend/tests/test_refinement.py`

- [ ] **Step 1: Create the refinement system prompt**

Create `backend/prompts/refine_system.txt`:
```
You are an expert at generating LTspice .asc schematic files.

You will receive a JSON description of a circuit and must produce a valid .asc file.

.asc file format rules:
1. First line: "Version 4"
2. Second line: "SHEET 1 <width> <height>"
3. Components: "SYMBOL <type> <x> <y> <rotation>" followed by "SYMATTR InstName <name>" and "SYMATTR Value <value>"
4. If a component has a Value2 (like AC value for voltage sources): "SYMATTR Value2 <value2>"
5. Wires: "WIRE <x1> <y1> <x2> <y2>"
6. Flags (net labels and ground): "FLAG <x> <y> <name>" where "0" means ground
7. SPICE directives: "TEXT <x> <y> Left 2 !<directive>"

Rotation values: R0 (default), R90, R180, R270, M0 (mirrored), M90

Here is a reference .asc file for formatting:

```
Version 4
SHEET 1 880 680
SYMBOL opamp2 400 128 R0
SYMATTR InstName U1
SYMATTR Value ADA4627
SYMBOL res 272 128 R90
SYMATTR InstName R5
SYMATTR Value 1000 noiseless
WIRE 416 144 336 144
FLAG 160 272 0
FLAG 608 176 OUT
TEXT 400 450 Left 2 !.param RINP=1k PSV=15
```

All coordinates must be integers. Snap to multiples of 16 when possible.
Output ONLY the .asc file content, nothing else. No explanations, no markdown fences.
```

- [ ] **Step 2: Implement the refinement service**

Create `backend/services/refinement.py`:
```python
import json
from pathlib import Path

from services.ollama_client import chat_text
from services.asc_generator import SchematicIR, generate_asc

REFINE_MODEL = "qwen3:14b"
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _ir_to_json_prompt(ir: SchematicIR) -> str:
    """Convert SchematicIR to a JSON string for the refinement prompt."""
    data = {
        "sheet": {"width": ir.sheet_width, "height": ir.sheet_height},
        "components": [],
        "wires": [],
        "flags": [],
        "text": [],
    }
    for c in ir.components:
        comp = {
            "type": c.type,
            "instanceName": c.instance_name,
            "value": c.value,
            "x": c.x,
            "y": c.y,
            "rotation": c.rotation,
        }
        if c.value2:
            comp["value2"] = c.value2
        data["components"].append(comp)

    for w in ir.wires:
        data["wires"].append({"x1": w.x1, "y1": w.y1, "x2": w.x2, "y2": w.y2})

    for f in ir.flags:
        data["flags"].append({"name": f.name, "x": f.x, "y": f.y})

    for t in ir.texts:
        data["text"].append({"content": t.content, "x": t.x, "y": t.y})

    return json.dumps(data, indent=2)


def _clean_asc_response(text: str) -> str:
    """Strip markdown fences or extra text from model response."""
    lines = text.strip().split("\n")
    # Remove markdown code fences if present
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines) + "\n"


async def refine_to_asc(ir: SchematicIR) -> str:
    """Use text model to refine JSON IR into .asc, with deterministic fallback."""
    # First, generate a deterministic .asc as baseline
    deterministic_asc = generate_asc(ir)

    system_prompt = _load_prompt("refine_system.txt")
    user_prompt = (
        f"Convert this circuit JSON into a valid .asc file:\n\n"
        f"{_ir_to_json_prompt(ir)}\n\n"
        f"Here is a deterministic draft for reference. Improve it if needed "
        f"(fix coordinates, add missing WINDOW lines, etc.), or return it as-is "
        f"if it looks correct:\n\n{deterministic_asc}"
    )

    try:
        response = await chat_text(REFINE_MODEL, system_prompt, user_prompt)
        refined = _clean_asc_response(response)
        # Validate the refined version starts correctly
        if refined.startswith("Version 4"):
            return refined
        # If model produced garbage, fall back to deterministic
        return deterministic_asc
    except Exception:
        # On any Ollama error, return the deterministic version
        return deterministic_asc
```

- [ ] **Step 3: Write tests for helper functions**

Create `backend/tests/test_refinement.py`:
```python
from services.refinement import _ir_to_json_prompt, _clean_asc_response
from services.asc_generator import SchematicIR


def test_ir_to_json_prompt_structure():
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    ir.add_component("res", "R1", "1k", 100, 100, "R0")
    ir.add_wire(100, 100, 200, 100)
    ir.add_flag("0", 150, 150)
    ir.add_text(".tran 1", 300, 300)

    result = _ir_to_json_prompt(ir)
    import json
    data = json.loads(result)
    assert data["sheet"]["width"] == 880
    assert len(data["components"]) == 1
    assert data["components"][0]["instanceName"] == "R1"
    assert len(data["wires"]) == 1
    assert len(data["flags"]) == 1
    assert len(data["text"]) == 1


def test_ir_to_json_prompt_value2():
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    ir.add_component("voltage", "V1", "5", 100, 100, "R0", value2="AC 1")
    result = _ir_to_json_prompt(ir)
    import json
    data = json.loads(result)
    assert data["components"][0]["value2"] == "AC 1"


def test_clean_asc_response_plain():
    text = "Version 4\nSHEET 1 880 680\n"
    assert _clean_asc_response(text) == "Version 4\nSHEET 1 880 680\n"


def test_clean_asc_response_with_fences():
    text = "```\nVersion 4\nSHEET 1 880 680\n```"
    assert _clean_asc_response(text) == "Version 4\nSHEET 1 880 680\n"


def test_clean_asc_response_with_language_fence():
    text = "```asc\nVersion 4\nSHEET 1 880 680\n```"
    assert _clean_asc_response(text) == "Version 4\nSHEET 1 880 680\n"
```

- [ ] **Step 4: Run tests**

Run:
```bash
cd backend && python -m pytest tests/test_refinement.py -v
```
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/refinement.py backend/prompts/refine_system.txt backend/tests/test_refinement.py
git commit -m "feat: add refinement service with deterministic fallback"
```

---

### Task 7: API Routes

**Files:**
- Create: `backend/api/routes.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_routes.py`

- [ ] **Step 1: Implement API routes**

Create `backend/api/routes.py`:
```python
import json
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from services.vision import analyze_image
from services.refinement import refine_to_asc
from services.asc_generator import SchematicIR, generate_asc
from services.validator import validate_asc

router = APIRouter(prefix="/api")

DICTIONARY_DIR = Path(__file__).parent.parent.parent / "dictionary"


@router.get("/dictionary")
async def get_dictionary():
    components = json.loads(
        (DICTIONARY_DIR / "components.json").read_text(encoding="utf-8")
    )
    directives = json.loads(
        (DICTIONARY_DIR / "directives.json").read_text(encoding="utf-8")
    )
    return {"components": components["components"], "directives": directives}


class GenerateResponse(BaseModel):
    ir: dict
    asc: str
    validation: dict


@router.post("/generate", response_model=GenerateResponse)
async def generate(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")

    image_bytes = await file.read()
    ir, raw_json = await analyze_image(image_bytes)
    asc_text = await refine_to_asc(ir)
    validation = validate_asc(asc_text)

    return GenerateResponse(
        ir=raw_json,
        asc=asc_text,
        validation={"valid": validation.valid, "errors": validation.errors},
    )


class RefineRequest(BaseModel):
    ir: dict


@router.post("/refine")
async def refine(request: RefineRequest):
    ir = _dict_to_ir(request.ir)
    asc_text = generate_asc(ir)
    validation = validate_asc(asc_text)
    return {
        "asc": asc_text,
        "validation": {"valid": validation.valid, "errors": validation.errors},
    }


class ValidateRequest(BaseModel):
    asc: str


@router.post("/validate")
async def validate(request: ValidateRequest):
    result = validate_asc(request.asc)
    return {"valid": result.valid, "errors": result.errors, "warnings": result.warnings}


def _dict_to_ir(data: dict) -> SchematicIR:
    sheet = data.get("sheet", {"width": 880, "height": 680})
    ir = SchematicIR(sheet_width=sheet["width"], sheet_height=sheet["height"])

    for comp in data.get("components", []):
        ir.add_component(
            comp_type=comp["type"],
            instance_name=comp["instanceName"],
            value=comp["value"],
            x=int(comp["position"]["x"]) if "position" in comp else int(comp["x"]),
            y=int(comp["position"]["y"]) if "position" in comp else int(comp["y"]),
            rotation=comp.get("rotation", "R0"),
            value2=comp.get("value2"),
        )

    for wire in data.get("wires", []):
        if "from" in wire:
            ir.add_wire(
                int(wire["from"]["x"]), int(wire["from"]["y"]),
                int(wire["to"]["x"]), int(wire["to"]["y"]),
            )
        else:
            ir.add_wire(int(wire["x1"]), int(wire["y1"]), int(wire["x2"]), int(wire["y2"]))

    for flag in data.get("flags", []):
        pos = flag.get("position", flag)
        name = flag["name"]
        ir.add_flag(name, int(pos["x"]), int(pos["y"]))

    for text in data.get("text", []):
        pos = text.get("position", text)
        ir.add_text(text["content"], int(pos["x"]), int(pos["y"]))

    return ir
```

- [ ] **Step 2: Mount routes in main.py**

Replace `backend/main.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router

app = FastAPI(title="image2asc")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 3: Write route tests (dictionary and validate endpoints)**

Create `backend/tests/test_routes.py`:
```python
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
```

- [ ] **Step 4: Install test dependencies and run**

Add `pytest`, `pytest-asyncio`, and `anyio` to `backend/requirements.txt`:
```
fastapi==0.115.0
uvicorn[standard]==0.30.0
httpx==0.27.0
python-multipart==0.0.9
pytest==8.3.0
pytest-asyncio==0.24.0
anyio==4.6.0
```

Run:
```bash
cd backend && pip install -r requirements.txt && python -m pytest tests/test_routes.py -v
```
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes.py backend/main.py backend/tests/test_routes.py backend/requirements.txt
git commit -m "feat: add API routes for generate, refine, validate, dictionary"
```

---

### Task 8: Frontend Types and API Client

**Files:**
- Create: `frontend/src/types/schematic.ts`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/gridSnap.ts`
- Create: `frontend/src/lib/ascGenerator.ts`

- [ ] **Step 1: Define TypeScript types**

Create `frontend/src/types/schematic.ts`:
```ts
export interface Position {
  x: number;
  y: number;
}

export interface Component {
  id: string; // client-side UUID
  type: string;
  instanceName: string;
  value: string;
  position: Position;
  rotation: string;
  value2?: string;
}

export interface Wire {
  id: string;
  from: Position;
  to: Position;
}

export interface Flag {
  id: string;
  name: string;
  position: Position;
}

export interface TextDirective {
  id: string;
  content: string;
  position: Position;
}

export interface Schematic {
  sheet: { width: number; height: number };
  components: Component[];
  wires: Wire[];
  flags: Flag[];
  text: TextDirective[];
}

export interface DictionaryComponent {
  id: string;
  category: string;
  displayName: string;
  symbol: {
    width: number;
    height: number;
    svgPath: string;
  };
  pins: { name: string; position: [number, number]; direction: string }[];
  ascSyntax: {
    symbolName: string;
    attributes: string[];
  };
  rotations: string[];
}

export interface Dictionary {
  components: Record<string, DictionaryComponent>;
  directives: {
    directives: Record<string, { syntax: string; description: string }>;
    valueFormats?: Record<string, string>;
  };
}

export interface GenerateResponse {
  ir: {
    sheet: { width: number; height: number };
    components: Array<{
      type: string;
      instanceName: string;
      value: string;
      position: Position;
      rotation: string;
      value2?: string;
    }>;
    wires: Array<{ from: Position; to: Position }>;
    flags: Array<{ name: string; position: Position }>;
    text: Array<{ content: string; position: Position }>;
  };
  asc: string;
  validation: { valid: boolean; errors: string[] };
}
```

- [ ] **Step 2: Create API client**

Create `frontend/src/lib/api.ts`:
```ts
import type { Dictionary, GenerateResponse } from "../types/schematic";

const BASE_URL = "http://localhost:8000/api";

export async function fetchDictionary(): Promise<Dictionary> {
  const resp = await fetch(`${BASE_URL}/dictionary`);
  if (!resp.ok) throw new Error(`Dictionary fetch failed: ${resp.status}`);
  return resp.json();
}

export async function generateFromImage(
  file: File
): Promise<GenerateResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await fetch(`${BASE_URL}/generate`, {
    method: "POST",
    body: formData,
  });
  if (!resp.ok) throw new Error(`Generate failed: ${resp.status}`);
  return resp.json();
}

export async function refineIR(
  ir: object
): Promise<{ asc: string; validation: { valid: boolean; errors: string[] } }> {
  const resp = await fetch(`${BASE_URL}/refine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ir }),
  });
  if (!resp.ok) throw new Error(`Refine failed: ${resp.status}`);
  return resp.json();
}

export async function validateAsc(
  asc: string
): Promise<{ valid: boolean; errors: string[] }> {
  const resp = await fetch(`${BASE_URL}/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ asc }),
  });
  if (!resp.ok) throw new Error(`Validate failed: ${resp.status}`);
  return resp.json();
}
```

- [ ] **Step 3: Create grid snap utility**

Create `frontend/src/lib/gridSnap.ts`:
```ts
const GRID_SIZE = 16;

export function snapToGrid(value: number): number {
  return Math.round(value / GRID_SIZE) * GRID_SIZE;
}

export function snapPosition(x: number, y: number): { x: number; y: number } {
  return { x: snapToGrid(x), y: snapToGrid(y) };
}
```

- [ ] **Step 4: Create client-side .asc generator**

Create `frontend/src/lib/ascGenerator.ts`:
```ts
import type { Schematic } from "../types/schematic";

export function generateAsc(schematic: Schematic): string {
  const lines: string[] = [];

  lines.push("Version 4");
  lines.push(`SHEET 1 ${schematic.sheet.width} ${schematic.sheet.height}`);

  for (const comp of schematic.components) {
    lines.push(
      `SYMBOL ${comp.type} ${comp.position.x} ${comp.position.y} ${comp.rotation}`
    );
    lines.push(`SYMATTR InstName ${comp.instanceName}`);
    lines.push(`SYMATTR Value ${comp.value}`);
    if (comp.value2) {
      lines.push(`SYMATTR Value2 ${comp.value2}`);
    }
  }

  for (const wire of schematic.wires) {
    lines.push(
      `WIRE ${wire.from.x} ${wire.from.y} ${wire.to.x} ${wire.to.y}`
    );
  }

  for (const flag of schematic.flags) {
    lines.push(`FLAG ${flag.position.x} ${flag.position.y} ${flag.name}`);
  }

  for (const text of schematic.text) {
    const prefix = text.content.startsWith(".") ? "!" : "";
    lines.push(
      `TEXT ${text.position.x} ${text.position.y} Left 2 ${prefix}${text.content}`
    );
  }

  return lines.join("\n") + "\n";
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/ frontend/src/lib/
git commit -m "feat: add frontend types, API client, grid snap, and .asc generator"
```

---

### Task 9: Schematic State Hook

**Files:**
- Create: `frontend/src/hooks/useSchematic.ts`
- Create: `frontend/src/hooks/useHistory.ts`

- [ ] **Step 1: Create undo/redo history hook**

Create `frontend/src/hooks/useHistory.ts`:
```ts
import { useCallback, useRef, useState } from "react";

export function useHistory<T>(initial: T) {
  const [state, setState] = useState<T>(initial);
  const pastRef = useRef<T[]>([]);
  const futureRef = useRef<T[]>([]);

  const set = useCallback(
    (newState: T) => {
      pastRef.current.push(state);
      futureRef.current = [];
      setState(newState);
    },
    [state]
  );

  const undo = useCallback(() => {
    if (pastRef.current.length === 0) return;
    const prev = pastRef.current.pop()!;
    futureRef.current.push(state);
    setState(prev);
  }, [state]);

  const redo = useCallback(() => {
    if (futureRef.current.length === 0) return;
    const next = futureRef.current.pop()!;
    pastRef.current.push(state);
    setState(next);
  }, [state]);

  return {
    state,
    set,
    undo,
    redo,
    canUndo: pastRef.current.length > 0,
    canRedo: futureRef.current.length > 0,
  };
}
```

- [ ] **Step 2: Create schematic state hook**

Create `frontend/src/hooks/useSchematic.ts`:
```ts
import { useCallback } from "react";
import type {
  Schematic,
  Component,
  Wire,
  Flag,
  TextDirective,
  Position,
  GenerateResponse,
} from "../types/schematic";
import { useHistory } from "./useHistory";
import { snapToGrid } from "../lib/gridSnap";

let nextId = 1;
function genId(): string {
  return `item-${nextId++}`;
}

const EMPTY_SCHEMATIC: Schematic = {
  sheet: { width: 880, height: 680 },
  components: [],
  wires: [],
  flags: [],
  text: [],
};

export function useSchematic() {
  const { state: schematic, set, undo, redo, canUndo, canRedo } =
    useHistory<Schematic>(structuredClone(EMPTY_SCHEMATIC));

  const loadFromGenerateResponse = useCallback(
    (resp: GenerateResponse) => {
      const s: Schematic = {
        sheet: resp.ir.sheet,
        components: resp.ir.components.map((c) => ({
          id: genId(),
          type: c.type,
          instanceName: c.instanceName,
          value: c.value,
          position: c.position,
          rotation: c.rotation,
          value2: c.value2,
        })),
        wires: resp.ir.wires.map((w) => ({
          id: genId(),
          from: w.from,
          to: w.to,
        })),
        flags: resp.ir.flags.map((f) => ({
          id: genId(),
          name: f.name,
          position: f.position,
        })),
        text: resp.ir.text.map((t) => ({
          id: genId(),
          content: t.content,
          position: t.position,
        })),
      };
      set(s);
    },
    [set]
  );

  const moveComponent = useCallback(
    (id: string, pos: Position) => {
      const snapped = { x: snapToGrid(pos.x), y: snapToGrid(pos.y) };
      set({
        ...schematic,
        components: schematic.components.map((c) =>
          c.id === id ? { ...c, position: snapped } : c
        ),
      });
    },
    [schematic, set]
  );

  const updateComponent = useCallback(
    (id: string, updates: Partial<Component>) => {
      set({
        ...schematic,
        components: schematic.components.map((c) =>
          c.id === id ? { ...c, ...updates } : c
        ),
      });
    },
    [schematic, set]
  );

  const addComponent = useCallback(
    (type: string, instanceName: string, value: string, pos: Position) => {
      const snapped = { x: snapToGrid(pos.x), y: snapToGrid(pos.y) };
      const comp: Component = {
        id: genId(),
        type,
        instanceName,
        value,
        position: snapped,
        rotation: "R0",
      };
      set({ ...schematic, components: [...schematic.components, comp] });
    },
    [schematic, set]
  );

  const deleteComponent = useCallback(
    (id: string) => {
      set({
        ...schematic,
        components: schematic.components.filter((c) => c.id !== id),
      });
    },
    [schematic, set]
  );

  const addWire = useCallback(
    (from: Position, to: Position) => {
      const wire: Wire = {
        id: genId(),
        from: { x: snapToGrid(from.x), y: snapToGrid(from.y) },
        to: { x: snapToGrid(to.x), y: snapToGrid(to.y) },
      };
      set({ ...schematic, wires: [...schematic.wires, wire] });
    },
    [schematic, set]
  );

  const deleteWire = useCallback(
    (id: string) => {
      set({
        ...schematic,
        wires: schematic.wires.filter((w) => w.id !== id),
      });
    },
    [schematic, set]
  );

  const addFlag = useCallback(
    (name: string, pos: Position) => {
      const flag: Flag = {
        id: genId(),
        name,
        position: { x: snapToGrid(pos.x), y: snapToGrid(pos.y) },
      };
      set({ ...schematic, flags: [...schematic.flags, flag] });
    },
    [schematic, set]
  );

  const deleteFlag = useCallback(
    (id: string) => {
      set({
        ...schematic,
        flags: schematic.flags.filter((f) => f.id !== id),
      });
    },
    [schematic, set]
  );

  const toIR = useCallback(() => {
    return {
      sheet: schematic.sheet,
      components: schematic.components.map((c) => ({
        type: c.type,
        instanceName: c.instanceName,
        value: c.value,
        position: c.position,
        rotation: c.rotation,
        value2: c.value2,
      })),
      wires: schematic.wires.map((w) => ({ from: w.from, to: w.to })),
      flags: schematic.flags.map((f) => ({
        name: f.name,
        position: f.position,
      })),
      text: schematic.text.map((t) => ({
        content: t.content,
        position: t.position,
      })),
    };
  }, [schematic]);

  return {
    schematic,
    loadFromGenerateResponse,
    moveComponent,
    updateComponent,
    addComponent,
    deleteComponent,
    addWire,
    deleteWire,
    addFlag,
    deleteFlag,
    toIR,
    undo,
    redo,
    canUndo,
    canRedo,
  };
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat: add useSchematic and useHistory hooks"
```

---

### Task 10: Toolbar Component

**Files:**
- Create: `frontend/src/components/Toolbar.tsx`

- [ ] **Step 1: Implement Toolbar**

Create `frontend/src/components/Toolbar.tsx`:
```tsx
import { useRef } from "react";

interface ToolbarProps {
  onUpload: (file: File) => void;
  onGenerate: () => void;
  onExport: () => void;
  onUndo: () => void;
  onRedo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  generating: boolean;
  imageLoaded: boolean;
}

export function Toolbar({
  onUpload,
  onGenerate,
  onExport,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
  generating,
  imageLoaded,
}: ToolbarProps) {
  const fileRef = useRef<HTMLInputElement>(null);

  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        padding: 8,
        borderBottom: "1px solid #ccc",
        alignItems: "center",
        background: "#f5f5f5",
      }}
    >
      <strong>image2asc</strong>
      <div style={{ width: 1, height: 24, background: "#ccc" }} />

      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        style={{ display: "none" }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onUpload(file);
        }}
      />
      <button onClick={() => fileRef.current?.click()}>Upload Image</button>

      <button onClick={onGenerate} disabled={!imageLoaded || generating}>
        {generating ? "Generating..." : "Generate"}
      </button>

      <button onClick={onExport}>Export .asc</button>

      <div style={{ width: 1, height: 24, background: "#ccc" }} />

      <button onClick={onUndo} disabled={!canUndo}>
        Undo
      </button>
      <button onClick={onRedo} disabled={!canRedo}>
        Redo
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Toolbar.tsx
git commit -m "feat: add Toolbar component"
```

---

### Task 11: Image Panel Component

**Files:**
- Create: `frontend/src/components/ImagePanel.tsx`

- [ ] **Step 1: Implement ImagePanel**

Create `frontend/src/components/ImagePanel.tsx`:
```tsx
interface ImagePanelProps {
  imageUrl: string | null;
}

export function ImagePanel({ imageUrl }: ImagePanelProps) {
  return (
    <div
      style={{
        flex: 1,
        borderRight: "1px solid #ccc",
        overflow: "auto",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#fafafa",
      }}
    >
      {imageUrl ? (
        <img
          src={imageUrl}
          alt="LTspice schematic"
          style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
        />
      ) : (
        <span style={{ color: "#999" }}>Upload an LTspice screenshot</span>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ImagePanel.tsx
git commit -m "feat: add ImagePanel component"
```

---

### Task 12: SVG Visual Editor

**Files:**
- Create: `frontend/src/components/Editor.tsx`

- [ ] **Step 1: Implement the SVG editor with component rendering, selection, and dragging**

Create `frontend/src/components/Editor.tsx`:
```tsx
import { useRef, useState, useCallback, useEffect } from "react";
import type {
  Schematic,
  Component,
  DictionaryComponent,
  Dictionary,
  Position,
} from "../types/schematic";

interface EditorProps {
  schematic: Schematic;
  dictionary: Dictionary | null;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onMoveComponent: (id: string, pos: Position) => void;
  onAddWire: (from: Position, to: Position) => void;
  mode: "select" | "wire";
}

export function Editor({
  schematic,
  dictionary,
  selectedId,
  onSelect,
  onMoveComponent,
  onAddWire,
  mode,
}: EditorProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [viewBox, setViewBox] = useState({ x: 0, y: 0, w: 880, h: 680 });
  const [dragging, setDragging] = useState<{
    id: string;
    offsetX: number;
    offsetY: number;
  } | null>(null);
  const [wireStart, setWireStart] = useState<Position | null>(null);
  const [wirePreview, setWirePreview] = useState<Position | null>(null);
  const [panning, setPanning] = useState<{
    startX: number;
    startY: number;
    startVX: number;
    startVY: number;
  } | null>(null);

  const svgPoint = useCallback(
    (clientX: number, clientY: number): Position => {
      const svg = svgRef.current;
      if (!svg) return { x: 0, y: 0 };
      const rect = svg.getBoundingClientRect();
      const x = ((clientX - rect.left) / rect.width) * viewBox.w + viewBox.x;
      const y = ((clientY - rect.top) / rect.height) * viewBox.h + viewBox.y;
      return { x: Math.round(x), y: Math.round(y) };
    },
    [viewBox]
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.button === 1) {
        // Middle click: pan
        setPanning({
          startX: e.clientX,
          startY: e.clientY,
          startVX: viewBox.x,
          startVY: viewBox.y,
        });
        e.preventDefault();
        return;
      }

      if (mode === "wire" && e.button === 0) {
        const pos = svgPoint(e.clientX, e.clientY);
        if (!wireStart) {
          setWireStart(pos);
          setWirePreview(pos);
        } else {
          onAddWire(wireStart, pos);
          setWireStart(null);
          setWirePreview(null);
        }
        return;
      }

      if (mode === "select" && e.button === 0) {
        // Clicking empty space deselects
        onSelect(null);
      }
    },
    [mode, wireStart, svgPoint, onAddWire, onSelect, viewBox]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (panning) {
        const svg = svgRef.current;
        if (!svg) return;
        const rect = svg.getBoundingClientRect();
        const dx =
          ((e.clientX - panning.startX) / rect.width) * viewBox.w;
        const dy =
          ((e.clientY - panning.startY) / rect.height) * viewBox.h;
        setViewBox((v) => ({
          ...v,
          x: panning.startVX - dx,
          y: panning.startVY - dy,
        }));
        return;
      }

      if (dragging) {
        const pos = svgPoint(e.clientX, e.clientY);
        onMoveComponent(dragging.id, {
          x: pos.x - dragging.offsetX,
          y: pos.y - dragging.offsetY,
        });
        return;
      }

      if (wireStart) {
        setWirePreview(svgPoint(e.clientX, e.clientY));
      }
    },
    [panning, dragging, wireStart, svgPoint, onMoveComponent, viewBox]
  );

  const handleMouseUp = useCallback(() => {
    setDragging(null);
    setPanning(null);
  }, []);

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      e.preventDefault();
      const scale = e.deltaY > 0 ? 1.1 : 0.9;
      const pos = svgPoint(e.clientX, e.clientY);
      setViewBox((v) => {
        const newW = v.w * scale;
        const newH = v.h * scale;
        const newX = pos.x - (pos.x - v.x) * scale;
        const newY = pos.y - (pos.y - v.y) * scale;
        return { x: newX, y: newY, w: newW, h: newH };
      });
    },
    [svgPoint]
  );

  const startDrag = useCallback(
    (compId: string, e: React.MouseEvent) => {
      e.stopPropagation();
      onSelect(compId);
      if (mode !== "select") return;
      const comp = schematic.components.find((c) => c.id === compId);
      if (!comp) return;
      const pos = svgPoint(e.clientX, e.clientY);
      setDragging({
        id: compId,
        offsetX: pos.x - comp.position.x,
        offsetY: pos.y - comp.position.y,
      });
    },
    [mode, schematic.components, svgPoint, onSelect]
  );

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setWireStart(null);
        setWirePreview(null);
        onSelect(null);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onSelect]);

  const renderComponent = (comp: Component) => {
    const dictComp = dictionary?.components[comp.type];
    const isSelected = comp.id === selectedId;

    return (
      <g
        key={comp.id}
        transform={`translate(${comp.position.x}, ${comp.position.y})`}
        onMouseDown={(e) => startDrag(comp.id, e)}
        style={{ cursor: mode === "select" ? "grab" : "default" }}
      >
        {/* Selection highlight */}
        {isSelected && dictComp && (
          <rect
            x={-4}
            y={-4}
            width={dictComp.symbol.width + 8}
            height={dictComp.symbol.height + 8}
            fill="none"
            stroke="#2196F3"
            strokeWidth={2}
            strokeDasharray="4,4"
          />
        )}

        {/* Component shape */}
        {dictComp ? (
          <path
            d={dictComp.symbol.svgPath}
            fill="none"
            stroke="#0000CC"
            strokeWidth={2}
          />
        ) : (
          <rect
            width={64}
            height={32}
            fill="none"
            stroke="#0000CC"
            strokeWidth={2}
          />
        )}

        {/* Pins */}
        {dictComp?.pins.map((pin) => (
          <circle
            key={pin.name}
            cx={pin.position[0]}
            cy={pin.position[1]}
            r={3}
            fill="#0000CC"
          />
        ))}

        {/* Label */}
        <text
          x={dictComp ? dictComp.symbol.width / 2 : 32}
          y={-8}
          textAnchor="middle"
          fontSize={12}
          fill="#0000CC"
        >
          {comp.instanceName}
        </text>

        {/* Value */}
        <text
          x={dictComp ? dictComp.symbol.width / 2 : 32}
          y={(dictComp?.symbol.height ?? 32) + 14}
          textAnchor="middle"
          fontSize={10}
          fill="#0000CC"
        >
          {comp.value}
        </text>
      </g>
    );
  };

  return (
    <svg
      ref={svgRef}
      viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
      style={{ flex: 2, background: "#e8e8e8", cursor: mode === "wire" ? "crosshair" : "default" }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onWheel={handleWheel}
    >
      {/* Grid */}
      <defs>
        <pattern id="grid" width={16} height={16} patternUnits="userSpaceOnUse">
          <circle cx={0} cy={0} r={0.5} fill="#ccc" />
        </pattern>
      </defs>
      <rect
        x={viewBox.x}
        y={viewBox.y}
        width={viewBox.w}
        height={viewBox.h}
        fill="url(#grid)"
      />

      {/* Wires */}
      {schematic.wires.map((wire) => (
        <line
          key={wire.id}
          x1={wire.from.x}
          y1={wire.from.y}
          x2={wire.to.x}
          y2={wire.to.y}
          stroke="#0000CC"
          strokeWidth={2}
          onClick={(e) => {
            e.stopPropagation();
            onSelect(wire.id);
          }}
          style={{ cursor: "pointer" }}
        />
      ))}

      {/* Wire preview */}
      {wireStart && wirePreview && (
        <line
          x1={wireStart.x}
          y1={wireStart.y}
          x2={wirePreview.x}
          y2={wirePreview.y}
          stroke="#2196F3"
          strokeWidth={1}
          strokeDasharray="4,4"
          pointerEvents="none"
        />
      )}

      {/* Components */}
      {schematic.components.map(renderComponent)}

      {/* Flags */}
      {schematic.flags.map((flag) => (
        <g key={flag.id} transform={`translate(${flag.position.x}, ${flag.position.y})`}>
          {flag.name === "0" ? (
            // Ground symbol
            <>
              <line x1={0} y1={0} x2={0} y2={10} stroke="#0000CC" strokeWidth={2} />
              <line x1={-10} y1={10} x2={10} y2={10} stroke="#0000CC" strokeWidth={2} />
              <line x1={-6} y1={14} x2={6} y2={14} stroke="#0000CC" strokeWidth={2} />
              <line x1={-2} y1={18} x2={2} y2={18} stroke="#0000CC" strokeWidth={2} />
            </>
          ) : (
            // Net label
            <>
              <line x1={0} y1={0} x2={0} y2={-5} stroke="#0000CC" strokeWidth={1} />
              <text x={2} y={-8} fontSize={11} fill="#0000CC">
                {flag.name}
              </text>
            </>
          )}
        </g>
      ))}

      {/* Text directives */}
      {schematic.text.map((t) => (
        <text
          key={t.id}
          x={t.position.x}
          y={t.position.y}
          fontSize={11}
          fill="#333"
        >
          {t.content}
        </text>
      ))}
    </svg>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Editor.tsx
git commit -m "feat: add SVG visual editor with drag, pan, zoom, and wire drawing"
```

---

### Task 13: Property Panel and Component Palette

**Files:**
- Create: `frontend/src/components/PropertyPanel.tsx`
- Create: `frontend/src/components/ComponentPalette.tsx`

- [ ] **Step 1: Implement PropertyPanel**

Create `frontend/src/components/PropertyPanel.tsx`:
```tsx
import type { Component, Schematic } from "../types/schematic";

interface PropertyPanelProps {
  schematic: Schematic;
  selectedId: string | null;
  onUpdateComponent: (id: string, updates: Partial<Component>) => void;
  onDeleteComponent: (id: string) => void;
  onDeleteWire: (id: string) => void;
  onDeleteFlag: (id: string) => void;
}

export function PropertyPanel({
  schematic,
  selectedId,
  onUpdateComponent,
  onDeleteComponent,
  onDeleteWire,
  onDeleteFlag,
}: PropertyPanelProps) {
  if (!selectedId) {
    return (
      <div style={{ padding: 12, color: "#999", fontSize: 13 }}>
        Select a component to edit its properties
      </div>
    );
  }

  const comp = schematic.components.find((c) => c.id === selectedId);
  if (comp) {
    return (
      <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        <h4 style={{ margin: 0 }}>Component: {comp.type}</h4>

        <label style={{ fontSize: 12 }}>
          Instance Name
          <input
            value={comp.instanceName}
            onChange={(e) =>
              onUpdateComponent(comp.id, { instanceName: e.target.value })
            }
            style={{ width: "100%", marginTop: 2 }}
          />
        </label>

        <label style={{ fontSize: 12 }}>
          Value
          <input
            value={comp.value}
            onChange={(e) =>
              onUpdateComponent(comp.id, { value: e.target.value })
            }
            style={{ width: "100%", marginTop: 2 }}
          />
        </label>

        {comp.value2 !== undefined && (
          <label style={{ fontSize: 12 }}>
            Value2
            <input
              value={comp.value2 ?? ""}
              onChange={(e) =>
                onUpdateComponent(comp.id, { value2: e.target.value })
              }
              style={{ width: "100%", marginTop: 2 }}
            />
          </label>
        )}

        <label style={{ fontSize: 12 }}>
          Rotation
          <select
            value={comp.rotation}
            onChange={(e) =>
              onUpdateComponent(comp.id, { rotation: e.target.value })
            }
            style={{ width: "100%", marginTop: 2 }}
          >
            {["R0", "R90", "R180", "R270", "M0", "M90"].map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>

        <label style={{ fontSize: 12 }}>
          X: {comp.position.x}, Y: {comp.position.y}
        </label>

        <button
          onClick={() => onDeleteComponent(comp.id)}
          style={{ color: "red", marginTop: 8 }}
        >
          Delete Component
        </button>
      </div>
    );
  }

  const wire = schematic.wires.find((w) => w.id === selectedId);
  if (wire) {
    return (
      <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        <h4 style={{ margin: 0 }}>Wire</h4>
        <span style={{ fontSize: 12 }}>
          ({wire.from.x}, {wire.from.y}) to ({wire.to.x}, {wire.to.y})
        </span>
        <button
          onClick={() => onDeleteWire(wire.id)}
          style={{ color: "red", marginTop: 8 }}
        >
          Delete Wire
        </button>
      </div>
    );
  }

  const flag = schematic.flags.find((f) => f.id === selectedId);
  if (flag) {
    return (
      <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        <h4 style={{ margin: 0 }}>Flag: {flag.name}</h4>
        <button
          onClick={() => onDeleteFlag(flag.id)}
          style={{ color: "red", marginTop: 8 }}
        >
          Delete Flag
        </button>
      </div>
    );
  }

  return <div style={{ padding: 12, color: "#999" }}>Unknown selection</div>;
}
```

- [ ] **Step 2: Implement ComponentPalette**

Create `frontend/src/components/ComponentPalette.tsx`:
```tsx
import type { Dictionary } from "../types/schematic";

interface ComponentPaletteProps {
  dictionary: Dictionary | null;
  onAddComponent: (type: string) => void;
  mode: "select" | "wire";
  onModeChange: (mode: "select" | "wire") => void;
  onAddFlag: () => void;
}

export function ComponentPalette({
  dictionary,
  onAddComponent,
  mode,
  onModeChange,
  onAddFlag,
}: ComponentPaletteProps) {
  if (!dictionary) {
    return (
      <div style={{ padding: 8, color: "#999", fontSize: 12 }}>
        Loading dictionary...
      </div>
    );
  }

  const categories = new Map<string, string[]>();
  for (const [id, comp] of Object.entries(dictionary.components)) {
    const cat = comp.category;
    if (!categories.has(cat)) categories.set(cat, []);
    categories.get(cat)!.push(id);
  }

  return (
    <div
      style={{
        width: 160,
        borderRight: "1px solid #ccc",
        overflow: "auto",
        fontSize: 12,
        background: "#fafafa",
      }}
    >
      <div style={{ padding: 8, borderBottom: "1px solid #eee" }}>
        <strong>Tools</strong>
        <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
          <button
            onClick={() => onModeChange("select")}
            style={{
              flex: 1,
              fontWeight: mode === "select" ? "bold" : "normal",
              background: mode === "select" ? "#ddd" : "#fff",
            }}
          >
            Select
          </button>
          <button
            onClick={() => onModeChange("wire")}
            style={{
              flex: 1,
              fontWeight: mode === "wire" ? "bold" : "normal",
              background: mode === "wire" ? "#ddd" : "#fff",
            }}
          >
            Wire
          </button>
        </div>
        <button onClick={onAddFlag} style={{ width: "100%", marginTop: 4 }}>
          + Flag
        </button>
      </div>

      {[...categories.entries()].map(([cat, ids]) => (
        <div key={cat} style={{ padding: 8, borderBottom: "1px solid #eee" }}>
          <strong style={{ textTransform: "capitalize" }}>{cat}</strong>
          <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 4 }}>
            {ids.map((id) => (
              <button
                key={id}
                onClick={() => onAddComponent(id)}
                style={{ textAlign: "left", padding: "2px 4px" }}
              >
                {dictionary.components[id].displayName}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PropertyPanel.tsx frontend/src/components/ComponentPalette.tsx
git commit -m "feat: add PropertyPanel and ComponentPalette components"
```

---

### Task 14: .asc Preview Component

**Files:**
- Create: `frontend/src/components/AscPreview.tsx`

- [ ] **Step 1: Implement AscPreview**

Create `frontend/src/components/AscPreview.tsx`:
```tsx
interface AscPreviewProps {
  ascText: string;
  validation: { valid: boolean; errors: string[] } | null;
}

export function AscPreview({ ascText, validation }: AscPreviewProps) {
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        borderLeft: "1px solid #ccc",
      }}
    >
      <div
        style={{
          padding: "4px 8px",
          borderBottom: "1px solid #ccc",
          fontSize: 12,
          fontWeight: "bold",
          display: "flex",
          justifyContent: "space-between",
        }}
      >
        <span>.asc Preview</span>
        {validation && (
          <span style={{ color: validation.valid ? "green" : "red" }}>
            {validation.valid ? "Valid" : `${validation.errors.length} error(s)`}
          </span>
        )}
      </div>

      {validation && !validation.valid && (
        <div
          style={{
            padding: 8,
            background: "#fff0f0",
            fontSize: 11,
            color: "red",
            borderBottom: "1px solid #fcc",
          }}
        >
          {validation.errors.map((e, i) => (
            <div key={i}>{e}</div>
          ))}
        </div>
      )}

      <pre
        style={{
          flex: 1,
          margin: 0,
          padding: 8,
          overflow: "auto",
          fontSize: 11,
          fontFamily: "monospace",
          background: "#fafafa",
          whiteSpace: "pre-wrap",
        }}
      >
        {ascText || "No .asc content yet. Upload an image and click Generate."}
      </pre>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/AscPreview.tsx
git commit -m "feat: add AscPreview component with validation display"
```

---

### Task 15: Wire Everything Together in App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Replace App.tsx with full integration**

Replace `frontend/src/App.tsx`:
```tsx
import { useState, useEffect, useCallback } from "react";
import { Toolbar } from "./components/Toolbar";
import { ImagePanel } from "./components/ImagePanel";
import { Editor } from "./components/Editor";
import { AscPreview } from "./components/AscPreview";
import { PropertyPanel } from "./components/PropertyPanel";
import { ComponentPalette } from "./components/ComponentPalette";
import { useSchematic } from "./hooks/useSchematic";
import { fetchDictionary, generateFromImage } from "./lib/api";
import { generateAsc } from "./lib/ascGenerator";
import type { Dictionary } from "./types/schematic";

function App() {
  const [dictionary, setDictionary] = useState<Dictionary | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [generating, setGenerating] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<"select" | "wire">("select");
  const [status, setStatus] = useState("Ready");
  const [validation, setValidation] = useState<{
    valid: boolean;
    errors: string[];
  } | null>(null);

  const {
    schematic,
    loadFromGenerateResponse,
    moveComponent,
    updateComponent,
    addComponent,
    deleteComponent,
    addWire,
    deleteWire,
    addFlag,
    deleteFlag,
    undo,
    redo,
    canUndo,
    canRedo,
  } = useSchematic();

  const ascText = generateAsc(schematic);

  // Load dictionary on mount
  useEffect(() => {
    fetchDictionary()
      .then(setDictionary)
      .catch((err) => setStatus(`Error loading dictionary: ${err.message}`));
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === "z") {
        e.preventDefault();
        undo();
      } else if (e.ctrlKey && e.key === "y") {
        e.preventDefault();
        redo();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [undo, redo]);

  const handleUpload = useCallback((file: File) => {
    setImageFile(file);
    setImageUrl(URL.createObjectURL(file));
    setStatus("Image loaded. Click Generate to analyze.");
  }, []);

  const handleGenerate = useCallback(async () => {
    if (!imageFile) return;
    setGenerating(true);
    setStatus("Analyzing image with vision model...");
    try {
      const resp = await generateFromImage(imageFile);
      loadFromGenerateResponse(resp);
      setValidation(resp.validation);
      setStatus(
        resp.validation.valid
          ? "Generation complete. Review and adjust in the editor."
          : `Generated with ${resp.validation.errors.length} validation error(s).`
      );
    } catch (err: any) {
      setStatus(`Generation failed: ${err.message}`);
    } finally {
      setGenerating(false);
    }
  }, [imageFile, loadFromGenerateResponse]);

  const handleExport = useCallback(() => {
    const blob = new Blob([ascText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "schematic.asc";
    a.click();
    URL.revokeObjectURL(url);
    setStatus("Exported schematic.asc");
  }, [ascText]);

  const handleAddComponent = useCallback(
    (type: string) => {
      const name = `${type.charAt(0).toUpperCase()}${schematic.components.filter((c) => c.type === type).length + 1}`;
      addComponent(type, name, "1k", { x: 400, y: 300 });
    },
    [addComponent, schematic.components]
  );

  const handleAddFlag = useCallback(() => {
    const name = prompt("Flag name (use '0' for ground):");
    if (name) addFlag(name, { x: 400, y: 300 });
  }, [addFlag]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <Toolbar
        onUpload={handleUpload}
        onGenerate={handleGenerate}
        onExport={handleExport}
        onUndo={undo}
        onRedo={redo}
        canUndo={canUndo}
        canRedo={canRedo}
        generating={generating}
        imageLoaded={!!imageFile}
      />

      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        <ComponentPalette
          dictionary={dictionary}
          onAddComponent={handleAddComponent}
          mode={mode}
          onModeChange={setMode}
          onAddFlag={handleAddFlag}
        />

        <ImagePanel imageUrl={imageUrl} />

        <Editor
          schematic={schematic}
          dictionary={dictionary}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onMoveComponent={moveComponent}
          onAddWire={addWire}
          mode={mode}
        />

        <div
          style={{
            width: 280,
            display: "flex",
            flexDirection: "column",
            borderLeft: "1px solid #ccc",
          }}
        >
          <div
            style={{
              borderBottom: "1px solid #ccc",
              maxHeight: "50%",
              overflow: "auto",
            }}
          >
            <PropertyPanel
              schematic={schematic}
              selectedId={selectedId}
              onUpdateComponent={updateComponent}
              onDeleteComponent={deleteComponent}
              onDeleteWire={deleteWire}
              onDeleteFlag={deleteFlag}
            />
          </div>
          <AscPreview ascText={ascText} validation={validation} />
        </div>
      </div>

      <footer
        style={{
          padding: "4px 8px",
          borderTop: "1px solid #ccc",
          fontSize: 12,
          background: "#f5f5f5",
        }}
      >
        {status}
      </footer>
    </div>
  );
}

export default App;
```

- [ ] **Step 2: Verify frontend builds**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: wire up all components in App.tsx - full UI integration"
```

---

### Task 16: End-to-End Integration Test

**Files:**
- No new files — this tests the full pipeline manually.

- [ ] **Step 1: Pull the vision model**

Run:
```bash
ollama pull qwen3-vl:8b
```
Expected: Model downloads successfully. May take several minutes depending on connection.

- [ ] **Step 2: Start the backend**

Run:
```bash
cd backend && uvicorn main:app --reload --port 8000
```
Expected: Server starts at http://localhost:8000.

- [ ] **Step 3: Start the frontend**

In a separate terminal:
```bash
cd frontend && npm run dev
```
Expected: Vite server starts at http://localhost:5173.

- [ ] **Step 4: Test the dictionary endpoint**

Run:
```bash
curl http://localhost:8000/api/dictionary | python -m json.tool | head -20
```
Expected: JSON output with component definitions.

- [ ] **Step 5: Test end-to-end generation**

Open http://localhost:5173 in a browser:
1. Click "Upload Image" and select `LTSpice_Amplifier_Noise_fig01.png`
2. Click "Generate"
3. Wait for the vision model to process (~30-60 seconds)
4. Verify: the visual editor shows components, the .asc preview shows valid content
5. Try dragging a component — verify it snaps to grid
6. Try drawing a wire — click Wire mode, click two points
7. Click "Export .asc" — verify the file downloads and opens in LTspice

- [ ] **Step 6: Commit any fixes**

If any issues were found during testing, fix them and commit:
```bash
git add -A && git commit -m "fix: integration test fixes"
```

---

### Task 17: Run All Tests

**Files:** None — validation task.

- [ ] **Step 1: Run all backend tests**

Run:
```bash
cd backend && python -m pytest tests/ -v
```
Expected: All tests pass.

- [ ] **Step 2: Run frontend build check**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds.

- [ ] **Step 3: Final commit**

```bash
git add -A && git commit -m "chore: all tests passing, build verified"
```
