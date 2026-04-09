# Algorithm V2 + UI Overhaul Design Spec

## Overview

Redesign the image-to-asc pipeline from a single monolithic LLM call into a multi-step wizard with focused prompts, user confirmation at each step, and an improved UI layout. Parse LTspice's native `.asy` symbol files for pixel-perfect dictionary entries.

## Goals

- Eliminate timeout issues by splitting into small, focused LLM calls
- Let users confirm/correct each extraction step before proceeding
- Use `.asy` files as the ground truth for component geometry and pin positions
- Improve UI layout: collapsible tools panel with reference images, screenshot in bottom-right
- Remove the redundant LLM refinement stage — use deterministic .asc generation only
- Fix component rotation rendering in the SVG editor
- Add scale indicator and grid toggle to the editor
- Dark mode and light mode theme support

## Non-Goals

- Fully automated (zero-click) extraction — this is intentionally interactive
- Supporting non-LTspice schematic styles
- Training or fine-tuning models

---

## 1. `.asy` Parser & Dictionary Upgrade

### `.asy` File Format

LTspice symbol files at `%LOCALAPPDATA%\LTspice\lib\sym\` use this format:

```
Version 4
SymbolType CELL
LINE Normal x1 y1 x2 y2
CIRCLE Normal x1 y1 x2 y2
ARC Normal x1 y1 x2 y2 x3 y3 x4 y4
RECTANGLE Normal x1 y1 x2 y2
WINDOW index x y justification fontSize
SYMATTR key value
PIN x y NONE rotation
PINATTR PinName name
PINATTR SpiceOrder n
```

### Parser

A Python module that reads `.asy` files and extracts:

- **Geometry**: all LINE, CIRCLE, ARC, RECTANGLE commands with coordinates
- **Pins**: position (x, y), name, SPICE order
- **Metadata**: SYMATTR Value (default symbol name), Prefix (R, C, V, etc.), Description
- **Windows**: label placement positions

The parser scans the LTspice sym directory and builds a structured dictionary. It handles both root-level symbols (res.asy, cap.asy) and subdirectory symbols (OpAmps/opamp2.asy).

### Dictionary Format Update

`dictionary/components.json` gains new fields from `.asy` parsing:

```json
{
  "res": {
    "id": "res",
    "category": "passive",
    "displayName": "Resistor",
    "asySource": "res.asy",
    "geometry": {
      "lines": [
        {"x1": 16, "y1": 88, "x2": 16, "y2": 96},
        {"x1": 0, "y1": 80, "x2": 16, "y2": 88},
        {"x1": 32, "y1": 64, "x2": 0, "y2": 80},
        {"x1": 0, "y1": 48, "x2": 32, "y2": 64},
        {"x1": 32, "y1": 32, "x2": 0, "y2": 48},
        {"x1": 16, "y1": 16, "x2": 16, "y2": 24},
        {"x1": 16, "y1": 24, "x2": 32, "y2": 32}
      ],
      "circles": [],
      "arcs": [],
      "bounds": {"minX": 0, "minY": 16, "maxX": 32, "maxY": 96}
    },
    "pins": [
      {"name": "A", "x": 16, "y": 16, "spiceOrder": 1},
      {"name": "B", "x": 16, "y": 96, "spiceOrder": 2}
    ],
    "prefix": "R",
    "description": "A resistor",
    "windows": [
      {"index": 0, "x": 36, "y": 40, "justification": "Left", "fontSize": 2},
      {"index": 3, "x": 36, "y": 76, "justification": "Left", "fontSize": 2}
    ],
    "symbol": {
      "width": 32,
      "height": 80,
      "svgPath": "<generated from geometry>"
    },
    "rotations": ["R0", "R90", "R180", "R270", "M0", "M90"]
  }
}
```

The existing hand-crafted `svgPath` is replaced with one generated from the `.asy` geometry. The `symbol.width` and `symbol.height` are computed from `geometry.bounds`.

### SVG Generation from `.asy` Geometry

Convert parsed LINE/CIRCLE/ARC commands into an SVG path string:
- `LINE Normal x1 y1 x2 y2` → `M x1,y1 L x2,y2`
- `CIRCLE Normal x1 y1 x2 y2` → SVG ellipse (bounding box)
- `ARC Normal x1 y1 x2 y2 x3 y3 x4 y4` → SVG arc command
- `RECTANGLE Normal x1 y1 x2 y2` → `M x1,y1 L x2,y1 L x2,y2 L x1,y2 Z`

Coordinates are normalized so the symbol's top-left is at (0,0).

### Which `.asy` Files to Parse

Parse these core symbols on startup (matching our current dictionary):

| File | Dictionary ID |
|------|--------------|
| `res.asy` | res |
| `cap.asy` | cap |
| `ind.asy` | ind |
| `voltage.asy` | voltage |
| `current.asy` | current |
| `OpAmps/opamp2.asy` | opamp2 |
| `OpAmps/opamp.asy` | opamp |
| `npn.asy` | npn |
| `pnp.asy` | pnp |
| `nmos.asy` | nmos |
| `pmos.asy` | pmos |
| `diode.asy` | diode |
| `zener.asy` | zener |

The parser also accepts a configurable LTspice path for non-default installations.

---

## 2. UI Layout Changes

### New Layout

```
+------------------------------------------------------------------+
|  image2asc  [Upload] [Generate ▸] [Export .asc] | [Undo] [Redo]  |
+----------+-------------------------------------------+-----------+
| [≡] Tools|                                           | Property  |
|          |                                           | Panel     |
| [img] Res|         SVG Visual Editor                  |           |
| [img] Cap|         (main workspace)                   |-----------|
| [img] Ind|                                           | .asc      |
|          |                                           | Preview   |
| [img] VS |                                           |           |
| [img] CS |                                           |-----------|
|          |                                           | Screenshot|
| [img] Op2|                                           | [⤢][⛶]   |
| [img] Op |                                           |           |
|          |                                           |           |
| [Wire]   |                                           |           |
| [Flag]   |                                           |           |
+----------+-------------------------------------------+-----------+
| Status bar                                                       |
+------------------------------------------------------------------+
```

### Tools Panel (left)
- **Collapsible**: toggle button `[≡]` at top to show/hide
- **Component buttons**: each shows a small rendered reference image (from `.asy` geometry) alongside the component name
- **Select/Wire/Flag tools**: remain at the top of the panel
- Categories group components: Passive, Sources, Amplifiers, Semiconductors

### Right Panel (stacked)
- **Property Panel** (top): edit selected component properties — same as current
- **.asc Preview** (middle): live .asc text output — same as current
- **Screenshot Panel** (bottom): the uploaded LTspice image
  - **Expand button** `[⤢]`: enlarges the screenshot panel to take more of the right column
  - **Fullscreen button** `[⛶]`: opens the image in a fullscreen overlay with zoom/pan
  - Default state: small thumbnail showing the uploaded image

### Editor (center)
- Takes the full remaining space
- Same SVG editor with grid, drag, pan, zoom as current

---

## 3. Generate Wizard (Toggleable Modal)

### Modal Behavior
- Opens when user clicks "Generate" (requires an uploaded image)
- Floats over the editor as a centered modal with semi-transparent backdrop
- **Hide button**: minimizes the modal to a floating pill at the bottom of the editor ("Generation in progress — click to resume")
- **Show button**: clicking the pill or pressing a keyboard shortcut re-opens the modal
- State is fully preserved when hidden/shown
- Editor is interactive behind the modal when hidden (user can drag components, draw wires)
- Modal closes when the wizard completes or user clicks "Close"

### Wizard Steps

#### Step 1: Canvas Setup
- Auto-detect canvas size from image pixel dimensions
- Map image pixels to LTspice grid coordinates (LTspice uses a fixed pixel-to-grid ratio)
- Default: 880x680
- UI: shows detected size, user can adjust width/height with input fields
- Button: "Next" to proceed

#### Step 2: Identify Components
- **LLM Call**: "List every component visible in this LTspice schematic. For each component, provide: type, instance name (e.g. R1, U1), and value."
- LLM returns a flat list — no coordinates, no wires
- UI: shows a table of identified components, each row has:
  - Cropped region from original image (if possible) or the full image with highlight
  - LLM's guess: type + name + value
  - Dictionary reference image for the guessed type (rendered from `.asy` geometry)
  - Confirm button (checkmark)
  - Change button → opens dropdown of all dictionary components to pick the correct one
  - Delete button (if the LLM hallucinated a component)
- User can also click "Add Missing" to manually add a component the LLM missed
- Button: "Next" (only active when at least one component is confirmed)

#### Step 3: Read Directives
- **LLM Call**: "Read all SPICE directives visible in this schematic. These are text lines starting with a dot (.), typically at the bottom. List each directive exactly as written."
- LLM returns a list of directive strings
- UI: shows each directive as an editable text field, user can confirm, edit, delete, or add missing
- Button: "Next"

#### Step 4: Place Components
- **LLM Call**: "Given these confirmed components: [list], describe the spatial layout. For each component, describe its approximate position (top-left, center, bottom-right, etc.) and which other components are nearby."
- The backend converts the qualitative descriptions into grid coordinates using a layout algorithm:
  - Parse relative positions ("R5 is at the top, U1 is in the center")
  - Assign initial grid coordinates based on spatial descriptions
  - Spread components to avoid overlap using component dimensions from the dictionary
- UI: shows the editor with components placed at estimated positions
- User can drag any component to adjust its position — the editor is live
- Button: "Next"

#### Step 5: Wire Connections
- **LLM Call**: "Looking at this schematic, describe how the components are connected. For each wire, say which component pin connects to which other component pin. Also list any ground connections and net labels (flags)."
- The backend converts pin-to-pin connections into WIRE coordinates using the placed component positions + pin offsets from the dictionary
- Also adds FLAG elements for ground and net labels
- UI: shows the editor with wires drawn, user can review/edit
- User can delete incorrect wires, draw new ones manually
- Button: "Finish"

#### Completion
- Modal shows a summary: N components, N wires, N flags, N directives
- Validation result (from the .asc validator)
- Buttons: "Close" (dismiss modal, keep editing), "Export .asc" (immediate download)

---

## 4. Prompting Strategy

### Principles
- **One task per LLM call** — never ask for everything at once
- **No coordinate estimation** — LLMs are bad at pixel coordinates; use qualitative descriptions and convert algorithmically
- **Small output** — simple lists, not complex nested JSON
- **Temperature 0.1** — minimize randomness for structured extraction

### Prompt: Step 2 (Identify Components)

System:
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
```

