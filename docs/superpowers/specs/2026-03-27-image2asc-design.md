# image2asc Design Spec

## Overview

A local web application that converts LTspice circuit schematic screenshots into `.asc` files using a hybrid two-stage AI pipeline (vision model + text model) and provides a visual node editor for manual corrections before export.

## Goals

- Accept LTspice screenshot images as input
- Produce valid `.asc` files that open correctly in LTspice
- Provide a visual editor for reviewing and adjusting generated schematics
- Run entirely locally using Ollama models (no cloud APIs)
- Start with simple circuits (~6 components), design to scale toward complex ones

## Non-Goals

- Hand-drawn or textbook schematic support (LTspice screenshots only)
- Simulation execution (just .asc generation)
- Auto-correction without user review

---

## Architecture

### System Diagram

```
Image --> Qwen3-VL 8B --> JSON IR --> Qwen3:14b --> .asc draft
                                                       |
                                   Web UI visual editor (review/adjust)
                                                       |
                                               Final .asc export
```

### Components

#### 1. Component Dictionary

A comprehensive JSON catalog that serves as the single source of truth for all LTspice elements. Used by the vision stage (to know what to look for), the text stage (to generate correct syntax), and the visual editor (to render components).

**Structure per component type:**

```json
{
  "id": "opamp2",
  "category": "amplifiers",
  "displayName": "Op-Amp (2-input)",
  "symbol": {
    "width": 64,
    "height": 96,
    "shape": "triangle",
    "svgPath": "M0,0 L64,48 L0,96 Z"
  },
  "pins": [
    { "name": "out", "position": [64, 48], "direction": "right" },
    { "name": "in+", "position": [0, 64], "direction": "left" },
    { "name": "in-", "position": [0, 32], "direction": "left" },
    { "name": "V+", "position": [32, 0], "direction": "up" },
    { "name": "V-", "position": [32, 96], "direction": "down" }
  ],
  "ascSyntax": {
    "keyword": "SYMBOL",
    "symbolName": "opamp2",
    "attributes": ["InstName", "Value"]
  },
  "rotations": {
    "R0": { "description": "default, output right" },
    "R90": { "description": "output down" },
    "R180": { "description": "output left" },
    "R270": { "description": "output up" },
    "M0": { "description": "mirrored" },
    "M90": { "description": "mirrored + 90" }
  }
}
```

**Component categories to include:**

- Passive: `res`, `cap`, `ind`
- Sources: `voltage`, `current`, `bv` (behavioral)
- Amplifiers: `opamp`, `opamp2`
- Semiconductors: `npn`, `pnp`, `nmos`, `pmos`, `diode`, `zener`
- Digital: `buf`, `inv`, `and`, `or`
- Special: `ground`, `flag` (net label)

**SPICE directives catalog:**

```json
{
  "directives": {
    ".tran": { "syntax": ".tran <tstop>", "description": "Transient analysis" },
    ".ac": { "syntax": ".ac <type> <npts> <fstart> <fstop>", "description": "AC analysis" },
    ".dc": { "syntax": ".dc <source> <start> <stop> <step>", "description": "DC sweep" },
    ".noise": { "syntax": ".noise V(<out>) <src> <type> <npts> <fstart> <fstop>", "description": "Noise analysis" },
    ".param": { "syntax": ".param <name>=<value>", "description": "Parameter definition" },
    ".lib": { "syntax": ".lib <filename>", "description": "Include library" },
    ".model": { "syntax": ".model <name> <type>(<params>)", "description": "Model definition" }
  }
}
```

#### 2. Vision Stage (Qwen3-VL 8B)

Receives the LTspice screenshot and produces a structured JSON intermediate representation (IR).

**Prompt strategy:**

The vision model receives:
- The image
- A system prompt describing LTspice visual conventions (blue components, gray background, wire junctions as dots, component label positions)
- A condensed version of the component dictionary (what shapes map to what types)
- Instructions to output JSON IR

**JSON IR schema:**

