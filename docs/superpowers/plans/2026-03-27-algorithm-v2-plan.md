# Algorithm V2 + UI Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single monolithic LLM call with a multi-step wizard, add `.asy`-based dictionary, fix editor rendering, and overhaul the UI layout with dark/light theme support.

**Architecture:** Parse LTspice `.asy` symbol files for pixel-perfect component geometry. Split vision pipeline into 4 focused LLM calls (identify, directives, layout, wires) with user confirmation between each. Remove redundant refinement LLM. Add CSS custom properties for theming, SVG rotation transforms, and a toggleable wizard modal.

**Tech Stack:** Python 3.10+, FastAPI, Ollama HTTP API, React 18, Vite, TypeScript, SVG, CSS Custom Properties

---

## File Map

```
New files:
  backend/services/asy_parser.py         -- .asy file parser
  backend/services/layout.py             -- spatial description -> grid coordinates
  backend/services/wire_router.py        -- pin connections -> WIRE coordinates
  backend/api/wizard_routes.py           -- wizard step API endpoints
  backend/prompts/identify_system.txt    -- Step 2 prompt
  backend/prompts/identify_user.txt      -- Step 2 user prompt template
  backend/prompts/directives_system.txt  -- Step 3 prompt
  backend/prompts/directives_user.txt    -- Step 3 user prompt template
  backend/prompts/layout_system.txt      -- Step 4 prompt
  backend/prompts/layout_user.txt        -- Step 4 user prompt template
  backend/prompts/wires_system.txt       -- Step 5 prompt
  backend/prompts/wires_user.txt         -- Step 5 user prompt template
  backend/tests/test_asy_parser.py
  backend/tests/test_layout.py
  backend/tests/test_wire_router.py
  backend/tests/test_wizard_routes.py
  frontend/src/styles/theme.css          -- CSS custom properties
  frontend/src/hooks/useTheme.ts         -- theme toggle hook
  frontend/src/components/GenerateWizard.tsx  -- modal wizard
  frontend/src/components/ScreenshotPanel.tsx -- bottom-right image panel

Modified files:
  dictionary/components.json             -- rebuilt from .asy data
  backend/main.py                        -- mount wizard routes
  backend/services/vision.py             -- split into step functions
  backend/services/ollama_client.py      -- increase timeout
  backend/api/routes.py                  -- remove /api/generate
  frontend/src/App.tsx                   -- new layout, wizard, theme
  frontend/src/components/Editor.tsx     -- rotation, scale, grid toggle
  frontend/src/components/Toolbar.tsx    -- grid toggle, theme toggle
  frontend/src/components/ComponentPalette.tsx -- collapsible, reference images
  frontend/src/types/schematic.ts        -- updated dictionary types
  frontend/src/lib/api.ts               -- wizard API functions
  frontend/src/index.css                 -- import theme.css

Deleted files:
  backend/services/refinement.py
  backend/prompts/refine_system.txt
  backend/prompts/vision_system.txt
  backend/tests/test_refinement.py
```

---

### Task 1: .asy Parser (TDD)

**Files:**
- Create: `backend/services/asy_parser.py`
- Create: `backend/tests/test_asy_parser.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_asy_parser.py`:
```python
import pytest
from services.asy_parser import parse_asy_file, parse_asy_string, AsySymbol


def test_parse_resistor():
    content = """Version 4
SymbolType CELL
LINE Normal 16 88 16 96
LINE Normal 0 80 16 88
LINE Normal 32 64 0 80
LINE Normal 0 48 32 64
LINE Normal 32 32 0 48
LINE Normal 16 16 16 24
LINE Normal 16 24 32 32
WINDOW 0 36 40 Left 2
WINDOW 3 36 76 Left 2
SYMATTR Value R
SYMATTR Prefix R
SYMATTR Description A resistor
PIN 16 16 NONE 0
PINATTR PinName A
PINATTR SpiceOrder 1
PIN 16 96 NONE 0
PINATTR PinName B
PINATTR SpiceOrder 2
"""
    sym = parse_asy_string(content)
    assert sym.prefix == "R"
    assert sym.description == "A resistor"
    assert len(sym.lines) == 7
    assert sym.lines[0] == (16, 88, 16, 96)
    assert len(sym.pins) == 2
    assert sym.pins[0].name == "A"
    assert sym.pins[0].x == 16
    assert sym.pins[0].y == 16
    assert sym.pins[0].spice_order == 1
    assert sym.pins[1].name == "B"
    assert sym.pins[1].spice_order == 2
    assert len(sym.circles) == 0
    assert len(sym.arcs) == 0
    assert sym.bounds == (0, 16, 32, 96)


def test_parse_voltage_source_with_circle():
    content = """Version 4
SymbolType CELL
LINE Normal -8 36 8 36
LINE Normal -8 76 8 76
LINE Normal 0 28 0 44
LINE Normal 0 96 0 88
LINE Normal 0 16 0 24
CIRCLE Normal -32 24 32 88
WINDOW 0 24 16 Left 2
WINDOW 3 24 96 Left 2
SYMATTR Value V
SYMATTR Prefix V
SYMATTR Description Voltage Source
PIN 0 16 NONE 0
PINATTR PinName +
PINATTR SpiceOrder 1
PIN 0 96 NONE 0
PINATTR PinName -
PINATTR SpiceOrder 2
"""
    sym = parse_asy_string(content)
    assert sym.prefix == "V"
    assert len(sym.lines) == 5
    assert len(sym.circles) == 1
    assert sym.circles[0] == (-32, 24, 32, 88)
    assert len(sym.pins) == 2
    assert sym.pins[0].name == "+"
    assert sym.pins[1].name == "-"


def test_parse_opamp2_with_subdirectory():
    content = """Version 4
SymbolType CELL
LINE Normal -32 32 32 64
LINE Normal -32 96 32 64
LINE Normal -32 32 -32 96
LINE Normal -28 48 -20 48
LINE Normal -28 80 -20 80
LINE Normal -24 84 -24 76
LINE Normal 0 32 0 48
LINE Normal 0 96 0 80
LINE Normal 4 44 12 44
LINE Normal 8 40 8 48
LINE Normal 4 84 12 84
WINDOW 0 16 32 Left 2
WINDOW 3 16 96 Left 2
SYMATTR Value opamp2
SYMATTR Prefix X
SYMATTR Description Basic Operational Amplifier
PIN -32 80 NONE 0
PINATTR PinName In+
PINATTR SpiceOrder 1
PIN -32 48 NONE 0
PINATTR PinName In-
PINATTR SpiceOrder 2
PIN 0 32 NONE 0
PINATTR PinName V+
PINATTR SpiceOrder 3
PIN 0 96 NONE 0
PINATTR PinName V-
PINATTR SpiceOrder 4
PIN 32 64 NONE 0
PINATTR PinName OUT
PINATTR SpiceOrder 5
"""
    sym = parse_asy_string(content)
    assert sym.prefix == "X"
    assert len(sym.pins) == 5
    assert sym.pins[4].name == "OUT"
    assert sym.pins[4].x == 32
    assert sym.pins[4].y == 64


def test_to_svg_path():
    content = """Version 4
SymbolType CELL
LINE Normal 0 0 32 0
LINE Normal 32 0 32 32
SYMATTR Value test
SYMATTR Prefix T
PIN 0 0 NONE 0
PINATTR PinName A
PINATTR SpiceOrder 1
"""
    sym = parse_asy_string(content)
    svg = sym.to_svg_path()
    assert "M0,0 L32,0" in svg
    assert "M32,0 L32,32" in svg


def test_to_svg_path_with_circle():
    content = """Version 4
SymbolType CELL
CIRCLE Normal 0 0 64 64
SYMATTR Value test
SYMATTR Prefix T
PIN 32 0 NONE 0
PINATTR PinName A
PINATTR SpiceOrder 1
"""
    sym = parse_asy_string(content)
    svg = sym.to_svg_path()
    # Circle bounding box (0,0)-(64,64) -> center (32,32) rx=32 ry=32
    assert "32,32" in svg


def test_to_dict():
    content = """Version 4
SymbolType CELL
LINE Normal 16 16 16 96
WINDOW 0 36 40 Left 2
SYMATTR Value R
SYMATTR Prefix R
SYMATTR Description A resistor
PIN 16 16 NONE 0
PINATTR PinName A
PINATTR SpiceOrder 1
PIN 16 96 NONE 0
PINATTR PinName B
PINATTR SpiceOrder 2
"""
    sym = parse_asy_string(content)
    d = sym.to_dict()
    assert d["prefix"] == "R"
    assert d["description"] == "A resistor"
    assert len(d["pins"]) == 2
    assert d["pins"][0]["name"] == "A"
    assert d["geometry"]["lines"][0] == {"x1": 16, "y1": 16, "x2": 16, "y2": 96}
    assert "bounds" in d["geometry"]
    assert "svgPath" in d["symbol"]
    assert d["symbol"]["width"] > 0
    assert d["symbol"]["height"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && python -m pytest tests/test_asy_parser.py -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the parser**

Create `backend/services/asy_parser.py`:
```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Pin:
    name: str
    x: int
    y: int
    spice_order: int


