# Image2Spice — How It Works

## Overview

Image2Spice converts circuit schematic screenshots into LTspice `.asc` files using a vision language model (VLM) and deterministic algorithms.

```
Screenshot → VLM Analysis → Circuit Graph → Layout → Wire Routing → .asc File
                                                                        ↓
                                                                    LTspice
```

---

## The Pipeline

### Step 1: Vision Analysis — "What's in the picture?"

A vision model (Claude Sonnet or local Ollama) looks at the circuit image and extracts structured data.

**Input:** Circuit screenshot

**Output:** JSON with components, connections, grounds, and labels

```json
{
  "components": [
    {"name": "V1", "type": "voltage", "value": "30V", "x": 10, "y": 30},
    {"name": "R1", "type": "res", "value": "2", "x": 10, "y": 65},
    {"name": "R2", "type": "res", "value": "8", "x": 50, "y": 50}
  ],
  "connections": [
    {"from": "V1.+", "to": "R1.A"},
    {"from": "R1.A", "to": "R2.A"}
  ],
  "grounds": ["V1.-"],
  "labels": [{"pin": "R2.A", "name": "VCC"}]
}
```

**Multi-pass validation:** If any component pins are left unconnected after the first pass, a second VLM pass reviews the image and fixes missing connections.

```python
# Pass 1: Initial analysis
analysis = await analyze_schematic(image_bytes, provider, api_key, model)

# Validate: check for unconnected pins
graph = build_graph_from_analysis(analysis, dictionary)
issues = graph.validate()

# Pass 2: If issues found, ask VLM to fix
if not issues["all_connected"]:
    corrected = await validate_and_fix(image_bytes, analysis, issues, ...)
    analysis = corrected
```

---

### Step 2: Circuit Graph — "How is everything connected?"

The raw VLM connections are merged into **nets** (groups of electrically connected pins) using a **union-find** algorithm.

**Why union-find?** The VLM reports pairwise connections: "V1.+ connects to R1.A" and "R1.A connects to R2.A". Union-find merges these into a single net: `{V1.+, R1.A, R2.A}` — all electrically the same point.

```python
class CircuitGraph:
    def build_nets(self, connections, grounds, labels):
        # Union-find: merge connected pins
        for conn in connections:
            pin_a = (conn["from"]["component"], conn["from"]["pin"])
            pin_b = (conn["to"]["component"], conn["to"]["pin"])
            self._uf_union(pin_a, pin_b)

        # Group pins by their root representative
        for pin in all_pins:
            root = self._uf_find(pin)
            groups[root].append(pin)

        # Result: nets like {net_0: [V1.+, R1.A, R2.A, R3.A, V2.-]}
```

**Example — Circuit 04 (parallel resistors):**
```
Connections:  V1.+ → R1.A → R2.A → R3.A → V2.-
              V1.- → R1.B → R2.B → R3.B → V2.+

Nets:  net_0 = {V1.+, R1.A, R2.A, R3.A, V2.-}   ← top bus
       net_1 = {V1.-, R1.B, R2.B, R3.B, V2.+}   ← bottom bus
```

---

### Step 3: Orientation Resolution — "Which way does each component face?"

Component orientation is determined from **circuit topology**, not from the VLM. This ensures correctness even when the VLM can't tell which end is + or -.

```python
def resolve_orientations(self):
    for name, node in self.components.items():
        pin_a_net_tier = self._net_tiers[pin_a_net]
        pin_b_net_tier = self._net_tiers[pin_b_net]

        if pin_a_net_tier < pin_b_net_tier:
            node.resolved_rotation = "R0"    # Pin A on top
        elif pin_a_net_tier > pin_b_net_tier:
            node.resolved_rotation = "R180"  # Flipped
        else:
            node.resolved_rotation = "R90"   # Horizontal
```

**Example:** V2's `-` pin connects to the top net (tier 0) and `+` pin connects to the bottom net (tier 1). Since `-` is pin A for voltage and its net tier (0) < `+` net tier (1), V2 gets `R180` (flipped).

---

### Step 4: Layout — "Where does everything go?"