```json
{
  "schematic": {
    "sheet": { "width": 880, "height": 680 },
    "components": [
      {
        "type": "opamp2",
        "instanceName": "U1",
        "value": "ADA4627",
        "position": { "x": 400, "y": 128 },
        "rotation": "R0"
      },
      {
        "type": "res",
        "instanceName": "R5",
        "value": "1000 noiseless",
        "position": { "x": 272, "y": 128 },
        "rotation": "R90"
      }
    ],
    "wires": [
      { "from": { "x": 416, "y": 144 }, "to": { "x": 336, "y": 144 } }
    ],
    "flags": [
      { "name": "0", "position": { "x": 160, "y": 272 } },
      { "name": "OUT", "position": { "x": 608, "y": 176 } }
    ],
    "text": [
      { "content": ".param RINP=1k PSV=15", "position": { "x": 400, "y": 450 }, "type": "directive" },
      { "content": ".tran 0.005", "position": { "x": 400, "y": 480 }, "type": "directive" }
    ]
  }
}
```

**Key considerations:**
- LTspice uses a coordinate grid (multiples of 16 typically)
- Component positions in .asc refer to the anchor point of the symbol
- Rotations are critical — R0/R90/R180/R270/M0/M90 change pin positions
- Wire endpoints must align with pin positions for proper connectivity

#### 3. Text Refinement Stage (Qwen3:14b)

Takes the JSON IR and produces a syntactically valid `.asc` file.

**Prompt strategy:**