@dataclass
class Window:
    index: int
    x: int
    y: int
    justification: str
    font_size: int


@dataclass
class AsySymbol:
    lines: list[tuple[int, int, int, int]] = field(default_factory=list)
    circles: list[tuple[int, int, int, int]] = field(default_factory=list)
    arcs: list[tuple[int, int, int, int, int, int, int, int]] = field(default_factory=list)
    rectangles: list[tuple[int, int, int, int]] = field(default_factory=list)
    pins: list[Pin] = field(default_factory=list)
    windows: list[Window] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)

    @property
    def prefix(self) -> str:
        return self.attrs.get("Prefix", "")

    @property
    def description(self) -> str:
        return self.attrs.get("Description", "")

    @property
    def value(self) -> str:
        return self.attrs.get("Value", "")

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """Returns (minX, minY, maxX, maxY) from all geometry and pins."""
        xs: list[int] = []
        ys: list[int] = []
        for x1, y1, x2, y2 in self.lines:
            xs.extend([x1, x2])
            ys.extend([y1, y2])
        for x1, y1, x2, y2 in self.circles:
            xs.extend([x1, x2])
            ys.extend([y1, y2])
        for coords in self.arcs:
            xs.extend([coords[0], coords[2]])
            ys.extend([coords[1], coords[3]])
        for x1, y1, x2, y2 in self.rectangles:
            xs.extend([x1, x2])
            ys.extend([y1, y2])
        for pin in self.pins:
            xs.append(pin.x)
            ys.append(pin.y)
        if not xs:
            return (0, 0, 0, 0)
        return (min(xs), min(ys), max(xs), max(ys))

    def to_svg_path(self) -> str:
        """Convert geometry to SVG path string, normalized to (0,0) origin."""
        min_x, min_y, _, _ = self.bounds
        parts: list[str] = []

        for x1, y1, x2, y2 in self.lines:
            parts.append(f"M{x1 - min_x},{y1 - min_y} L{x2 - min_x},{y2 - min_y}")

        for x1, y1, x2, y2 in self.circles:
            cx = (x1 + x2) / 2 - min_x
            cy = (y1 + y2) / 2 - min_y
            rx = abs(x2 - x1) / 2
            ry = abs(y2 - y1) / 2
            parts.append(
                f"M{cx - rx},{cy} "
                f"A{rx},{ry} 0 1,0 {cx + rx},{cy} "
                f"A{rx},{ry} 0 1,0 {cx - rx},{cy}"
            )

        for x1, y1, x2, y2 in self.rectangles:
            nx1, ny1 = x1 - min_x, y1 - min_y
            nx2, ny2 = x2 - min_x, y2 - min_y
            parts.append(f"M{nx1},{ny1} L{nx2},{ny1} L{nx2},{ny2} L{nx1},{ny2} Z")

        return " ".join(parts)

    def to_dict(self) -> dict:
        """Convert to dictionary format for components.json."""
        min_x, min_y, max_x, max_y = self.bounds
        width = max_x - min_x
        height = max_y - min_y

        geometry = {
            "lines": [
                {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
                for x1, y1, x2, y2 in self.lines
            ],
            "circles": [
                {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
                for x1, y1, x2, y2 in self.circles
            ],
            "arcs": [
                {"x1": c[0], "y1": c[1], "x2": c[2], "y2": c[3],
                 "x3": c[4], "y3": c[5], "x4": c[6], "y4": c[7]}
                for c in self.arcs
            ],
            "bounds": {"minX": min_x, "minY": min_y, "maxX": max_x, "maxY": max_y},
        }

        pins = [
            {"name": p.name, "x": p.x, "y": p.y, "spiceOrder": p.spice_order}
            for p in self.pins
        ]

        windows = [
            {"index": w.index, "x": w.x, "y": w.y,
             "justification": w.justification, "fontSize": w.font_size}
            for w in self.windows
        ]

        return {
            "prefix": self.prefix,
            "description": self.description,
            "geometry": geometry,
            "pins": pins,
            "windows": windows,
            "symbol": {
                "width": width,
                "height": height,
                "svgPath": self.to_svg_path(),
            },
        }


def parse_asy_string(content: str) -> AsySymbol:
    """Parse .asy file content string into an AsySymbol."""
    sym = AsySymbol()
    current_pin_x = 0
    current_pin_y = 0
    lines = content.strip().split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("LINE Normal "):
            parts = line.split()
            sym.lines.append((int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])))

        elif line.startswith("CIRCLE Normal "):
            parts = line.split()
            sym.circles.append((int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])))

        elif line.startswith("ARC Normal "):
            parts = line.split()
            sym.arcs.append(tuple(int(parts[j]) for j in range(2, 10)))

        elif line.startswith("RECTANGLE Normal "):
            parts = line.split()
            sym.rectangles.append((int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])))

        elif line.startswith("WINDOW "):
            parts = line.split()
            sym.windows.append(Window(
                index=int(parts[1]),
                x=int(parts[2]),
                y=int(parts[3]),
                justification=parts[4],
                font_size=int(parts[5]),
            ))

        elif line.startswith("SYMATTR "):
            parts = line.split(maxsplit=2)
            if len(parts) == 3:
                sym.attrs[parts[1]] = parts[2]

        elif line.startswith("PIN "):
            parts = line.split()
            current_pin_x = int(parts[1])
            current_pin_y = int(parts[2])

        elif line.startswith("PINATTR PinName "):
            pin_name = line.split(maxsplit=2)[2]
            # Look ahead for SpiceOrder
            spice_order = 0
            if i + 1 < len(lines) and lines[i + 1].strip().startswith("PINATTR SpiceOrder"):
                spice_order = int(lines[i + 1].strip().split()[-1])
                i += 1
            sym.pins.append(Pin(pin_name, current_pin_x, current_pin_y, spice_order))

        i += 1
    return sym


def parse_asy_file(path: Path) -> AsySymbol:
    """Parse a .asy file from disk."""
    return parse_asy_string(path.read_text(encoding="utf-8"))


# Mapping of dictionary IDs to .asy file paths (relative to sym dir)
CORE_SYMBOLS = {
    "res": "res.asy",
    "cap": "cap.asy",
    "ind": "ind.asy",
    "voltage": "voltage.asy",
    "current": "current.asy",
    "opamp2": "OpAmps/opamp2.asy",
    "opamp": "OpAmps/opamp.asy",
    "npn": "npn.asy",
    "pnp": "pnp.asy",
    "nmos": "nmos.asy",
    "pmos": "pmos.asy",
    "diode": "diode.asy",
    "zener": "zener.asy",
}

# Category mapping
CATEGORIES = {
    "res": "passive", "cap": "passive", "ind": "passive",
    "voltage": "sources", "current": "sources",
    "opamp2": "amplifiers", "opamp": "amplifiers",
    "npn": "semiconductors", "pnp": "semiconductors",
    "nmos": "semiconductors", "pmos": "semiconductors",
    "diode": "semiconductors", "zener": "semiconductors",
}

# Display names
DISPLAY_NAMES = {
    "res": "Resistor", "cap": "Capacitor", "ind": "Inductor",
    "voltage": "Voltage Source", "current": "Current Source",
    "opamp2": "Op-Amp (2-input)", "opamp": "Op-Amp (single supply)",
    "npn": "NPN Transistor", "pnp": "PNP Transistor",
    "nmos": "NMOS Transistor", "pmos": "PMOS Transistor",
    "diode": "Diode", "zener": "Zener Diode",
}


def build_dictionary_from_asy(ltspice_sym_dir: Path) -> dict:
    """Parse all core .asy files and build the components dictionary."""
    components = {}
    for comp_id, asy_path in CORE_SYMBOLS.items():
        full_path = ltspice_sym_dir / asy_path
        if not full_path.exists():
            continue
        sym = parse_asy_file(full_path)
        entry = sym.to_dict()
        entry["id"] = comp_id
        entry["category"] = CATEGORIES[comp_id]
        entry["displayName"] = DISPLAY_NAMES[comp_id]
        entry["asySource"] = asy_path
        entry["rotations"] = ["R0", "R90", "R180", "R270", "M0", "M90"]
        # Keep ascSyntax for .asc generation
        attrs = ["InstName", "Value"]
        if comp_id == "voltage":
            attrs.append("Value2")
        entry["ascSyntax"] = {"symbolName": comp_id, "attributes": attrs}
        components[comp_id] = entry
    return {"components": components}
```

- [ ] **Step 4: Run tests**

Run:
```bash
cd backend && python -m pytest tests/test_asy_parser.py -v
```
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/asy_parser.py backend/tests/test_asy_parser.py
git commit -m "feat: add .asy file parser with TDD tests"
```

---

