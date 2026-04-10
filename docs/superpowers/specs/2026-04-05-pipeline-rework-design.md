# Pipeline Rework: VLM Role Shift to Relational Describer

**Date:** 2026-04-05
**Status:** Approved
**Goal:** Fix the broken VLM-to-deterministic handoff so the wizard pipeline produces valid `.asc` files end-to-end.

---

## Problem

The pipeline expects the VLM to bridge detection -> layout -> wiring, but:

1. **Pin name mismatch kills wiring silently.** Dictionary uses canonical names (`A`/`B`, `+`/`-`, `In+`/`In-`/`V+`/`V-`/`OUT`). VLM returns varied names (`1`, `2`, `pin1`, `positive`, `p`). `wire_router._find_pin()` only does case-insensitive lookup — no aliasing. Unmatched connections are silently skipped.
2. **Layout has no collision handling.** `layout.py` maps to 9 fixed points. Multiple components in the same region stack on (432, 336). The 128px "nearby" offsets only work if the VLM describes every relationship.
3. **No VLM output validation.** `_extract_json()` handles markdown fences, but malformed structures pass through silently and downstream code gets garbage.
4. **Wire routing is too simple.** L-shaped horizontal-first routing only. No obstacle avoidance, no junction merging, no alternate route selection.

## Approach

Shift the VLM's role from spatial mapper to relational describer. The VLM provides what it's good at (recognition, relative relationships, reading text). Python handles all deterministic computation (grid placement, wire routing, coordinate math).

**Files changed:** `schemas.py` (new), `layout.py`, `wire_router.py`, `vision.py`, `wizard_routes.py`, `GenerateWizard.tsx`, `api.ts`, prompt `.txt` files.
**Files untouched:** `asc_generator.py`, `ascGenerator.ts`, `useSchematic.ts`, `useHistory.ts`, `validator.py`, `ollama_client.py`, `routes.py`, `components.json`, `directives.json`.

---

## Section 1: Pydantic Models + Pin Normalization

### New file: `backend/services/schemas.py`

Pydantic models that validate every VLM response before it enters the pipeline.

**Models:**

```python
class IdentifiedComponent(BaseModel):
    type: str                    # must exist in components.json keys
    instanceName: str            # e.g. "R1", "U1"
    value: str                   # e.g. "10k", "LM358"
    value2: Optional[str] = None # for dual-value sources

class IdentifyResponse(BaseModel):
    components: list[IdentifiedComponent]
    # Accepts both bare array and {"components": [...]}

class DirectivesResponse(BaseModel):
    directives: list[str]
    # Each validated against /^\.\w+/

class NearbyRef(BaseModel):
    name: str                    # instanceName of nearby component
    direction: str               # one of: above, below, left, right, above-left, above-right, below-left, below-right

class LayoutItem(BaseModel):
    instanceName: str
    region: str                  # one of 9 valid regions
    nearby: list[NearbyRef] = []

class LayoutResponse(BaseModel):
    layout: list[LayoutItem]

class ConnectionEndpoint(BaseModel):
    component: str               # instanceName
    pin: str                     # raw pin name (normalized later)

class WireConnection(BaseModel):
    from_: ConnectionEndpoint = Field(alias="from")
    to: ConnectionEndpoint

class GroundRef(BaseModel):
    component: str
    pin: str

class LabelRef(BaseModel):
    component: str
    pin: str
    label: str

class WiresResponse(BaseModel):
    connections: list[WireConnection] = []
    grounds: list[GroundRef] = []
    labels: list[LabelRef] = []
```

### Pin normalization

A mapping table per component type that translates VLM's varied pin names to dictionary-canonical names.

```python
PIN_ALIASES: dict[str, dict[str, str]]
```

Coverage for all 16 component types. Maps common VLM outputs:
- Numeric: `"1"` -> `"A"`, `"2"` -> `"B"` (for passives)
- Descriptive: `"positive"` -> `"+"`, `"negative"` -> `"-"` (for sources)
- Abbreviated: `"inv"` -> `"In-"`, `"noninv"` -> `"In+"` (for opamps)
- Generic: `"pin1"` -> first pin, `"pin2"` -> second pin (by spiceOrder)
- Passthrough: if already canonical, return as-is