The text model receives:
- The JSON IR from the vision stage
- A reference `.asc` file (the user's `LTSpice_Amplifier_Noise.asc`) as a formatting example
- The component dictionary entries for all component types present in the IR
- Instructions to produce a valid .asc file following exact LTspice syntax

**Responsibilities:**
- Convert JSON IR to .asc line-by-line syntax
- Ensure `SYMBOL`, `SYMATTR`, `WIRE`, `FLAG`, and `TEXT` lines follow LTspice conventions
- Snap coordinates to the LTspice grid (multiples of 16)
- Validate that wire endpoints connect to component pins
- Include all SPICE directives from the IR

**Validation rules (enforced post-generation):**
- File starts with `Version 4`
- Has exactly one `SHEET` line
- Every `SYMBOL` is followed by its `SYMATTR` lines
- `WIRE` coordinates are integers
- `FLAG` names are valid net labels
- `TEXT` directives start with `.` for SPICE commands

#### 4. Web UI

**Tech stack:**
- **Backend:** Python + FastAPI
- **Frontend:** React (Vite) + SVG-based visual editor
- **Communication:** REST API + WebSocket for generation progress

**Layout:**

```
+--------------------------------------------------+
|  [Upload Image]  [Generate]  [Export .asc]        |
+--------------------------------------------------+
|  Source Image  |  Visual Editor  |  .asc Preview  |
|                |                 |                 |
|  (uploaded     |  (SVG canvas    |  (read-only     |
|   screenshot)  |   with drag/    |   text view,    |
|                |   drop          |   updates live   |
|                |   components,   |   as editor      |
|                |   wire drawing, |   changes)       |
|                |   property      |                 |
|                |   editing)      |                 |
+--------------------------------------------------+
|  Status bar: model progress, errors               |
+--------------------------------------------------+
```

**Visual Editor features:**

- **Component palette:** sidebar with all dictionary components, drag onto canvas
- **Component rendering:** SVG shapes from dictionary, with pin indicators
- **Wire drawing:** click pin-to-pin to draw wires, auto-routing optional (later)
- **Property panel:** click a component to edit instanceName, value, rotation
- **Grid snap:** all placements snap to LTspice grid (16px increments)
- **Zoom/pan:** scroll to zoom, middle-click drag to pan
- **Undo/redo:** standard Ctrl+Z / Ctrl+Y

**API endpoints:**

```
POST /api/generate     -- upload image, returns JSON IR + .asc draft
GET  /api/dictionary   -- returns full component dictionary
POST /api/refine       -- send edited JSON IR, get new .asc
POST /api/validate     -- validate .asc syntax
WS   /api/ws/progress  -- real-time generation progress
```

---

## Data Flow (detailed)

1. User uploads LTspice screenshot via web UI
2. Backend sends image to Qwen3-VL 8B with vision prompt + dictionary context
3. Vision model returns structured JSON IR
4. Backend validates IR against dictionary (component types exist, required fields present)
5. Backend sends IR + reference .asc + dictionary to Qwen3:14b
6. Text model returns .asc draft
7. Backend runs syntax validation on .asc
8. Frontend receives JSON IR (populates visual editor) + .asc text (populates preview)
9. User reviews in visual editor, makes adjustments (move components, redraw wires, edit values)
10. Each edit updates the JSON IR, which re-renders the .asc preview in real-time
11. User clicks Export to save final .asc file

---

## File Structure

```
image2asc/
  backend/
    main.py                  -- FastAPI app entry point
    api/
      routes.py              -- API endpoint handlers
      websocket.py           -- WebSocket progress handler
    services/
      vision.py              -- Qwen3-VL 8B Ollama integration
      refinement.py          -- Qwen3:14b Ollama integration
      validator.py           -- .asc syntax validation
    dictionary/
      components.json        -- Component definitions
      directives.json        -- SPICE directive catalog
      prompts/
        vision_system.txt    -- System prompt for vision model
        vision_user.txt      -- User prompt template for vision model
        refine_system.txt    -- System prompt for text model
        refine_user.txt      -- User prompt template for text model
    requirements.txt
  frontend/
    src/
      App.tsx
      components/
        ImagePanel.tsx       -- Source image display
        Editor.tsx           -- SVG visual node editor
        AscPreview.tsx       -- .asc text preview
        ComponentPalette.tsx -- Draggable component list
        PropertyPanel.tsx    -- Component property editor
        Toolbar.tsx          -- Upload, generate, export buttons
      lib/
        dictionary.ts        -- Dictionary types and loader
        ascGenerator.ts      -- JSON IR to .asc conversion (client-side)
        gridSnap.ts          -- Coordinate snapping utilities
      types/
        schematic.ts         -- JSON IR TypeScript types
    package.json
    vite.config.ts
  dictionary/
    components.json          -- Shared dictionary (copied to both)
    directives.json
  docs/
    superpowers/
      specs/
        2026-03-27-image2asc-design.md
```

---

## Technology Choices

| Choice | Rationale |
|--------|-----------|
| FastAPI | Async Python, easy Ollama integration, WebSocket support |
| React + Vite | Fast dev experience, strong SVG ecosystem |
| SVG (not Canvas) | DOM-based = easier hit testing, event handling, accessibility |
| Ollama HTTP API | Simple REST calls, no SDK needed, model-agnostic |
| JSON IR | Decouples vision output from .asc syntax, enables editor state |
| Shared dictionary | Single source of truth for components across all stages |

---

## Models

| Stage | Model | Ollama Command | VRAM |
|-------|-------|----------------|------|
| Vision | Qwen3-VL 8B | `ollama run qwen3-vl:8b` | ~6 GB (Q4) |
| Refinement | Qwen3:14b | `ollama run qwen3:14b` | ~9 GB (Q4) |

Note: Models run sequentially (vision first, then text), so they don't need to fit in VRAM simultaneously. Ollama handles model swapping automatically.

---

## Scaling Considerations

For growing from simple to complex circuits:

- **Dictionary expansion:** Add new component types as needed — the architecture doesn't change
- **Chunked processing:** For complex schematics, the vision model could process image regions separately, then merge IRs
- **Multi-pass refinement:** The text model could do multiple passes — first topology, then values, then directives
- **Validation tightening:** Add connectivity checks (every wire endpoint must touch a pin or another wire)
- **User feedback loop:** Save user corrections as training data for future prompt improvement

---

## Prerequisites

- Ollama installed and running
- `ollama pull qwen3-vl:8b` (new install needed)
- `ollama pull qwen3:14b` (already installed)
- Python 3.10+
- Node.js 18+