### Task 2: Rebuild Dictionary from .asy Files

**Files:**
- Create: `backend/scripts/rebuild_dictionary.py`
- Modify: `dictionary/components.json`

- [ ] **Step 1: Create rebuild script**

Create `backend/scripts/rebuild_dictionary.py`:
```python
"""Rebuild dictionary/components.json from LTspice .asy files."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from services.asy_parser import build_dictionary_from_asy

def main():
    ltspice_sym = Path(os.environ.get(
        "LTSPICE_SYM_DIR",
        os.path.expandvars(r"%LOCALAPPDATA%\LTspice\lib\sym")
    ))

    if not ltspice_sym.exists():
        print(f"LTspice sym directory not found: {ltspice_sym}")
        print("Set LTSPICE_SYM_DIR environment variable to override.")
        sys.exit(1)

    print(f"Parsing .asy files from: {ltspice_sym}")
    dictionary = build_dictionary_from_asy(ltspice_sym)

    out_path = Path(__file__).parent.parent.parent / "dictionary" / "components.json"
    out_path.write_text(json.dumps(dictionary, indent=2), encoding="utf-8")
    print(f"Wrote {len(dictionary['components'])} components to {out_path}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the rebuild script**

Run:
```bash
cd backend && python scripts/rebuild_dictionary.py
```
Expected: `Wrote 13 components to .../dictionary/components.json`

- [ ] **Step 3: Verify the new dictionary**

Run:
```bash
python -c "import json; d=json.load(open('../dictionary/components.json')); print(list(d['components'].keys())); print('pins:', len(d['components']['res']['pins']))"
```
Expected: Lists all 13 component IDs, `pins: 2` for resistor.

- [ ] **Step 4: Run existing backend tests to ensure nothing broke**

Run:
```bash
cd backend && python -m pytest tests/ -v
```
Expected: All tests pass (dictionary format change may require test updates — fix any that fail).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/rebuild_dictionary.py dictionary/components.json
git commit -m "feat: rebuild dictionary from LTspice .asy files"
```

---

### Task 3: Delete Refinement Service

**Files:**
- Delete: `backend/services/refinement.py`
- Delete: `backend/prompts/refine_system.txt`
- Delete: `backend/tests/test_refinement.py`
- Modify: `backend/api/routes.py`

- [ ] **Step 1: Remove refinement imports from routes.py**

In `backend/api/routes.py`, remove the import of `refine_to_asc` and the `generate` endpoint that used it. Remove the old `/api/generate` endpoint entirely. Keep `/api/refine` but make it use only the deterministic `generate_asc`:

The `/api/refine` endpoint already uses `generate_asc` deterministically — just verify it doesn't import from `refinement.py`. Read `backend/api/routes.py` and remove only the `from services.refinement import refine_to_asc` line and the `generate` endpoint function.

- [ ] **Step 2: Delete the files**

```bash
rm backend/services/refinement.py backend/prompts/refine_system.txt backend/tests/test_refinement.py
```

- [ ] **Step 3: Remove old vision_system.txt** (will be replaced by step-specific prompts)

```bash
rm backend/prompts/vision_system.txt
```

- [ ] **Step 4: Run tests**

Run:
```bash
cd backend && python -m pytest tests/ -v
```
Expected: All remaining tests pass. `test_refinement.py` is gone. `test_routes.py` should still pass since `/api/refine` doesn't use the refinement service.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove refinement LLM service - use deterministic .asc generation only"
```

---

### Task 4: Theme CSS + Toggle Hook

**Files:**
- Create: `frontend/src/styles/theme.css`
- Create: `frontend/src/hooks/useTheme.ts`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Create theme.css**

Create `frontend/src/styles/theme.css`:
```css
:root,
:root[data-theme="light"] {
  --bg-editor: #e8e8e8;
  --bg-panel: #f5f5f5;
  --bg-input: #ffffff;
  --bg-modal: #ffffff;
  --bg-backdrop: rgba(0, 0, 0, 0.4);
  --color-text: #333333;
  --color-text-muted: #999999;
  --color-component: #0000CC;
  --color-wire: #0000CC;
  --color-selection: #2196F3;
  --color-grid: #cccccc;
  --color-border: #cccccc;
  --color-error: #cc0000;
  --color-success: green;
  --color-button-bg: #ffffff;
  --color-button-active: #dddddd;
  --color-preview-bg: #fafafa;
}

:root[data-theme="dark"] {
  --bg-editor: #1e1e1e;
  --bg-panel: #2d2d2d;
  --bg-input: #3a3a3a;
  --bg-modal: #2d2d2d;
  --bg-backdrop: rgba(0, 0, 0, 0.6);
  --color-text: #e0e0e0;
  --color-text-muted: #888888;
  --color-component: #6699FF;
  --color-wire: #6699FF;
  --color-selection: #42a5f5;
  --color-grid: #333333;
  --color-border: #444444;
  --color-error: #ff6666;
  --color-success: #66cc66;
  --color-button-bg: #3a3a3a;
  --color-button-active: #555555;
  --color-preview-bg: #252525;
}
```

- [ ] **Step 2: Create useTheme hook**

Create `frontend/src/hooks/useTheme.ts`:
```ts
import { useState, useEffect, useCallback } from "react";

function getInitialTheme(): "light" | "dark" {
  const stored = localStorage.getItem("theme");
  if (stored === "light" || stored === "dark") return stored;
  if (window.matchMedia("(prefers-color-scheme: dark)").matches) return "dark";
  return "light";
}

export function useTheme() {
  const [theme, setThemeState] = useState<"light" | "dark">(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setThemeState((t) => (t === "light" ? "dark" : "light"));
  }, []);

  return { theme, toggleTheme };
}
```

- [ ] **Step 3: Import theme.css in index.css**

Add to the top of `frontend/src/index.css`:
```css
@import "./styles/theme.css";
```

- [ ] **Step 4: Verify frontend builds**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/styles/theme.css frontend/src/hooks/useTheme.ts frontend/src/index.css
git commit -m "feat: add dark/light theme CSS variables and toggle hook"
```

---

### Task 5: Editor — Rotation, Scale Indicator, Grid Toggle

**Files:**
- Modify: `frontend/src/components/Editor.tsx`

- [ ] **Step 1: Add rotation transform, scale indicator, grid toggle, and theme colors to Editor**

The Editor component needs these changes:
1. Accept `showGrid` prop
2. Apply rotation transforms to component `<g>` elements
3. Show zoom percentage in bottom-left corner
4. Use CSS variable colors instead of hardcoded values

Update `EditorProps` interface:
```ts
interface EditorProps {
  schematic: Schematic;
  dictionary: Dictionary | null;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onMoveComponent: (id: string, pos: Position) => void;
  onAddWire: (from: Position, to: Position) => void;
  mode: "select" | "wire";
  showGrid: boolean;
}
```

Add rotation transform function inside the component:
```ts
function getRotationTransform(
  rotation: string,
  width: number,
  height: number
): string {
  const cx = width / 2;
  const cy = height / 2;
  switch (rotation) {
    case "R90": return `rotate(90, ${cx}, ${cy})`;
    case "R180": return `rotate(180, ${cx}, ${cy})`;
    case "R270": return `rotate(270, ${cx}, ${cy})`;
    case "M0": return `translate(${width}, 0) scale(-1, 1)`;
    case "M90": return `translate(${width}, 0) scale(-1, 1) rotate(90, ${cx}, ${cy})`;
    default: return "";
  }
}
```

In `renderComponent`, wrap the component shape group with the rotation transform:
```tsx
const rotTransform = dictComp
  ? getRotationTransform(comp.rotation, dictComp.symbol.width, dictComp.symbol.height)
  : "";

return (
  <g key={comp.id} transform={`translate(${comp.position.x}, ${comp.position.y})`} ...>
    {/* Selection highlight - outside rotation */}
    {isSelected && dictComp && ( <rect ... /> )}
    {/* Rotated content */}
    <g transform={rotTransform}>
      {dictComp ? <path ... /> : <rect ... />}
      {dictComp?.pins.map((pin) => ( <circle ... /> ))}
    </g>
    {/* Labels - outside rotation so they stay readable */}
    <text ...>{comp.instanceName}</text>
    <text ...>{comp.value}</text>
  </g>
);
```

Add scale indicator after the main content, as a fixed-position overlay in SVG:
```tsx
{/* Scale indicator - bottom left */}
<text
  x={viewBox.x + 10}
  y={viewBox.y + viewBox.h - 10}
  fontSize={14 * (viewBox.w / 880)}
  fill="var(--color-text-muted)"
  pointerEvents="none"
>
  {Math.round((880 / viewBox.w) * 100)}%
</text>
```

For the grid, conditionally render based on `showGrid` prop:
```tsx
{showGrid && (
  <>
    <defs>
      <pattern id="grid" width={16} height={16} patternUnits="userSpaceOnUse">
        <circle cx={0} cy={0} r={0.5} fill="var(--color-grid)" />
      </pattern>
    </defs>
    <rect x={viewBox.x} y={viewBox.y} width={viewBox.w} height={viewBox.h} fill="url(#grid)" />
  </>
)}
```