User:
```
List every component in this schematic. For each, provide:
- type (one of: res, cap, ind, voltage, current, opamp2, opamp, npn, pnp, nmos, pmos, diode, zener)
- instanceName (the label, e.g. R1, U1, V3)
- value (the displayed value, e.g. "1k", "ADA4627", "{PSV}")
- value2 (only for voltage sources with a second value like "AC 0.01", otherwise omit)

Output as JSON array:
[{"type": "res", "instanceName": "R1", "value": "1k"}, ...]
```

### Prompt: Step 3 (Read Directives)

System:
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

Read the text exactly as it appears — do not modify or interpret it.
```

User:
```
List every SPICE directive visible in this schematic.
Output as a JSON array of strings:
[".param RINP=1k PSV=15", ".tran 0.005", ".noise V(OUT) V3 dec 10 1 1Meg"]
```

### Prompt: Step 4 (Spatial Layout)

System:
```
You are describing the spatial layout of components in an LTspice schematic.

Use a coordinate system where (0,0) is the top-left of the schematic.
Describe positions using grid regions: top-left, top-center, top-right, center-left, center, center-right, bottom-left, bottom-center, bottom-right.
Also describe relative positions between components (e.g. "R5 is directly above U1", "V1 is to the right of U1").
```

User:
```
These components were identified in the schematic:
{confirmed_component_list}