```python
def normalize_pin(comp_type: str, raw_pin: str) -> str:
    """Map VLM pin name to dictionary-canonical name. Returns raw_pin if no alias found."""
```

### Validation flow

```
VLM response string
  -> _extract_json() (existing, handles markdown fences)
  -> Pydantic model.model_validate() 
  -> on success: normalized, typed data -> next pipeline stage
  -> on failure: 400 response with {"error": str, "details": list[str], "raw": str}
```

---

## Section 2: Layout Solver Upgrade

Replace the fixed 9-point grid with iterative constraint-based placement that handles collision avoidance.

### Algorithm: 5 phases

**Phase 1 — Initial region placement (improved)**
- Same 9-region coordinate map as today
- If multiple components land in the same region, offset them in a grid pattern within that region (e.g., 2 components: side by side at -64px and +64px from region center)

**Phase 2 — Relative constraint enforcement**
- For each "nearby" relationship from VLM (e.g., "R1 is above U1"), verify the spatial constraint holds (R1.y < U1.y)
- If violated, shift the constrained component by 128px in the stated direction from the reference component
- Process constraints in order: components with more constraints are placed first (they become anchors)

**Phase 3 — Collision resolution (new)**
- Load bounding boxes from `components.json` (`geometry.bounds`) for each component type
- Detect overlapping component bounding boxes (including minimum spacing of 96px / 6 grid units)
- For each collision pair, push apart along the axis of least overlap
- Iterate until no overlaps remain, max 50 iterations (guaranteed termination)

**Phase 4 — Compaction (new)**
- Compute centroid of all component positions
- Shift centroid toward sheet center
- Pull outlier components inward while maintaining minimum spacing
- Prevents sparse, spread-out layouts

**Phase 5 — Snap + clamp (same as today)**
- Snap all positions to 16px grid via `_snap()`
- Clamp within sheet bounds (32 to sheet_width-32, 32 to sheet_height-32)

### Interface (unchanged)

```python
def compute_layout(
    layout_desc: list[dict],
    component_sizes: dict[str, dict],  # now includes bounds from dictionary
    sheet_width: int = 880,
    sheet_height: int = 680
) -> dict[str, dict]:
    """Returns {instanceName: {"x": int, "y": int}}"""
```

### Prompt change: `layout_system.txt`

Minimal change — add explicit examples to reduce VLM hallucination:

```
You are describing the spatial layout of components in an LTspice schematic.

Describe positions using grid regions: top-left, top-center, top-right, center-left, center, center-right, bottom-left, bottom-center, bottom-right.

Describe relative positions between components using these directions ONLY: above, below, left, right, above-left, above-right, below-left, below-right.

Example output:
[
  {"instanceName": "V1", "region": "top-left", "nearby": []},
  {"instanceName": "R1", "region": "center-left", "nearby": [{"name": "V1", "direction": "below"}]},
  {"instanceName": "U1", "region": "center", "nearby": [{"name": "R1", "direction": "right"}]}
]

Output ONLY valid JSON. Do not include coordinates.
```

---

## Section 3: Wire Router Upgrade

Replace single L-route with obstacle-aware Manhattan routing and junction handling.

### Algorithm

**Step 1 — Resolve endpoints**
- For each connection, look up source and target component positions
- Look up pin offsets from dictionary, applying `normalize_pin()` first
- Compute absolute pin positions: `(comp.x + pin.x, comp.y + pin.y)`
- Log warning and skip if component or pin not found (should be rare after normalization)

**Step 2 — Route wires (improved Manhattan)**
- **Aligned pins** (share X or Y): single straight segment
- **Non-aligned pins**: try both L-route orientations:
  - Horizontal-first: `(src) -> (dst.x, src.y) -> (dst)`
  - Vertical-first: `(src) -> (src.x, dst.y) -> (dst)`
  - Score each by counting intersections with component bounding boxes
  - Pick the route with fewer obstacles
- **Obstacle detected on both L-routes**: add Z-route (3 segments). Compute the midpoint X (or Y) between source and target, offset it by 48px away from the nearest obstacle bounding box edge, and route: `src -> (mid, src.y) -> (mid, dst.y) -> dst` (horizontal detour) or the vertical equivalent