Replace all hardcoded colors:
- `stroke="#0000CC"` → `stroke="var(--color-component)"`
- `fill="#0000CC"` → `fill="var(--color-component)"`
- `stroke="#2196F3"` → `stroke="var(--color-selection)"`
- `background: "#e8e8e8"` → `background: "var(--bg-editor)"`

- [ ] **Step 2: Verify frontend builds**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Editor.tsx
git commit -m "feat: add rotation transforms, scale indicator, grid toggle, theme colors to editor"
```

---

### Task 6: Toolbar — Grid Toggle + Theme Toggle

**Files:**
- Modify: `frontend/src/components/Toolbar.tsx`

- [ ] **Step 1: Add grid and theme toggle props and buttons**

Add to `ToolbarProps`:
```ts
  showGrid: boolean;
  onToggleGrid: () => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
```

Add buttons after the Redo button:
```tsx
<div style={{ width: 1, height: 24, background: "var(--color-border)" }} />
<button
  onClick={onToggleGrid}
  style={{ background: showGrid ? "var(--color-button-active)" : "var(--color-button-bg)" }}
>
  Grid
</button>
<button onClick={onToggleTheme}>
  {theme === "light" ? "Dark" : "Light"}
</button>
```

Replace all hardcoded colors in the toolbar with CSS variables:
- `background: "#f5f5f5"` → `background: "var(--bg-panel)"`
- `borderBottom: "1px solid #ccc"` → `borderBottom: "1px solid var(--color-border)"`

- [ ] **Step 2: Verify frontend builds**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Toolbar.tsx
git commit -m "feat: add grid toggle and theme toggle to toolbar"
```

---

### Task 7: Screenshot Panel

**Files:**
- Create: `frontend/src/components/ScreenshotPanel.tsx`

- [ ] **Step 1: Create ScreenshotPanel**

Create `frontend/src/components/ScreenshotPanel.tsx`:
```tsx
import { useState } from "react";

interface ScreenshotPanelProps {
  imageUrl: string | null;
}

export function ScreenshotPanel({ imageUrl }: ScreenshotPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  if (!imageUrl) {
    return (
      <div style={{
        padding: 12,
        color: "var(--color-text-muted)",
        fontSize: 12,
        textAlign: "center",
        borderTop: "1px solid var(--color-border)",
      }}>
        Upload an image to see it here
      </div>
    );
  }

  return (
    <>
      <div style={{
        borderTop: "1px solid var(--color-border)",
        display: "flex",
        flexDirection: "column",
        height: expanded ? "50%" : 150,
        minHeight: 80,
      }}>
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "2px 8px",
          fontSize: 12,
          fontWeight: "bold",
          color: "var(--color-text)",
          borderBottom: "1px solid var(--color-border)",
          background: "var(--bg-panel)",
        }}>
          <span>Screenshot</span>
          <div style={{ display: "flex", gap: 4 }}>
            <button
              onClick={() => setExpanded((e) => !e)}
              style={{ fontSize: 10, padding: "1px 4px" }}
              title={expanded ? "Collapse" : "Expand"}
            >
              {expanded ? "▼" : "▲"}
            </button>
            <button
              onClick={() => setFullscreen(true)}
              style={{ fontSize: 10, padding: "1px 4px" }}
              title="Fullscreen"
            >
              ⛶
            </button>
          </div>
        </div>
        <div style={{ flex: 1, overflow: "auto", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <img
            src={imageUrl}
            alt="LTspice screenshot"
            style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
          />
        </div>
      </div>

      {/* Fullscreen overlay */}
      {fullscreen && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 1000,
            background: "var(--bg-backdrop)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
          }}
          onClick={() => setFullscreen(false)}
        >
          <img
            src={imageUrl}
            alt="LTspice screenshot fullscreen"
            style={{ maxWidth: "95vw", maxHeight: "95vh", objectFit: "contain" }}
            onClick={(e) => e.stopPropagation()}
          />
          <button
            onClick={() => setFullscreen(false)}
            style={{
              position: "absolute",
              top: 16,
              right: 16,
              fontSize: 24,
              background: "var(--bg-panel)",
              color: "var(--color-text)",
              border: "none",
              borderRadius: 4,
              padding: "4px 12px",
              cursor: "pointer",
            }}
          >
            ✕
          </button>
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 2: Verify frontend builds**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ScreenshotPanel.tsx
git commit -m "feat: add ScreenshotPanel with expand/fullscreen"
```

---

### Task 8: Wizard Prompts

**Files:**
- Create: `backend/prompts/identify_system.txt`
- Create: `backend/prompts/directives_system.txt`
- Create: `backend/prompts/layout_system.txt`
- Create: `backend/prompts/wires_system.txt`

- [ ] **Step 1: Create all four prompt files**

Create `backend/prompts/identify_system.txt`:
```
You are analyzing an LTspice circuit schematic screenshot.

LTspice schematics use dark blue components on a light gray background.
Component types you may see:
- Resistor (res): zigzag line, labeled R1/R2/etc, values like "1k", "100", "noiseless"
- Capacitor (cap): two parallel horizontal lines with leads
- Inductor (ind): coil/bumps pattern
- Voltage Source (voltage): circle with + and - signs, labeled V1/V2/etc
- Current Source (current): circle with arrow inside
- Op-Amp 2-input (opamp2): triangle with +/- inputs and V+/V- power pins, labeled U1/U2/etc
- Op-Amp single supply (opamp): triangle with +/- inputs, no power pins
- NPN Transistor (npn): vertical bar with angled collector/emitter lines, arrow on emitter pointing out
- PNP Transistor (pnp): vertical bar with angled collector/emitter lines, arrow on emitter pointing in
- NMOS (nmos): MOSFET symbol with gate, drain, source
- PMOS (pmos): MOSFET symbol with gate, drain, source, bubble on gate
- Diode (diode): triangle with bar
- Zener Diode (zener): triangle with bent bar ends

List ONLY the components. Do NOT describe wires, positions, or connections.
Output ONLY valid JSON.
```

Create `backend/prompts/directives_system.txt`:
```
You are reading text from an LTspice schematic screenshot.

SPICE directives are text lines that start with a dot (.) and appear as text on the schematic, typically near the bottom. Common directives:
- .tran (transient analysis)
- .ac (AC analysis)
- .dc (DC sweep)
- .noise (noise analysis)
- .param (parameter definition)
- .lib, .include (library inclusion)
- .model (model definition)
- .op (operating point)
- .meas (measurement)

Read the text exactly as it appears. Do not modify or interpret it.
Output ONLY valid JSON.
```

Create `backend/prompts/layout_system.txt`:
```
You are describing the spatial layout of components in an LTspice schematic.

Use a coordinate system where (0,0) is the top-left of the schematic.
Describe positions using grid regions: top-left, top-center, top-right, center-left, center, center-right, bottom-left, bottom-center, bottom-right.
Also describe relative positions between components (e.g. "R5 is directly above U1", "V1 is to the right of U1").
Output ONLY valid JSON.
```

Create `backend/prompts/wires_system.txt`:
```
You are tracing wire connections in an LTspice schematic.

Wires in LTspice are straight blue lines (horizontal or vertical) that connect component pins. Wires meet at junctions (small blue dots/squares).

Ground connections appear as small downward-pointing triangles labeled "0".
Net labels are text labels at wire endpoints (like "OUT", "VP", "VN").

Describe connections in terms of component pins, not coordinates.
Output ONLY valid JSON.
```

- [ ] **Step 2: Commit**

```bash
git add backend/prompts/
git commit -m "feat: add step-specific wizard prompts"
```

---

### Task 9: Vision Service Refactor

**Files:**
- Modify: `backend/services/vision.py`
- Modify: `backend/tests/test_vision.py`

- [ ] **Step 1: Refactor vision.py into step-specific functions**