For each component, describe:
- region: which area of the schematic it occupies (top-left, center, bottom-right, etc.)
- nearby: which other components are adjacent and in which direction

Output as JSON array:
[{"instanceName": "U1", "region": "center", "nearby": [{"name": "R5", "direction": "above"}, {"name": "V1", "direction": "right"}]}, ...]
```

### Prompt: Step 5 (Wire Connections)

System:
```
You are tracing wire connections in an LTspice schematic.

Wires in LTspice are straight blue lines (horizontal or vertical) that connect component pins. Wires meet at junctions (small blue dots/squares).

Ground connections appear as small downward-pointing triangles labeled "0".
Net labels are text labels at wire endpoints (like "OUT", "VP", "VN").

Describe connections in terms of component pins, not coordinates.
```

User:
```
These components are in the schematic:
{confirmed_component_list_with_pin_names}

Describe every wire connection:
- Which component pin connects to which other component pin
- Any ground connections (which pin connects to ground)
- Any net labels (which pin has a label and what is it)

Output as JSON:
{
  "connections": [
    {"from": {"component": "R5", "pin": "2"}, "to": {"component": "U1", "pin": "in-"}},
    ...
  ],
  "grounds": [
    {"component": "V3", "pin": "-"},
    ...
  ],
  "labels": [
    {"component": "U1", "pin": "out", "label": "OUT"},
    ...
  ]
}
```

---

## 5. Layout Algorithm (Step 4 Backend)

Converts qualitative spatial descriptions into grid coordinates.

### Algorithm

1. **Region mapping**: Divide the 880x680 sheet into a 3x3 grid of regions:
   - top-left: (80, 80), top-center: (440, 80), top-right: (720, 80)
   - center-left: (80, 340), center: (440, 340), center-right: (720, 340)
   - bottom-left: (80, 540), bottom-center: (440, 540), bottom-right: (720, 540)

2. **Initial placement**: Place each component at its region's center point

3. **Relative adjustment**: For each "nearby" relationship, adjust positions:
   - "R5 is above U1" → move R5 y-coordinate to be above U1 by component height + margin
   - "V1 is to the right of U1" → move V1 x-coordinate to be right of U1 by component width + margin

4. **Overlap resolution**: If any two components overlap (based on their dictionary bounds), push them apart

5. **Grid snap**: Snap all positions to multiples of 16

---

## 6. Wire Generation (Step 5 Backend)

Converts pin-to-pin connections into WIRE coordinates.

### Algorithm

1. For each connection, look up the source component position + source pin offset (from dictionary)
2. Look up the destination component position + destination pin offset
3. Calculate the absolute pin positions: `component_position + pin_offset`
4. Generate orthogonal wire routing between the two pin positions:
   - Simple L-route: horizontal then vertical (or vertical then horizontal)
   - If the L-route would cross a component, try a Z-route (horizontal-vertical-horizontal)
5. Generate FLAG elements for ground connections and net labels at the appropriate pin positions

---

## 7. Kill the Refinement Stage

- Remove the `refine_to_asc` LLM call entirely
- The deterministic `generate_asc()` in `asc_generator.py` handles all .asc generation
- This eliminates the Qwen3:14b dependency — only Qwen3-VL 8B is needed
- The `refinement.py` service and `refine_system.txt` prompt are deleted

---

## 8. Editor Improvements

### Component Rotation

Currently the SVG editor ignores the `rotation` property — all components render at R0. Fix by applying an SVG transform based on the rotation value:

| Rotation | SVG Transform (around component center) |
|----------|-----------------------------------------|
| R0 | none |
| R90 | `rotate(90, cx, cy)` |
| R180 | `rotate(180, cx, cy)` |
| R270 | `rotate(270, cx, cy)` |
| M0 | `scale(-1, 1)` (horizontal mirror) |
| M90 | `scale(-1, 1) rotate(90)` (mirror + 90) |

The center point `(cx, cy)` is computed from the component's dictionary bounds: `cx = width/2`, `cy = height/2`. Pin positions must also be transformed to match the rotation so wires connect to the correct locations.

### Scale Indicator

Show the current zoom level in the bottom-left corner of the editor canvas:
- Display as percentage: "100%", "150%", "50%"
- Calculated from: `baseViewBoxWidth / currentViewBoxWidth * 100`
- Base viewbox is 880x680 (the default sheet size)
- Also show a small ruler graphic (e.g. a 100-unit line with tick marks) that scales with zoom to give spatial reference

### Grid Toggle

Add a button to the toolbar (or editor controls area) to show/hide the grid dots:
- Default: grid visible
- Icon: grid symbol or "Grid" text toggle button
- State stored in component state, passed to the Editor SVG as a prop
- When hidden, the grid pattern is not rendered but snap-to-grid still works (snapping is independent of grid visibility)

### Dark Mode / Light Mode

Toggle between dark and light themes via a button in the toolbar (sun/moon icon).

**Light mode (default):**
| Element | Color |
|---------|-------|
| Editor background | `#e8e8e8` |
| Grid dots | `#cccccc` |
| Components/wires | `#0000CC` (LTspice blue) |
| Component labels | `#0000CC` |
| Toolbar/panels background | `#f5f5f5` |
| Panel text | `#333333` |
| Borders | `#cccccc` |
| Selection highlight | `#2196F3` |