Components are placed at the positions the VLM reported (as percentages of image width/height), then aligned into columns.

```python
# Map VLM percentages to canvas coordinates
x = snap(MARGIN + (x_pct / 100) * (sheet_width - 2 * MARGIN))
y = snap(MARGIN + (y_pct / 100) * (sheet_height - 2 * MARGIN))

# Column alignment: if V1 and R1 are directly connected
# and roughly in the same column, snap them to the same X
if dx < threshold and dy > dx:
    avg_x = snap((v1_x + r1_x) / 2)
    v1.position = (avg_x, v1_y)
    r1.position = (avg_x, r1_y)
```

**Result:**
```
  V1 (x=160)          R2 (x=576)         V2 (x=992)
      |                    |                   |
  R1 (x=160)                              R3 (x=992)
```

V1 and R1 share x=160 (same column). V2 and R3 share x=992.

---

### Step 5: Wire Routing — "How do the wires run?"

The routing algorithm produces clean orthogonal wires using a **"direct wires + bus"** strategy:

```python
def _route_net_with_direct_wires(pin_positions, pin_components):
    # 1. Group pins by column (same X coordinate)
    columns = group_by_x(pin_positions, tolerance=16)

    # 2. Draw direct vertical wires within each column
    for column in columns:
        sort by Y, connect adjacent pins vertically

    # 3. Draw horizontal bus connecting all columns
    bus_y = pick Y above or below all pins (minimize stub length)
    draw horizontal wire from leftmost to rightmost column

    # 4. One vertical stub per column to reach the bus
    for each column:
        draw stub from closest pin to bus_y
```

**Example — Circuit 04:**
```
Step 1: Columns → {x=160: [V1.+, R1.A]}, {x=576: [R2.A]}, {x=992: [V2.-, R3.A]}

Step 2: Direct vertical wires
  WIRE 160 256 160 512    (V1.+ down to R1.A)
  WIRE 992 256 992 512    (V2.- down to R3.A)

Step 3: Horizontal bus at y=240
  WIRE 160 240 992 240    (spanning all columns)

Step 4: Stubs to bus
  WIRE 160 256 160 240    (V1.+ up to bus)
  WIRE 576 400 576 240    (R2.A up to bus)
  WIRE 992 256 992 240    (V2.- up to bus)
```

**Visual result:**
```
    ════════════ bus y=240 ════════════
     │              │              │
    V1.+           R2.A          V2.-
     │                             │
    (direct wire)             (direct wire)
     │                             │
    R1.A                         R3.A
     │              │              │
    ════════════ bus y=608 ════════════
```

---

### Step 6: .asc Export — "Make it work in LTspice"

The final .asc file uses LTspice coordinates. Component positions are converted from SVG space to LTspice origin space:

```python
# SVG space: position = top-left of visual bounding box
# LTspice space: position = symbol origin point
# Conversion: subtract the geometry bounds offset

bounds = dictionary["components"][type]["geometry"]["bounds"]
# bounds = [minX, minY, maxX, maxY], e.g. [-32, 16, 32, 96] for voltage

ltspice_x = svg_x - bounds[0]   # e.g. 160 - (-32) = 192
ltspice_y = svg_y - bounds[1]   # e.g. 240 - 16 = 224
```

**Output .asc:**
```
Version 4
SHEET 1 1135 800
WIRE 160 240 992 240
WIRE 160 256 160 512
WIRE 992 256 992 512
SYMBOL voltage 192 224 R0
WINDOW 0 24 16 Left 2
WINDOW 3 24 96 Left 2
SYMATTR InstName V1
SYMATTR Value 30
SYMBOL res 160 496 R0
SYMATTR InstName R1
SYMATTR Value 2
```

---

## Pin Position Calculation

Pins are defined in LTspice local coordinates in the component dictionary. To get the screen position, we apply two transforms:

```
1. Bounds offset:  svg_pin = ltspice_pin - bounds_min
2. Rotation:       rotated_pin = rotate(svg_pin, around center of symbol)
3. Absolute:       screen_pos = component_position + rotated_pin
```