Replace `backend/services/vision.py`:
```python
import json
import re
from pathlib import Path

from services.ollama_client import chat_with_vision

VISION_MODEL = "qwen3-vl:8b"
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _extract_json(text: str) -> dict | list:
    """Extract JSON from model response, handling markdown code fences."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())
    start = text.find("{")
    start_arr = text.find("[")
    if start_arr != -1 and (start == -1 or start_arr < start):
        end = text.rfind("]")
        if end != -1:
            return json.loads(text[start_arr : end + 1])
    if start != -1:
        end = text.rfind("}")
        if end != -1:
            return json.loads(text[start : end + 1])
    raise ValueError(f"Could not extract JSON from response: {text[:200]}")


async def identify_components(image_bytes: bytes) -> list[dict]:
    """Step 2: Identify components in the image. Returns list of {type, instanceName, value, value2?}."""
    system = _load_prompt("identify_system.txt")
    user = (
        "List every component in this schematic. For each, provide:\n"
        "- type (one of: res, cap, ind, voltage, current, opamp2, opamp, npn, pnp, nmos, pmos, diode, zener)\n"
        "- instanceName (the label, e.g. R1, U1, V3)\n"
        "- value (the displayed value, e.g. \"1k\", \"ADA4627\", \"{PSV}\")\n"
        "- value2 (only for voltage sources with a second value like \"AC 0.01\", otherwise omit)\n\n"
        'Output as JSON array:\n[{"type": "res", "instanceName": "R1", "value": "1k"}, ...]'
    )
    response = await chat_with_vision(VISION_MODEL, system, user, image_bytes)
    result = _extract_json(response)
    if isinstance(result, list):
        return result
    return result.get("components", [])


async def read_directives(image_bytes: bytes) -> list[str]:
    """Step 3: Read SPICE directives from the image. Returns list of directive strings."""
    system = _load_prompt("directives_system.txt")
    user = (
        "List every SPICE directive visible in this schematic.\n"
        'Output as a JSON array of strings:\n'
        '[".param RINP=1k PSV=15", ".tran 0.005"]'
    )
    response = await chat_with_vision(VISION_MODEL, system, user, image_bytes)
    result = _extract_json(response)
    if isinstance(result, list):
        return result
    return result.get("directives", [])


async def describe_layout(image_bytes: bytes, components: list[dict]) -> list[dict]:
    """Step 4: Describe spatial layout. Returns list of {instanceName, region, nearby}."""
    system = _load_prompt("layout_system.txt")
    comp_list = ", ".join(f"{c['instanceName']} ({c['type']})" for c in components)
    user = (
        f"These components were identified in the schematic:\n{comp_list}\n\n"
        "For each component, describe:\n"
        "- region: which area of the schematic it occupies (top-left, top-center, top-right, center-left, center, center-right, bottom-left, bottom-center, bottom-right)\n"
        "- nearby: which other components are adjacent and in which direction\n\n"
        'Output as JSON array:\n'
        '[{"instanceName": "U1", "region": "center", "nearby": [{"name": "R5", "direction": "above"}]}, ...]'
    )
    response = await chat_with_vision(VISION_MODEL, system, user, image_bytes)
    result = _extract_json(response)
    if isinstance(result, list):
        return result
    return result.get("layout", [])


async def describe_wires(image_bytes: bytes, components: list[dict], pin_info: dict) -> dict:
    """Step 5: Describe wire connections. Returns {connections, grounds, labels}."""
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
    response = await chat_with_vision(VISION_MODEL, system, user, image_bytes)
    result = _extract_json(response)
    if isinstance(result, dict):
        return result
    return {"connections": [], "grounds": [], "labels": []}
```

- [ ] **Step 2: Update tests**

Replace `backend/tests/test_vision.py`:
```python
import pytest
from services.vision import _extract_json


def test_extract_json_from_code_fence():
    text = '```json\n{"sheet": {"width": 880}}\n```'
    result = _extract_json(text)
    assert result["sheet"]["width"] == 880


def test_extract_json_bare_object():
    text = '{"sheet": {"width": 880}}'
    result = _extract_json(text)
    assert result["sheet"]["width"] == 880


def test_extract_json_bare_array():
    text = '[{"type": "res", "instanceName": "R1"}]'
    result = _extract_json(text)
    assert isinstance(result, list)
    assert result[0]["type"] == "res"


def test_extract_json_array_with_surrounding_text():
    text = 'Here are the components:\n[{"type": "res"}]\nDone.'
    result = _extract_json(text)
    assert isinstance(result, list)
    assert result[0]["type"] == "res"


def test_extract_json_with_surrounding_text():
    text = 'Analysis:\n{"sheet": {"width": 880}}\nDone.'
    result = _extract_json(text)
    assert result["sheet"]["width"] == 880


def test_extract_json_invalid():
    with pytest.raises(ValueError):
        _extract_json("no json here")
```

- [ ] **Step 3: Run tests**

Run:
```bash
cd backend && python -m pytest tests/test_vision.py -v
```
Expected: All 6 tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/services/vision.py backend/tests/test_vision.py
git commit -m "refactor: split vision service into step-specific functions"
```

---

### Task 10: Layout Algorithm (TDD)

**Files:**
- Create: `backend/services/layout.py`
- Create: `backend/tests/test_layout.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_layout.py`:
```python
import pytest
from services.layout import compute_layout

COMPONENT_SIZES = {
    "res": {"width": 32, "height": 80},
    "voltage": {"width": 48, "height": 96},
    "opamp2": {"width": 64, "height": 64},
}


def test_single_component_center():
    layout_desc = [
        {"instanceName": "U1", "region": "center", "nearby": []}
    ]
    result = compute_layout(layout_desc, COMPONENT_SIZES, 880, 680)
    assert result["U1"]["x"] == 440
    assert result["U1"]["y"] == 340


def test_two_components_regions():
    layout_desc = [
        {"instanceName": "R1", "region": "top-left", "nearby": []},
        {"instanceName": "V1", "region": "bottom-right", "nearby": []},
    ]
    result = compute_layout(layout_desc, COMPONENT_SIZES, 880, 680)
    assert result["R1"]["x"] < result["V1"]["x"]
    assert result["R1"]["y"] < result["V1"]["y"]


def test_nearby_above():
    layout_desc = [
        {"instanceName": "U1", "region": "center", "nearby": []},
        {"instanceName": "R1", "region": "center", "nearby": [
            {"name": "U1", "direction": "below"}
        ]},
    ]
    result = compute_layout(layout_desc, COMPONENT_SIZES, 880, 680)
    assert result["R1"]["y"] < result["U1"]["y"]


def test_nearby_right():
    layout_desc = [
        {"instanceName": "U1", "region": "center", "nearby": []},
        {"instanceName": "V1", "region": "center", "nearby": [
            {"name": "U1", "direction": "left"}
        ]},
    ]
    result = compute_layout(layout_desc, COMPONENT_SIZES, 880, 680)
    assert result["V1"]["x"] > result["U1"]["x"]


def test_grid_snap():
    layout_desc = [
        {"instanceName": "R1", "region": "center", "nearby": []}
    ]
    result = compute_layout(layout_desc, COMPONENT_SIZES, 880, 680)
    assert result["R1"]["x"] % 16 == 0
    assert result["R1"]["y"] % 16 == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && python -m pytest tests/test_layout.py -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

Create `backend/services/layout.py`:
```python
REGION_COORDS = {
    "top-left": (144, 112),
    "top-center": (432, 112),
    "top-right": (720, 112),
    "center-left": (144, 336),
    "center": (432, 336),
    "center-right": (720, 336),
    "bottom-left": (144, 544),
    "bottom-center": (432, 544),
    "bottom-right": (720, 544),
}

DIRECTION_OFFSETS = {
    "above": (0, -128),
    "below": (0, 128),
    "left": (-128, 0),
    "right": (128, 0),
    "above-left": (-128, -128),
    "above-right": (128, -128),
    "below-left": (-128, 128),
    "below-right": (128, 128),
}


def _snap(value: int) -> int:
    return round(value / 16) * 16


def compute_layout(
    layout_desc: list[dict],
    component_sizes: dict[str, dict],
    sheet_width: int = 880,
    sheet_height: int = 680,
) -> dict[str, dict]:
    """Convert spatial descriptions to grid coordinates.

    Returns: {instanceName: {"x": int, "y": int}} for each component.
    """
    positions: dict[str, dict] = {}

    # Phase 1: Place by region
    for item in layout_desc:
        name = item["instanceName"]
        region = item.get("region", "center")
        base_x, base_y = REGION_COORDS.get(region, (432, 336))
        positions[name] = {"x": base_x, "y": base_y}

    # Phase 2: Adjust by nearby relationships
    for item in layout_desc:
        name = item["instanceName"]
        for nearby in item.get("nearby", []):
            ref_name = nearby.get("name", "")
            direction = nearby.get("direction", "")

            if ref_name not in positions:
                continue

            # "direction" means where the reference is relative to this component
            # e.g. "below" means the reference is below, so this component is above
            opposite = {
                "above": "below", "below": "above",
                "left": "right", "right": "left",
                "above-left": "below-right", "above-right": "below-left",
                "below-left": "above-right", "below-right": "above-left",
            }
            move_dir = opposite.get(direction, direction)
            dx, dy = DIRECTION_OFFSETS.get(move_dir, (0, 0))

            ref_pos = positions[ref_name]
            positions[name] = {
                "x": ref_pos["x"] + dx,
                "y": ref_pos["y"] + dy,
            }

    # Phase 3: Grid snap
    for name in positions:
        positions[name]["x"] = _snap(positions[name]["x"])
        positions[name]["y"] = _snap(positions[name]["y"])

    # Phase 4: Clamp to sheet bounds
    for name in positions:
        positions[name]["x"] = max(32, min(sheet_width - 32, positions[name]["x"]))
        positions[name]["y"] = max(32, min(sheet_height - 32, positions[name]["y"]))

    return positions
```