**Dark mode:**
| Element | Color |
|---------|-------|
| Editor background | `#1e1e1e` |
| Grid dots | `#333333` |
| Components/wires | `#6699FF` (lighter blue for contrast) |
| Component labels | `#6699FF` |
| Toolbar/panels background | `#2d2d2d` |
| Panel text | `#e0e0e0` |
| Borders | `#444444` |
| Selection highlight | `#42a5f5` |

Implementation:
- Store theme preference in `localStorage` so it persists across sessions
- Respect OS preference on first visit via `prefers-color-scheme` media query
- Use CSS custom properties (`--bg-editor`, `--color-component`, etc.) defined on `:root` and toggled via a `data-theme="dark"` attribute on `<html>`
- The `.asc preview` panel uses a monospace font with theme-aware colors
- The screenshot panel keeps its original image colors regardless of theme

---

## 9. New API Endpoints

The current `/api/generate` endpoint (single call) is replaced with step-by-step endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/wizard/identify` | Step 2: send image, get component list |
| POST | `/api/wizard/directives` | Step 3: send image, get directive list |
| POST | `/api/wizard/layout` | Step 4: send image + confirmed components, get spatial layout |
| POST | `/api/wizard/wires` | Step 5: send image + placed components, get connections |
| POST | `/api/layout/compute` | Convert spatial descriptions to grid coordinates |
| POST | `/api/wires/compute` | Convert pin connections to WIRE coordinates |

Existing endpoints remain:
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/dictionary` | Component and directive definitions |
| POST | `/api/refine` | Convert IR to .asc (deterministic, no LLM) |
| POST | `/api/validate` | Validate .asc syntax |