```python
# Example: Voltage source + pin at R0
# Dictionary: pin.x=0, pin.y=16, bounds=[-32, 16, 32, 96]
# Symbol size: width=64, height=80

svg_x = 0 - (-32) = 32      # step 1
svg_y = 16 - 16 = 0

# R0 = no rotation            # step 2

screen_x = comp.x + 32       # step 3
screen_y = comp.y + 0
# Pin appears at top-center of the voltage source circle
```

```python
# Same pin at R180 (flipped)
svg_x = 32, svg_y = 0        # step 1

# R180: rotate 180° around (32, 40)
rotated_x = 2*32 - 32 = 32   # step 2
rotated_y = 2*40 - 0 = 80

screen_x = comp.x + 32       # step 3
screen_y = comp.y + 80
# Pin appears at bottom-center (flipped)
```

---

## User Workflow

### Generate
1. Upload circuit screenshot
2. Select VLM provider (Claude Sonnet, OpenAI, or local Ollama)
3. Click Generate → runs the full pipeline (2 VLM passes + deterministic layout/routing)

### Edit
4. **Drag** components to adjust positions
5. **Redraw Wires** → re-runs wire routing with current positions (no VLM call)
6. **Wire mode** → manually draw L-shaped wires that snap to component pins
7. **Select wires** → click or marquee-select, then delete

### Export
8. **Export .asc** → download file that opens in LTspice
9. Coordinates are automatically converted to LTspice format

---

## Architecture

```
Frontend (React + TypeScript + Vite)
├── App.tsx                    — orchestration, state management
├── Editor.tsx                 — SVG schematic editor
│   ├── Component rendering    — SVG paths from dictionary
│   ├── Wire drawing           — LTspice-style L-shaped wires
│   ├── Pin highlighting       — snap-to-pin in wire mode
│   └── Marquee selection      — multi-select wires
├── GenerateWizard.tsx         — generation modal with progress
├── Toolbar.tsx                — buttons, provider selector
├── PropertyPanel.tsx          — edit selected component/wire
├── ascGenerator.ts            — schematic → .asc text
├── ascParser.ts               — .asc text → schematic
└── useSchematic.ts            — CRUD + undo/redo history

Backend (Python + FastAPI)
├── wizard_routes.py           — API endpoints
│   ├── /generate-asc          — full pipeline
│   └── /redraw-wires          — re-route only
├── vision.py                  — VLM calls (analyze, validate)
├── schematic_builder.py       — VLM output → .asc
├── circuit_graph.py           — nets, tiers, orientation
│   ├── Union-Find             — group pins into nets
│   ├── BFS tier assignment    — signal flow hierarchy
│   └── Orientation resolver   — topology-driven rotation
├── wire_router.py             — net-aware routing
│   ├── route_nets()           — bus + direct wire routing
│   └── _route_net_with_direct_wires()
├── layout.py                  — tier-based placement
├── asc_generator.py           — SchematicIR → .asc
└── llm_client.py              — Ollama/OpenRouter/OpenAI/Claude

Dictionary
└── components.json            — 13 LTspice component definitions
    ├── Pin positions           — LTspice local coordinates
    ├── SVG paths               — visual rendering
    ├── Geometry bounds         — coordinate transform offsets
    └── Window positions        — text label placement
```

---

## Key Technologies

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Vision | Claude Sonnet API | Circuit image analysis |
| Backend | Python + FastAPI | API, routing algorithms |
| Frontend | React + TypeScript | SVG editor, UI |
| Data | Union-Find, BFS | Net grouping, tier assignment |
| Export | LTspice .asc format | Industry-standard output |

---

## Ground Truth Validation

The system is validated against hand-crafted reference circuits:

| Circuit | Components | Result |
|---------|-----------|--------|
| 04 — Parallel resistors | V1, V2, R1-R3 | Correct topology, orientation, wiring |
| 03 — Mixed network | V1, R1-R4 | Horizontal + vertical components |
| 07 — RL circuit | V1, R, L | Simple two-component |
| 08 — RC circuit | V1, R, C | Simple two-component |