- [ ] **Step 4: Run tests**

Run:
```bash
cd backend && python -m pytest tests/test_layout.py -v
```
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/layout.py backend/tests/test_layout.py
git commit -m "feat: add layout algorithm - spatial descriptions to grid coordinates"
```

---

### Task 11: Wire Router (TDD)

**Files:**
- Create: `backend/services/wire_router.py`
- Create: `backend/tests/test_wire_router.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_wire_router.py`:
```python
import pytest
from services.wire_router import compute_wires, WireResult


def test_simple_connection():
    components = {
        "R1": {"x": 100, "y": 100, "type": "res"},
        "R2": {"x": 300, "y": 100, "type": "res"},
    }
    pin_defs = {
        "res": [
            {"name": "A", "x": 16, "y": 16, "spiceOrder": 1},
            {"name": "B", "x": 16, "y": 96, "spiceOrder": 2},
        ],
    }
    connections_data = {
        "connections": [
            {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "A"}}
        ],
        "grounds": [],
        "labels": [],
    }
    result = compute_wires(components, pin_defs, connections_data)
    assert len(result.wires) >= 1
    # Wire should start at R1 pin B absolute position
    assert result.wires[0][0] == 116  # R1.x + pin.x
    assert result.wires[0][1] == 196  # R1.y + pin.y


def test_ground_connection():
    components = {
        "V1": {"x": 100, "y": 100, "type": "voltage"},
    }
    pin_defs = {
        "voltage": [
            {"name": "+", "x": 0, "y": 16, "spiceOrder": 1},
            {"name": "-", "x": 0, "y": 96, "spiceOrder": 2},
        ],
    }
    connections_data = {
        "connections": [],
        "grounds": [{"component": "V1", "pin": "-"}],
        "labels": [],
    }
    result = compute_wires(components, pin_defs, connections_data)
    assert len(result.flags) >= 1
    assert result.flags[0]["name"] == "0"


def test_net_label():
    components = {
        "U1": {"x": 200, "y": 200, "type": "opamp2"},
    }
    pin_defs = {
        "opamp2": [
            {"name": "In+", "x": -32, "y": 80, "spiceOrder": 1},
            {"name": "In-", "x": -32, "y": 48, "spiceOrder": 2},
            {"name": "V+", "x": 0, "y": 32, "spiceOrder": 3},
            {"name": "V-", "x": 0, "y": 96, "spiceOrder": 4},
            {"name": "OUT", "x": 32, "y": 64, "spiceOrder": 5},
        ],
    }
    connections_data = {
        "connections": [],
        "grounds": [],
        "labels": [{"component": "U1", "pin": "OUT", "label": "OUT"}],
    }
    result = compute_wires(components, pin_defs, connections_data)
    assert len(result.flags) >= 1
    assert result.flags[0]["name"] == "OUT"


def test_l_route_wires():
    """Two pins not aligned should produce 2 wire segments (L-route)."""
    components = {
        "R1": {"x": 100, "y": 100, "type": "res"},
        "R2": {"x": 300, "y": 300, "type": "res"},
    }
    pin_defs = {
        "res": [
            {"name": "A", "x": 16, "y": 16, "spiceOrder": 1},
            {"name": "B", "x": 16, "y": 96, "spiceOrder": 2},
        ],
    }
    connections_data = {
        "connections": [
            {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "A"}}
        ],
        "grounds": [],
        "labels": [],
    }
    result = compute_wires(components, pin_defs, connections_data)
    # Non-aligned pins need 2 wire segments
    assert len(result.wires) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && python -m pytest tests/test_wire_router.py -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

Create `backend/services/wire_router.py`:
```python
from dataclasses import dataclass, field


@dataclass
class WireResult:
    wires: list[tuple[int, int, int, int]] = field(default_factory=list)
    flags: list[dict] = field(default_factory=list)


def _find_pin(pin_defs: dict, comp_type: str, pin_name: str) -> dict | None:
    """Find a pin definition by name, case-insensitive."""
    for pin in pin_defs.get(comp_type, []):
        if pin["name"].lower() == pin_name.lower():
            return pin
    return None


def _abs_pin_pos(comp: dict, pin: dict) -> tuple[int, int]:
    """Get absolute pin position: component position + pin offset."""
    return (comp["x"] + pin["x"], comp["y"] + pin["y"])


def compute_wires(
    components: dict[str, dict],
    pin_defs: dict[str, list[dict]],
    connections_data: dict,
) -> WireResult:
    """Convert pin-to-pin connections into wire coordinates and flags.

    components: {instanceName: {"x": int, "y": int, "type": str}}
    pin_defs: {compType: [{"name": str, "x": int, "y": int, "spiceOrder": int}]}
    connections_data: {"connections": [...], "grounds": [...], "labels": [...]}
    """
    result = WireResult()

    # Process connections
    for conn in connections_data.get("connections", []):
        from_comp_name = conn["from"]["component"]
        from_pin_name = conn["from"]["pin"]
        to_comp_name = conn["to"]["component"]
        to_pin_name = conn["to"]["pin"]

        from_comp = components.get(from_comp_name)
        to_comp = components.get(to_comp_name)
        if not from_comp or not to_comp:
            continue

        from_pin = _find_pin(pin_defs, from_comp["type"], from_pin_name)
        to_pin = _find_pin(pin_defs, to_comp["type"], to_pin_name)
        if not from_pin or not to_pin:
            continue

        fx, fy = _abs_pin_pos(from_comp, from_pin)
        tx, ty = _abs_pin_pos(to_comp, to_pin)

        if fx == tx or fy == ty:
            # Aligned: single wire
            result.wires.append((fx, fy, tx, ty))
        else:
            # L-route: horizontal then vertical
            result.wires.append((fx, fy, tx, fy))
            result.wires.append((tx, fy, tx, ty))

    # Process ground connections
    for gnd in connections_data.get("grounds", []):
        comp = components.get(gnd["component"])
        if not comp:
            continue
        pin = _find_pin(pin_defs, comp["type"], gnd["pin"])
        if not pin:
            continue
        px, py = _abs_pin_pos(comp, pin)
        result.flags.append({"name": "0", "x": px, "y": py})

    # Process net labels
    for label in connections_data.get("labels", []):
        comp = components.get(label["component"])
        if not comp:
            continue
        pin = _find_pin(pin_defs, comp["type"], label["pin"])
        if not pin:
            continue
        px, py = _abs_pin_pos(comp, pin)
        result.flags.append({"name": label["label"], "x": px, "y": py})

    return result
```

- [ ] **Step 4: Run tests**

Run:
```bash
cd backend && python -m pytest tests/test_wire_router.py -v
```
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/wire_router.py backend/tests/test_wire_router.py
git commit -m "feat: add wire router - pin connections to WIRE coordinates"
```

---

### Task 12: Wizard API Routes

**Files:**
- Create: `backend/api/wizard_routes.py`
- Create: `backend/tests/test_wizard_routes.py`
- Modify: `backend/main.py`
- Modify: `backend/services/ollama_client.py`

- [ ] **Step 1: Increase Ollama timeout**

In `backend/services/ollama_client.py`, change `timeout=300.0` to `timeout=600.0` on both lines (27 and 47).

- [ ] **Step 2: Create wizard routes**

Create `backend/api/wizard_routes.py`:
```python
import json
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from services.vision import identify_components, read_directives, describe_layout, describe_wires
from services.layout import compute_layout
from services.wire_router import compute_wires

router = APIRouter(prefix="/api/wizard")

DICTIONARY_DIR = Path(__file__).parent.parent.parent / "dictionary"


def _load_dictionary() -> dict:
    return json.loads(
        (DICTIONARY_DIR / "components.json").read_text(encoding="utf-8")
    )


@router.post("/identify")
async def wizard_identify(file: UploadFile = File(...)):
    """Step 2: Identify components in the image."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    image_bytes = await file.read()
    components = await identify_components(image_bytes)
    return {"components": components}


@router.post("/directives")
async def wizard_directives(file: UploadFile = File(...)):
    """Step 3: Read SPICE directives from the image."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    image_bytes = await file.read()
    directives = await read_directives(image_bytes)
    return {"directives": directives}


class LayoutRequest(BaseModel):
    components: list[dict]