The old `POST /api/generate` is removed.

---

## 9. File Changes Summary

### New Files
- `backend/services/asy_parser.py` — `.asy` file parser
- `backend/services/layout.py` — spatial description to grid coordinate converter
- `backend/services/wire_router.py` — pin-to-pin connection to WIRE coordinate converter
- `backend/api/wizard_routes.py` — wizard step API endpoints
- `backend/prompts/identify_system.txt` — Step 2 system prompt
- `backend/prompts/directives_system.txt` — Step 3 system prompt
- `backend/prompts/layout_system.txt` — Step 4 system prompt
- `backend/prompts/wires_system.txt` — Step 5 system prompt
- `backend/tests/test_asy_parser.py`
- `backend/tests/test_layout.py`
- `backend/tests/test_wire_router.py`
- `frontend/src/components/GenerateWizard.tsx` — modal wizard component
- `frontend/src/components/ScreenshotPanel.tsx` — bottom-right screenshot display

### Modified Files
- `dictionary/components.json` — add `.asy`-derived geometry, pins, metadata
- `backend/main.py` — mount wizard routes
- `backend/services/vision.py` — split into step-specific functions
- `backend/services/ollama_client.py` — increase timeout to 600s
- `frontend/src/App.tsx` — new layout, integrate wizard modal
- `frontend/src/components/ComponentPalette.tsx` — reference images, collapsible
- `frontend/src/components/Editor.tsx` — expand to fill center, add rotation transforms, scale indicator, grid toggle
- `frontend/src/components/Toolbar.tsx` — add grid toggle button, theme toggle button
- `frontend/src/styles/theme.css` — CSS custom properties for light/dark themes

### Deleted Files
- `backend/services/refinement.py` — replaced by deterministic generation
- `backend/prompts/refine_system.txt` — no longer needed
- `backend/prompts/vision_system.txt` — replaced by step-specific prompts
- `backend/tests/test_refinement.py` — service deleted

---

## Prerequisites

- Ollama installed and running
- `ollama pull qwen3-vl:8b` (only vision model needed now — qwen3:14b no longer required)
- LTspice installed at default location (`%LOCALAPPDATA%\LTspice\`)
- Python 3.10+, Node.js 18+