**Step 3 — Junction handling**
- After all wires routed, identify points where 3+ wire segment endpoints coincide — these are junctions (LTspice handles them automatically, no extra action)
- Wire segments that cross at non-endpoints are visual crossings only, NOT junctions — no action needed

**Step 4 — Ground and label placement (improved)**
- Grounds: add a 32px downward wire stub from pin, place `FLAG` at stub end with name `"0"`
- Labels: place `FLAG` at pin's absolute position with the label name

### Interface (extended)

```python
def compute_wires(
    components: dict,
    pin_defs: dict,
    connections_data: dict,
    component_bounds: dict = None  # NEW: bounding boxes for obstacle avoidance
) -> WireResult:
```

### Prompt change: `wires_system.txt`

Add explicit pin name guidance to reduce mismatch:

```
You are tracing wire connections in an LTspice schematic.

Wires are straight blue lines (horizontal or vertical) connecting component pins.
Ground connections are small downward-pointing triangles labeled "0".
Net labels are text at wire endpoints (like "OUT", "VCC").

Use these exact pin names:
- Resistor, Capacitor, Inductor: "A" (top/left pin), "B" (bottom/right pin)
- Voltage/Current Source: "+" (positive), "-" (negative)
- Diode, Zener: "+" (anode), "-" (cathode)
- NPN/PNP: "C" (collector), "B" (base), "E" (emitter)
- NMOS/PMOS: "D" (drain), "G" (gate), "S" (source)
- Op-Amp: "In+" (non-inverting), "In-" (inverting), "OUT" (output)
- Op-Amp 2-supply: "In+", "In-", "V+", "V-", "OUT"

Junction dots = true electrical connection.
Crossing lines without dots = NOT connected.

Example output:
{
  "connections": [
    {"from": {"component": "R1", "pin": "B"}, "to": {"component": "C1", "pin": "A"}}
  ],
  "grounds": [{"component": "V1", "pin": "-"}],
  "labels": [{"component": "U1", "pin": "OUT", "label": "OUT"}]
}

Output ONLY valid JSON.
```

---

## Section 4: Wizard State Flow & Error Handling

### Backend — wizard_routes.py

- Each endpoint wraps VLM output in Pydantic validation (Section 1)
- On Pydantic `ValidationError`: return `400` with `{"error": "...", "details": [...], "raw": "..."}`
- `/api/wizard/layout` passes component bounds from dictionary into `compute_layout()`
- `/api/wizard/wires` passes component bounds into `compute_wires()`
- Pin normalization applied in `/api/wizard/wires` before calling `compute_wires()`

### Frontend — GenerateWizard.tsx

- Each step gets a **retry button** on error. Re-sends the same request (VLM non-determinism means retries often work)
- Error display shows the backend's error message, not a generic "Something went wrong"
- If a call takes >30s, show "AI is still analyzing..." status text

### Frontend — api.ts

- Each wizard function checks for non-200 responses and throws with backend error message
- Existing function signatures stay the same

### What stays the same

- 4-step wizard flow: identify -> directives -> layout -> wires
- Incremental `onAdd*` callback pattern
- `useSchematic.ts`, `useHistory.ts` untouched
- `asc_generator.py` and `ascGenerator.ts` untouched
- `validator.py`, `ollama_client.py`, `routes.py` untouched

---

## Testing Strategy

- **schemas.py**: Unit tests for Pydantic validation — valid inputs, invalid inputs, edge cases (missing fields, wrong types, extra fields)
- **Pin normalization**: Unit tests for every component type's alias map + passthrough for canonical names
- **layout.py**: Update existing tests + add: collision resolution, multi-component same-region, constraint enforcement, compaction
- **wire_router.py**: Update existing tests + add: both L-route orientations, obstacle avoidance, ground stubs, junction detection
- **wizard_routes.py**: Update existing tests to verify 400 responses on malformed VLM output
- **End-to-end mock test**: Hardcode a known circuit as mock VLM responses, run full pipeline identify->directives->layout->wires->asc_generator, verify output is valid `.asc` that can be opened in LTspice

---

## Out of Scope

- Changing `asc_generator.py` — it works, just needs clean input
- Adding `networkx` or other external dependencies — pure Python only
- Changing the component dictionary schema
- SSE streaming (separate spec exists for that)
- SVG editor changes