@router.post("/layout")
async def wizard_layout(file: UploadFile = File(...), components_json: str = ""):
    """Step 4: Describe layout and compute coordinates."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    image_bytes = await file.read()
    components = json.loads(components_json) if components_json else []

    # Get spatial descriptions from LLM
    layout_desc = await describe_layout(image_bytes, components)

    # Get component sizes from dictionary
    dictionary = _load_dictionary()
    comp_sizes = {}
    for comp_id, comp_data in dictionary["components"].items():
        comp_sizes[comp_id] = {
            "width": comp_data["symbol"]["width"],
            "height": comp_data["symbol"]["height"],
        }

    # Compute grid positions
    positions = compute_layout(layout_desc, comp_sizes)

    return {"layout": layout_desc, "positions": positions}


@router.post("/wires")
async def wizard_wires(file: UploadFile = File(...), components_json: str = "", positions_json: str = ""):
    """Step 5: Trace wire connections."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    image_bytes = await file.read()
    components = json.loads(components_json) if components_json else []
    positions = json.loads(positions_json) if positions_json else {}

    # Get pin definitions from dictionary
    dictionary = _load_dictionary()
    pin_defs = {}
    for comp_id, comp_data in dictionary["components"].items():
        pin_defs[comp_id] = comp_data.get("pins", [])

    # Get wire descriptions from LLM
    wire_desc = await describe_wires(image_bytes, components, pin_defs)

    # Build component map with positions and types
    comp_map = {}
    for comp in components:
        name = comp["instanceName"]
        if name in positions:
            comp_map[name] = {
                "x": positions[name]["x"],
                "y": positions[name]["y"],
                "type": comp["type"],
            }

    # Compute wire coordinates
    wire_result = compute_wires(comp_map, pin_defs, wire_desc)

    return {
        "wire_descriptions": wire_desc,
        "wires": [{"x1": w[0], "y1": w[1], "x2": w[2], "y2": w[3]} for w in wire_result.wires],
        "flags": wire_result.flags,
    }
```

- [ ] **Step 3: Mount wizard routes in main.py**

Add to `backend/main.py` after the existing router import:
```python
from api.wizard_routes import router as wizard_router
```

And after `app.include_router(router)`:
```python
app.include_router(wizard_router)
```

- [ ] **Step 4: Write basic route tests**

Create `backend/tests/test_wizard_routes.py`:
```python
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
```

- [ ] **Step 5: Run tests**

Run:
```bash
cd backend && python -m pytest tests/test_wizard_routes.py -v
```
Expected: 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/api/wizard_routes.py backend/tests/test_wizard_routes.py backend/main.py backend/services/ollama_client.py
git commit -m "feat: add wizard API routes for step-by-step generation"
```

---

### Task 13: Frontend API + Types Update

**Files:**
- Modify: `frontend/src/types/schematic.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add wizard types and API functions**

Add to `frontend/src/types/schematic.ts`:
```ts
export interface WizardComponent {
  type: string;
  instanceName: string;
  value: string;
  value2?: string;
  confirmed?: boolean;
}

export interface WizardLayoutItem {
  instanceName: string;
  region: string;
  nearby: { name: string; direction: string }[];
}

export interface WizardWireResult {
  wires: { x1: number; y1: number; x2: number; y2: number }[];
  flags: { name: string; x: number; y: number }[];
}
```

Update `DictionaryComponent` to include the new fields:
```ts
export interface DictionaryComponent {
  id: string;
  category: string;
  displayName: string;
  asySource?: string;
  prefix?: string;
  description?: string;
  geometry?: {
    lines: { x1: number; y1: number; x2: number; y2: number }[];
    circles: { x1: number; y1: number; x2: number; y2: number }[];
    arcs: any[];
    bounds: { minX: number; minY: number; maxX: number; maxY: number };
  };
  pins: { name: string; x?: number; y?: number; position?: [number, number]; direction?: string; spiceOrder?: number }[];
  windows?: any[];
  symbol: {
    width: number;
    height: number;
    svgPath: string;
  };
  ascSyntax: {
    symbolName: string;
    attributes: string[];
  };
  rotations: string[];
}
```

Add wizard API functions to `frontend/src/lib/api.ts`:
```ts
import type { WizardComponent, WizardWireResult } from "../types/schematic";

export async function wizardIdentify(file: File): Promise<{ components: WizardComponent[] }> {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await fetch(`${BASE_URL}/wizard/identify`, { method: "POST", body: formData });
  if (!resp.ok) throw new Error(`Identify failed: ${resp.status}`);
  return resp.json();
}

export async function wizardDirectives(file: File): Promise<{ directives: string[] }> {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await fetch(`${BASE_URL}/wizard/directives`, { method: "POST", body: formData });
  if (!resp.ok) throw new Error(`Directives failed: ${resp.status}`);
  return resp.json();
}

export async function wizardLayout(
  file: File,
  components: WizardComponent[]
): Promise<{ positions: Record<string, { x: number; y: number }> }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("components_json", JSON.stringify(components));
  const resp = await fetch(`${BASE_URL}/wizard/layout`, { method: "POST", body: formData });
  if (!resp.ok) throw new Error(`Layout failed: ${resp.status}`);
  return resp.json();
}

export async function wizardWires(
  file: File,
  components: WizardComponent[],
  positions: Record<string, { x: number; y: number }>
): Promise<WizardWireResult> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("components_json", JSON.stringify(components));
  formData.append("positions_json", JSON.stringify(positions));
  const resp = await fetch(`${BASE_URL}/wizard/wires`, { method: "POST", body: formData });
  if (!resp.ok) throw new Error(`Wires failed: ${resp.status}`);
  return resp.json();
}
```

- [ ] **Step 2: Verify frontend builds**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/schematic.ts frontend/src/lib/api.ts
git commit -m "feat: add wizard types and API client functions"
```

---

### Task 14: Generate Wizard Modal

**Files:**
- Create: `frontend/src/components/GenerateWizard.tsx`

- [ ] **Step 1: Create the wizard modal component**

Create `frontend/src/components/GenerateWizard.tsx`. This is a large component — it manages 5 wizard steps in a toggleable modal. The full implementation should include:

- Modal overlay with backdrop
- Step indicator (1-5)
- Step 1: Canvas size (auto-detected, editable inputs)
- Step 2: Component identification (table with confirm/change/delete per row, add missing button)
- Step 3: Directives (editable text fields, add/delete)
- Step 4: Layout placement (calls API, shows status)
- Step 5: Wire connections (calls API, shows status)
- Completion summary
- Hide/Show toggle (minimizes to floating pill)
- Close button

The component receives: `imageFile`, `dictionary`, `schematic actions` (addComponent, addWire, addFlag, etc.), and `onClose` callback.

Each step calls the corresponding wizard API endpoint, displays results for user confirmation, and on "Next" applies confirmed data to the schematic via the passed-in action callbacks.

```tsx
import { useState, useCallback } from "react";
import type { Dictionary, WizardComponent } from "../types/schematic";
import { wizardIdentify, wizardDirectives, wizardLayout, wizardWires } from "../lib/api";

interface GenerateWizardProps {
  imageFile: File;
  dictionary: Dictionary | null;
  onAddComponent: (type: string, name: string, value: string, pos: { x: number; y: number }, value2?: string) => void;
  onAddWire: (from: { x: number; y: number }, to: { x: number; y: number }) => void;
  onAddFlag: (name: string, pos: { x: number; y: number }) => void;
  onAddText: (content: string, pos: { x: number; y: number }) => void;
  onClose: () => void;
}

type WizardStep = "canvas" | "identify" | "directives" | "layout" | "wires" | "done";

export function GenerateWizard({
  imageFile,
  dictionary,
  onAddComponent,
  onAddWire,
  onAddFlag,
  onAddText,
  onClose,
}: GenerateWizardProps) {
  const [step, setStep] = useState<WizardStep>("canvas");
  const [minimized, setMinimized] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 1 state
  const [sheetWidth, setSheetWidth] = useState(880);
  const [sheetHeight, setSheetHeight] = useState(680);

  // Step 2 state
  const [components, setComponents] = useState<WizardComponent[]>([]);

  // Step 3 state
  const [directives, setDirectives] = useState<string[]>([]);

  // Step 4 state
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});

  const stepLabels: Record<WizardStep, string> = {
    canvas: "1. Canvas",
    identify: "2. Components",
    directives: "3. Directives",
    layout: "4. Layout",
    wires: "5. Wires",
    done: "Done",
  };

  const handleIdentify = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await wizardIdentify(imageFile);
      setComponents(result.components.map((c) => ({ ...c, confirmed: false })));
      setStep("identify");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [imageFile]);

  const handleDirectives = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await wizardDirectives(imageFile);
      setDirectives(result.directives);
      setStep("directives");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [imageFile]);

  const handleLayout = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const confirmed = components.filter((c) => c.confirmed !== false);
      const result = await wizardLayout(imageFile, confirmed);
      setPositions(result.positions);

      // Add components to schematic
      for (const comp of confirmed) {
        const pos = result.positions[comp.instanceName] || { x: 400, y: 300 };
        onAddComponent(comp.type, comp.instanceName, comp.value, pos, comp.value2);
      }

      setStep("layout");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [imageFile, components, onAddComponent]);

  const handleWires = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const confirmed = components.filter((c) => c.confirmed !== false);
      const result = await wizardWires(imageFile, confirmed, positions);

      // Add wires to schematic
      for (const w of result.wires) {
        onAddWire({ x: w.x1, y: w.y1 }, { x: w.x2, y: w.y2 });
      }

      // Add flags
      for (const f of result.flags) {
        onAddFlag(f.name, { x: f.x, y: f.y });
      }

      // Add directives as text
      let textY = sheetHeight - 80;
      for (const d of directives) {
        onAddText(d, { x: 400, y: textY });
        textY += 30;
      }

      setStep("done");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [imageFile, components, positions, directives, onAddWire, onAddFlag, onAddText, sheetHeight]);

  // Minimized pill
  if (minimized) {
    return (
      <div
        onClick={() => setMinimized(false)}
        style={{
          position: "fixed", bottom: 16, left: "50%", transform: "translateX(-50%)",
          background: "var(--color-selection)", color: "#fff", padding: "8px 20px",
          borderRadius: 20, cursor: "pointer", zIndex: 999, fontSize: 13,
        }}
      >
        Generation in progress — click to resume ({stepLabels[step]})
      </div>
    );
  }

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 998, display: "flex",
      alignItems: "center", justifyContent: "center", background: "var(--bg-backdrop)",
    }}>
      <div style={{
        background: "var(--bg-modal)", borderRadius: 8, padding: 24,
        width: 600, maxHeight: "80vh", overflow: "auto",
        boxShadow: "0 8px 32px rgba(0,0,0,0.3)", color: "var(--color-text)",
      }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <strong style={{ fontSize: 16 }}>Generate — {stepLabels[step]}</strong>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={() => setMinimized(true)} title="Minimize">—</button>
            <button onClick={onClose} title="Close">✕</button>
          </div>
        </div>

        {error && <div style={{ color: "var(--color-error)", marginBottom: 12, fontSize: 13 }}>{error}</div>}

        {/* Step 1: Canvas */}
        {step === "canvas" && (
          <div>
            <p>Sheet size (auto-detected):</p>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 16 }}>
              <label>Width: <input type="number" value={sheetWidth} onChange={(e) => setSheetWidth(+e.target.value)} style={{ width: 80 }} /></label>
              <label>Height: <input type="number" value={sheetHeight} onChange={(e) => setSheetHeight(+e.target.value)} style={{ width: 80 }} /></label>
            </div>
            <button onClick={handleIdentify} disabled={loading}>
              {loading ? "Identifying components..." : "Next — Identify Components"}
            </button>
          </div>
        )}

        {/* Step 2: Identify */}
        {step === "identify" && (
          <div>
            <p>{components.length} component(s) found:</p>
            <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: 4 }}>Type</th>
                  <th style={{ textAlign: "left", padding: 4 }}>Name</th>
                  <th style={{ textAlign: "left", padding: 4 }}>Value</th>
                  <th style={{ padding: 4 }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {components.map((c, i) => (
                  <tr key={i} style={{ borderTop: "1px solid var(--color-border)" }}>
                    <td style={{ padding: 4 }}>
                      <select value={c.type} onChange={(e) => {
                        const updated = [...components];
                        updated[i] = { ...c, type: e.target.value };
                        setComponents(updated);
                      }}>
                        {dictionary && Object.keys(dictionary.components).map((id) => (
                          <option key={id} value={id}>{dictionary.components[id].displayName}</option>
                        ))}
                      </select>
                    </td>
                    <td style={{ padding: 4 }}>
                      <input value={c.instanceName} onChange={(e) => {
                        const updated = [...components];
                        updated[i] = { ...c, instanceName: e.target.value };
                        setComponents(updated);
                      }} style={{ width: 60 }} />
                    </td>
                    <td style={{ padding: 4 }}>
                      <input value={c.value} onChange={(e) => {
                        const updated = [...components];
                        updated[i] = { ...c, value: e.target.value };
                        setComponents(updated);
                      }} style={{ width: 120 }} />
                    </td>
                    <td style={{ padding: 4, textAlign: "center" }}>
                      <button onClick={() => {
                        const updated = [...components];
                        updated[i] = { ...c, confirmed: true };
                        setComponents(updated);
                      }} style={{ color: c.confirmed ? "var(--color-success)" : undefined }}>
                        {c.confirmed ? "✓" : "Confirm"}
                      </button>
                      <button onClick={() => setComponents(components.filter((_, j) => j !== i))} style={{ color: "var(--color-error)", marginLeft: 4 }}>✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
              <button onClick={() => setComponents([...components, { type: "res", instanceName: `R${components.length + 1}`, value: "1k", confirmed: false }])}>
                + Add Missing
              </button>
              <button onClick={handleDirectives} disabled={loading}>
                {loading ? "Reading directives..." : "Next — Read Directives"}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Directives */}
        {step === "directives" && (
          <div>
            <p>{directives.length} directive(s) found:</p>
            {directives.map((d, i) => (
              <div key={i} style={{ display: "flex", gap: 4, marginBottom: 4 }}>
                <input value={d} onChange={(e) => {
                  const updated = [...directives];
                  updated[i] = e.target.value;
                  setDirectives(updated);
                }} style={{ flex: 1 }} />
                <button onClick={() => setDirectives(directives.filter((_, j) => j !== i))} style={{ color: "var(--color-error)" }}>✕</button>
              </div>
            ))}
            <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
              <button onClick={() => setDirectives([...directives, ".tran 1"])}>+ Add</button>
              <button onClick={handleLayout} disabled={loading}>
                {loading ? "Computing layout..." : "Next — Place Components"}
              </button>
            </div>
          </div>
        )}

        {/* Step 4: Layout */}
        {step === "layout" && (
          <div>
            <p>Components placed in editor. Drag to adjust positions, then continue.</p>
            <p style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
              Minimize this dialog to interact with the editor, then resume.
            </p>
            <button onClick={handleWires} disabled={loading}>
              {loading ? "Tracing wires..." : "Next — Trace Wires"}
            </button>
          </div>
        )}

        {/* Step 5: Wires */}
        {step === "wires" && (
          <div>
            <p>Processing wires...</p>
          </div>
        )}

        {/* Done */}
        {step === "done" && (
          <div>
            <p style={{ color: "var(--color-success)", fontWeight: "bold" }}>Generation complete!</p>
            <p>{components.filter((c) => c.confirmed !== false).length} components, {directives.length} directives placed.</p>
            <p>Review and adjust in the editor, then export.</p>
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button onClick={onClose}>Close</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify frontend builds**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/GenerateWizard.tsx
git commit -m "feat: add Generate Wizard modal with 5-step workflow"
```

---

### Task 15: App.tsx Integration + Layout Overhaul

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/ComponentPalette.tsx`
- Delete: `frontend/src/components/ImagePanel.tsx`

- [ ] **Step 1: Update App.tsx with new layout, wizard, theme, grid toggle**

Rewrite `frontend/src/App.tsx` to:
- Import and use `useTheme` hook
- Add `showGrid` state
- Replace `ImagePanel` with `ScreenshotPanel` in bottom-right
- Add `GenerateWizard` modal (shown when `wizardOpen` is true)
- Pass `showGrid`, `theme`, `toggleTheme`, `toggleGrid` to `Toolbar` and `Editor`
- Make `ComponentPalette` collapsible
- Add `addText` to `useSchematic` if not present (for directives) — or use a simple inline function
- Remove the old `generateFromImage` import and `handleGenerate` that used the single-call API

Key changes to the layout structure:
```tsx
<div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
  <Toolbar ... showGrid={showGrid} onToggleGrid={() => setShowGrid(g => !g)} theme={theme} onToggleTheme={toggleTheme} />
  <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
    {showPalette && <ComponentPalette ... collapsed={!showPalette} onToggle={() => setShowPalette(p => !p)} />}
    <Editor ... showGrid={showGrid} />
    <div style={{ width: 280, display: "flex", flexDirection: "column" }}>
      <PropertyPanel ... />
      <AscPreview ... />
      <ScreenshotPanel imageUrl={imageUrl} />
    </div>
  </div>
  <footer ...>{status}</footer>
  {wizardOpen && <GenerateWizard ... onClose={() => setWizardOpen(false)} />}
</div>
```

- [ ] **Step 2: Update ComponentPalette to be collapsible with toggle button**

Add a `collapsed`/`onToggle` prop. When collapsed, show only the toggle button. Add reference images from dictionary SVG paths next to component names.

- [ ] **Step 3: Delete ImagePanel.tsx** (replaced by ScreenshotPanel)

```bash
rm frontend/src/components/ImagePanel.tsx
```

- [ ] **Step 4: Verify frontend builds**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: integrate wizard, new layout, collapsible palette, theme, grid toggle"
```

---

### Task 16: Run All Tests + Final Verification

**Files:** None — validation task.

- [ ] **Step 1: Run all backend tests**

Run:
```bash
cd backend && python -m pytest tests/ -v
```
Expected: All tests pass.

- [ ] **Step 2: Run frontend build**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A && git commit -m "chore: all tests passing, build verified"
```
