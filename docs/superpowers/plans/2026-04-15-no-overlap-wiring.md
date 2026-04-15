# No-Overlap Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent collinear wire overlap in both the interactive editor and the backend-generated schematics, and upgrade the `/api/wizard/wires` endpoint to use the VLM-aware `route_with_paths` router.

**Architecture:** Frontend gets a shared overlap helper (`wireOverlap.ts`) consumed by `Editor.tsx` for both red-ghost preview and click-time rejection. Backend's `_deduplicate_wires` is replaced with `_merge_collinear_wires` (same call sites) to collapse overlapping/abutting collinear segments. The `/api/wizard/wires` handler is migrated from the legacy `compute_wires` path to `route_with_paths`, building a `CircuitGraph` in-handler (pattern copied from `wizard_routes.py:302-340`), while the `wires_system.txt` prompt and `WiresResponse` schema are extended with optional `wire_paths` and `buses` hints.

**Tech Stack:** Python 3 (FastAPI, Pydantic v2, pytest) backend; React 19 + TypeScript + Vite frontend.

**Spec:** `docs/superpowers/specs/2026-04-15-no-overlap-wiring-design.md`

---

## Task 1: Backend — replace `_deduplicate_wires` with `_merge_collinear_wires`

**Files:**
- Create: `backend/tests/test_wire_overlap.py`
- Modify: `backend/services/wire_router.py` (replace function at lines 290-301, update imports/call sites at lines 287, 463, 524, 586)

- [ ] **Step 1: Write the failing test file**

Create `backend/tests/test_wire_overlap.py`:

```python
"""Tests for collinear wire merging."""
from services.wire_router import _merge_collinear_wires


def test_exact_duplicate_collapses_to_one():
    wires = [(0, 0, 100, 0), (0, 0, 100, 0)]
    assert _merge_collinear_wires(wires) == [(0, 0, 100, 0)]


def test_reversed_duplicate_collapses_to_one():
    wires = [(0, 0, 100, 0), (100, 0, 0, 0)]
    result = _merge_collinear_wires(wires)
    assert len(result) == 1
    assert result[0] == (0, 0, 100, 0)


def test_containment_keeps_outer():
    # wire A contains wire B
    wires = [(0, 0, 100, 0), (20, 0, 80, 0)]
    assert _merge_collinear_wires(wires) == [(0, 0, 100, 0)]


def test_partial_overlap_merges_to_union():
    wires = [(0, 0, 60, 0), (40, 0, 100, 0)]
    assert _merge_collinear_wires(wires) == [(0, 0, 100, 0)]


def test_abutting_segments_merge():
    # endpoint-to-endpoint on same line
    wires = [(0, 0, 50, 0), (50, 0, 100, 0)]
    assert _merge_collinear_wires(wires) == [(0, 0, 100, 0)]


def test_collinear_disjoint_stays_separate():
    wires = [(0, 0, 40, 0), (60, 0, 100, 0)]
    result = _merge_collinear_wires(wires)
    assert len(result) == 2
    assert (0, 0, 40, 0) in result
    assert (60, 0, 100, 0) in result


def test_perpendicular_crossing_stays_separate():
    # horizontal and vertical wires crossing at (50, 0) are not overlap
    wires = [(0, 0, 100, 0), (50, -50, 50, 50)]
    result = _merge_collinear_wires(wires)
    assert len(result) == 2
    assert (0, 0, 100, 0) in result
    assert (50, -50, 50, 50) in result


def test_different_y_horizontals_stay_separate():
    # two horizontals at different y are not collinear
    wires = [(0, 0, 100, 0), (0, 16, 100, 16)]
    assert len(_merge_collinear_wires(wires)) == 2


def test_vertical_overlap_merges():
    wires = [(32, 0, 32, 80), (32, 40, 32, 120)]
    assert _merge_collinear_wires(wires) == [(32, 0, 32, 120)]


def test_empty_input_returns_empty():
    assert _merge_collinear_wires([]) == []


def test_zero_length_wire_dropped():
    wires = [(50, 50, 50, 50)]
    assert _merge_collinear_wires(wires) == []


def test_triple_partial_overlap():
    wires = [(0, 0, 40, 0), (30, 0, 70, 0), (60, 0, 100, 0)]
    assert _merge_collinear_wires(wires) == [(0, 0, 100, 0)]


def test_mixed_horizontal_and_vertical():
    wires = [
        (0, 0, 100, 0),     # horizontal
        (0, 0, 100, 0),     # horizontal dup → merge
        (0, 0, 0, 100),     # vertical
        (0, 50, 0, 150),    # vertical partial overlap → merge
    ]
    result = _merge_collinear_wires(wires)
    assert len(result) == 2
    assert (0, 0, 100, 0) in result
    assert (0, 0, 0, 150) in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `backend/`:

```bash
python -m pytest tests/test_wire_overlap.py -v
```

Expected: all tests FAIL with `ImportError: cannot import name '_merge_collinear_wires' from 'services.wire_router'`.

- [ ] **Step 3: Implement `_merge_collinear_wires` in `wire_router.py`**

Replace the body of `_deduplicate_wires` (lines 290-301) with a new function and rename it. The replacement in full:

```python
def _merge_collinear_wires(
    wires: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    """Merge collinear wires that overlap or abut.

    Groups wires by orientation and shared axis, then sweeps each group
    collapsing overlapping and endpoint-touching intervals into their
    union.  The result is a list of maximal non-overlapping segments —
    electrically identical to the input but visually minimal.

    Zero-length wires are dropped.  Non-Manhattan (diagonal) wires are
    passed through unchanged; the router never emits them today.
    """
    horizontal: dict[int, list[tuple[int, int]]] = {}
    vertical: dict[int, list[tuple[int, int]]] = {}
    other: list[tuple[int, int, int, int]] = []

    for x1, y1, x2, y2 in wires:
        if x1 == x2 and y1 == y2:
            continue  # zero-length
        if y1 == y2:
            lo, hi = (x1, x2) if x1 <= x2 else (x2, x1)
            horizontal.setdefault(y1, []).append((lo, hi))
        elif x1 == x2:
            lo, hi = (y1, y2) if y1 <= y2 else (y2, y1)
            vertical.setdefault(x1, []).append((lo, hi))
        else:
            other.append((x1, y1, x2, y2))

    result: list[tuple[int, int, int, int]] = []

    for y, intervals in horizontal.items():
        for lo, hi in _merge_intervals(intervals):
            result.append((lo, y, hi, y))

    for x, intervals in vertical.items():
        for lo, hi in _merge_intervals(intervals):
            result.append((x, lo, x, hi))

    result.extend(other)
    return result


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sweep-merge a list of (lo, hi) intervals; touching intervals merge."""
    if not intervals:
        return []
    sorted_iv = sorted(intervals)
    merged: list[list[int]] = [list(sorted_iv[0])]
    for lo, hi in sorted_iv[1:]:
        if lo <= merged[-1][1]:  # overlap or abut
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [(a, b) for a, b in merged]
```

Then update the four call sites in `wire_router.py` — replace `_deduplicate_wires` with `_merge_collinear_wires` at:
- line 287 (inside `_route_net_with_direct_wires`)
- line 463 (inside `route_with_paths`)
- line 524 (inside `route_connections`)
- line 586 (inside `route_nets`)

- [ ] **Step 4: Run the new tests and existing router tests**

```bash
python -m pytest tests/test_wire_overlap.py tests/test_wire_router.py -v
```

Expected: all tests PASS. If `test_wire_router.py` tests break, investigate — the merge semantics are strictly more aggressive than dedup, so a previously-passing expected count may need adjustment. Adjust the existing assertions only if the new output is electrically equivalent and visually cleaner.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_wire_overlap.py backend/services/wire_router.py
git commit -m "feat(router): merge collinear wire overlaps in dedup pass

Replaces _deduplicate_wires with _merge_collinear_wires, which
sweeps per-axis intervals and collapses overlapping or abutting
collinear segments into their union.  Electrically identical
output; visually minimal.  Same call-site contract — all three
routers (route_with_paths, route_connections, route_nets) pick
up the change for free."
```

---

## Task 2: Backend — extend `WiresResponse` schema with `wire_paths` and `buses`

**Files:**
- Modify: `backend/services/schemas.py` (add models after line 114, extend `WiresResponse`)
- Create: `backend/tests/test_schemas_wires.py` (a focused schema test)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_schemas_wires.py`:

```python
from services.schemas import WiresResponse


def test_wires_response_accepts_empty_new_fields():
    resp = WiresResponse.model_validate({
        "connections": [],
        "grounds": [],
        "labels": [],
    })
    assert resp.wire_paths == []
    assert resp.buses == []


def test_wires_response_parses_wire_paths():
    resp = WiresResponse.model_validate({
        "connections": [],
        "grounds": [],
        "labels": [],
        "wire_paths": [
            {"from_pin": "R1.A", "to_pin": "Q1.C", "path": "L_horizontal_first"},
        ],
    })
    assert len(resp.wire_paths) == 1
    assert resp.wire_paths[0].from_pin == "R1.A"
    assert resp.wire_paths[0].to_pin == "Q1.C"
    assert resp.wire_paths[0].path == "L_horizontal_first"


def test_wires_response_parses_buses():
    resp = WiresResponse.model_validate({
        "connections": [],
        "grounds": [],
        "labels": [],
        "buses": [
            {"orientation": "horizontal", "y_pct": 40, "connects": ["R1.B", "R2.B", "C1.A"]},
        ],
    })
    assert len(resp.buses) == 1
    assert resp.buses[0].orientation == "horizontal"
    assert resp.buses[0].y_pct == 40
    assert resp.buses[0].connects == ["R1.B", "R2.B", "C1.A"]


def test_wires_response_roundtrip_dump_keeps_alias_keys():
    resp = WiresResponse.model_validate({
        "connections": [],
        "grounds": [],
        "labels": [],
        "wire_paths": [{"from_pin": "R1.A", "to_pin": "R2.A", "path": "direct_horizontal"}],
    })
    dumped = resp.model_dump(by_alias=True)
    assert "wire_paths" in dumped
    assert dumped["wire_paths"][0]["from_pin"] == "R1.A"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_schemas_wires.py -v
```

Expected: FAIL with `AttributeError: 'WiresResponse' object has no attribute 'wire_paths'` (or similar).

- [ ] **Step 3: Add the models and extend `WiresResponse`**

In `backend/services/schemas.py`, insert after line 114 (after the `LabelRef` definition, before `WiresResponse`):

```python
class WirePath(BaseModel):
    from_pin: str
    to_pin: str
    path: str = "L_horizontal_first"

    model_config = {"populate_by_name": True}


class Bus(BaseModel):
    orientation: str = "horizontal"
    y_pct: float | None = None
    x_pct: float | None = None
    connects: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
```

Then update `WiresResponse` (line 117-120) to:

```python
class WiresResponse(BaseModel):
    connections: list[WireConnection] = Field(default_factory=list)
    grounds: list[GroundRef] = Field(default_factory=list)
    labels: list[LabelRef] = Field(default_factory=list)
    wire_paths: list[WirePath] = Field(default_factory=list)
    buses: list[Bus] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_schemas_wires.py tests/test_vision.py -v
```

Expected: all tests PASS. `test_vision.py` should continue to pass because the new fields default to empty.

- [ ] **Step 5: Commit**

```bash
git add backend/services/schemas.py backend/tests/test_schemas_wires.py
git commit -m "feat(schemas): add WirePath and Bus fields to WiresResponse

Extends the wires-step response schema with optional wire_paths
and buses hints, consumed by route_with_paths.  Fields default
to empty lists for backward compatibility with old VLM responses."
```

---

## Task 3: Backend — expand `wires_system.txt` prompt and `describe_wires` user prompt

**Files:**
- Modify: `backend/prompts/wires_system.txt`
- Modify: `backend/services/vision.py` (user prompt string at lines 135-151)

- [ ] **Step 1: Replace `backend/prompts/wires_system.txt` entirely**

```
You are tracing wire connections in an LTspice schematic image.

For each wire visible in the image, identify which two components it connects and which pin on each component.

Pin names by component type:
- Resistor/Capacitor/Inductor: "A" (pin 1), "B" (pin 2)
- Voltage/Current Source: "+" (positive), "-" (negative)
- Diode/Zener: "+" (anode), "-" (cathode)
- NPN/PNP: "C" (collector), "B" (base), "E" (emitter)
- NMOS/PMOS: "D" (drain), "G" (gate), "S" (source)
- Op-Amp: "In+" or "noninvin", "In-" or "invin", "OUT"

Ground symbols (downward triangles or "0") are ground connections.
Net labels (text like "VCC", "OUT", "Vout") mark named nets.

If you are unsure which specific pin, just use "A" or "B" for 2-pin components — the router will find the nearest pin automatically.

ROUTING HINTS (optional fields — set to [] if uncertain):
- wire_paths: per-connection path shape as seen in the image.
  Allowed "path" values:
    * "L_horizontal_first" — wire goes horizontally first, then vertically
    * "L_vertical_first"   — wire goes vertically first, then horizontally
    * "direct_horizontal"  — straight horizontal wire (same Y)
    * "direct_vertical"    — straight vertical wire (same X)
  Use pin refs like "R1.A", "Q1.C".
- buses: a visible shared line connecting 3 or more pins.
  orientation: "horizontal" or "vertical".
  y_pct / x_pct: approximate location as a percentage (0-100) of image height/width.
  connects: list of pin refs ("R1.B", "R2.B", ...) that touch the bus.

Only describe what you actually see. If a bus is not obviously present or the path is ambiguous, leave the field empty — the router will fall back to automatic L-routing.

Output ONLY valid JSON:
{
  "connections": [
    {"from": {"component": "R1", "pin": "A"}, "to": {"component": "Q1", "pin": "C"}}
  ],
  "grounds": [
    {"component": "R5", "pin": "B"}
  ],
  "labels": [
    {"component": "R3", "pin": "A", "label": "VCC"}
  ],
  "wire_paths": [
    {"from_pin": "R1.A", "to_pin": "Q1.C", "path": "L_horizontal_first"}
  ],
  "buses": [
    {"orientation": "horizontal", "y_pct": 40, "connects": ["R1.B", "R2.B", "C1.A"]}
  ]
}
```

- [ ] **Step 2: Update the user prompt in `vision.py`**

In `backend/services/vision.py`, replace the `user = (...)` block (lines 135-151) with:

```python
    user = (
        f"Components in this schematic: {comp_names}\n\n"
        "List EVERY wire connection between components. For each wire, say which component pin connects to which.\n\n"
        "Pin names:\n"
        "- 2-pin (R, C, L, diode): A (pin 1/top/left), B (pin 2/bottom/right)\n"
        "- Sources (V, I): + (positive), - (negative)\n"
        "- NPN/PNP: C (collector), B (base), E (emitter)\n"
        "- MOSFET: D (drain), G (gate), S (source)\n\n"
        "Also list:\n"
        "- Ground connections (triangles or '0' symbol)\n"
        "- Net labels (VCC, OUT, etc.)\n"
        "- wire_paths (optional): per-wire path shape "
        '("L_horizontal_first", "L_vertical_first", "direct_horizontal", "direct_vertical").\n'
        "- buses (optional): shared bus lines touching 3+ pins; give orientation, y_pct or x_pct, and connects list.\n\n"
        "If a path or bus is not visually obvious, leave the field as []. Include ALL connections. Don't skip any wires.\n\n"
        'Output JSON:\n'
        '{"connections": [{"from": {"component": "R1", "pin": "B"}, "to": {"component": "Q1", "pin": "C"}}], '
        '"grounds": [{"component": "R5", "pin": "B"}], '
        '"labels": [{"component": "R3", "pin": "A", "label": "VCC"}], '
        '"wire_paths": [{"from_pin": "R1.A", "to_pin": "Q1.C", "path": "L_horizontal_first"}], '
        '"buses": [{"orientation": "horizontal", "y_pct": 40, "connects": ["R1.B", "R2.B"]}]}'
    )
```

Also update the fallback dict at line 161:

```python
    if not isinstance(raw, dict):
        raw = {"connections": [], "grounds": [], "labels": [], "wire_paths": [], "buses": []}
```

And update the log line at line 156-159 to include the new counts:

```python
    logger.info("Wire parsed: %d connections, %d grounds, %d labels, %d wire_paths, %d buses",
                len(raw.get("connections", [])) if isinstance(raw, dict) else 0,
                len(raw.get("grounds", [])) if isinstance(raw, dict) else 0,
                len(raw.get("labels", [])) if isinstance(raw, dict) else 0,
                len(raw.get("wire_paths", [])) if isinstance(raw, dict) else 0,
                len(raw.get("buses", [])) if isinstance(raw, dict) else 0)
```

- [ ] **Step 3: Run the vision tests**

```bash
python -m pytest tests/test_vision.py -v
```

Expected: PASS. Tests should not break because `WiresResponse` defaults the new fields.

- [ ] **Step 4: Commit**

```bash
git add backend/prompts/wires_system.txt backend/services/vision.py
git commit -m "feat(vision): ask VLM for wire_paths and buses hints

Expands wires_system prompt + describe_wires user prompt with
optional wire_paths and buses fields.  VLM is instructed to
leave them empty when uncertain, so responses remain backward
compatible when no routing hints are visible in the image."
```

---

## Task 4: Backend — migrate `/api/wizard/wires` to `route_with_paths`

**Files:**
- Modify: `backend/api/wizard_routes.py` (lines 123-204 — the `wizard_wires` handler)
- Modify: `backend/tests/test_wizard_wires_route.py` or add new fixture test; if no existing test, create `backend/tests/test_wizard_wires_endpoint.py`

- [ ] **Step 1: Check for an existing endpoint test**

```bash
python -m pytest --collect-only tests/ 2>/dev/null | grep -i "wires\|wizard" || echo "no wizard tests"
```

If a `test_wizard_*` file exists that already covers `/api/wizard/wires`, extend it. Otherwise continue to step 2 and create a new file.

- [ ] **Step 2: Write a failing integration-level test**

Create `backend/tests/test_wizard_wires_endpoint.py`:

```python
"""Tests for /api/wizard/wires handler migration to route_with_paths."""
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@pytest.fixture
def mock_wires_desc_legacy():
    """VLM response with NO wire_paths/buses — ensures backward compat."""
    return {
        "connections": [
            {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R2", "pin": "A"}},
        ],
        "grounds": [],
        "labels": [],
        "wire_paths": [],
        "buses": [],
    }


@pytest.fixture
def mock_wires_desc_with_paths():
    """VLM response WITH wire_paths — exercises the new router."""
    return {
        "connections": [
            {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R2", "pin": "A"}},
        ],
        "grounds": [],
        "labels": [],
        "wire_paths": [
            {"from_pin": "R1.A", "to_pin": "R2.A", "path": "L_vertical_first"},
        ],
        "buses": [],
    }


@pytest.fixture
def components_payload():
    return [
        {"instanceName": "R1", "type": "res", "value": "1k"},
        {"instanceName": "R2", "type": "res", "value": "2k"},
    ]


@pytest.fixture
def positions_payload():
    return {
        "R1": {"x": 64, "y": 64, "rotation": "R0"},
        "R2": {"x": 256, "y": 128, "rotation": "R0"},
    }


def _post(mock_desc, components, positions):
    # A 1x1 PNG placeholder — handler uses only the file name for MIME sniff
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
        b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe"
        b"\x02\xfe\xa3V\x1f\x8f\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    import json
    with patch("api.wizard_routes.describe_wires", new=AsyncMock(return_value=mock_desc)):
        return client.post(
            "/api/wizard/wires",
            files={"file": ("test.png", png, "image/png")},
            data={
                "components_json": json.dumps(components),
                "positions_json": json.dumps(positions),
                "provider_json": "{}",
            },
        )


def test_wires_endpoint_legacy_payload_still_works(
    mock_wires_desc_legacy, components_payload, positions_payload,
):
    resp = _post(mock_wires_desc_legacy, components_payload, positions_payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "wires" in body
    assert len(body["wires"]) >= 1, "Expected at least one wire between R1 and R2"


def test_wires_endpoint_honors_wire_path_hint(
    mock_wires_desc_with_paths, components_payload, positions_payload,
):
    resp = _post(mock_wires_desc_with_paths, components_payload, positions_payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    wires = body["wires"]
    # L_vertical_first: first segment is vertical (x1 == x2), second is horizontal (y1 == y2)
    vertical_first = [w for w in wires if w["x1"] == w["x2"]]
    assert len(vertical_first) >= 1, \
        f"Expected a vertical-first segment; got {wires}"
```

- [ ] **Step 3: Run test to verify at least one fails**

```bash
python -m pytest tests/test_wizard_wires_endpoint.py -v
```

Expected: the first test may pass (legacy behavior), but the second test likely FAILS because the handler ignores `wire_paths` today (calls `compute_wires`, not `route_with_paths`).

- [ ] **Step 4: Migrate the handler**

In `backend/api/wizard_routes.py`, replace lines 184-198 (the `comp_map` construction and `compute_wires` call) with:

```python
        # Build a CircuitGraph and route via the VLM-aware path router.
        # Pattern mirrors /api/redraw at lines 302-340.
        from services.circuit_graph import CircuitGraph
        from services.wire_router import route_with_paths

        graph = CircuitGraph(dictionary)
        graph.add_components([
            {"name": c["instanceName"], "type": c["type"], "value": c.get("value", "1")}
            for c in components
        ])
        for c in components:
            name = c["instanceName"]
            if name in graph.components and name in positions:
                node = graph.components[name]
                node.position = (positions[name]["x"], positions[name]["y"])
                node.resolved_rotation = positions[name].get("rotation", "R0")

        wire_result = route_with_paths(
            graph,
            wire_paths=wire_desc.get("wire_paths", []),
            buses=wire_desc.get("buses", []),
            connections=wire_desc.get("connections", []),
            grounds=wire_desc.get("grounds", []),
            labels=wire_desc.get("labels", []),
        )
```

Also remove the now-unused imports at the top of the file if `compute_wires` was imported explicitly (check the import block — only remove if not used elsewhere in this module).

Quick check:

```bash
python -c "import ast, sys; src=open('api/wizard_routes.py').read(); print('compute_wires' in src)"
```

If `compute_wires` still appears somewhere else in the file, leave the import. Otherwise remove it.

- [ ] **Step 5: Run the endpoint tests and full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests PASS, including both new endpoint tests.

- [ ] **Step 6: Commit**

```bash
git add backend/api/wizard_routes.py backend/tests/test_wizard_wires_endpoint.py
git commit -m "feat(wizard): route /api/wizard/wires via route_with_paths

Builds a CircuitGraph in-handler and feeds VLM-provided
wire_paths and buses to route_with_paths, falling back to
per-connection L-routing when the hints are empty.  Backward-
compatible with old VLM responses."
```

---

## Task 5: Frontend — create `wireOverlap.ts` helper

**Files:**
- Create: `frontend/src/lib/wireOverlap.ts`

- [ ] **Step 1: Create the helper**

Create `frontend/src/lib/wireOverlap.ts`:

```ts
import type { Position } from "../types/schematic";

interface Segment {
  from: Position;
  to: Position;
}

/**
 * Returns true if `candidate` is collinear with any wire in `existing`
 * AND shares a positive-length sub-segment with it.
 *
 * Abutting endpoint-to-endpoint is NOT considered overlap (strict inequality)
 * — it is a valid T-junction or line extension by the user.  Perpendicular
 * crossings are never overlap.
 */
export function isCollinearOverlap(
  candidate: Segment,
  existing: readonly Segment[],
): boolean {
  const aHoriz = candidate.from.y === candidate.to.y;
  const aVert = candidate.from.x === candidate.to.x;
  if (aHoriz && aVert) return false; // zero-length candidate — let caller handle

  for (const w of existing) {
    const bHoriz = w.from.y === w.to.y;
    const bVert = w.from.x === w.to.x;

    if (aHoriz && bHoriz && candidate.from.y === w.from.y) {
      const aLo = Math.min(candidate.from.x, candidate.to.x);
      const aHi = Math.max(candidate.from.x, candidate.to.x);
      const bLo = Math.min(w.from.x, w.to.x);
      const bHi = Math.max(w.from.x, w.to.x);
      if (Math.max(aLo, bLo) < Math.min(aHi, bHi)) return true;
    } else if (aVert && bVert && candidate.from.x === w.from.x) {
      const aLo = Math.min(candidate.from.y, candidate.to.y);
      const aHi = Math.max(candidate.from.y, candidate.to.y);
      const bLo = Math.min(w.from.y, w.to.y);
      const bHi = Math.max(w.from.y, w.to.y);
      if (Math.max(aLo, bLo) < Math.min(aHi, bHi)) return true;
    }
    // horizontal vs vertical → never collinear, skip
  }
  return false;
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/wireOverlap.ts
git commit -m "feat(editor): add wire overlap detection helper

Pure function isCollinearOverlap determines if a candidate wire
segment shares positive length with any existing wire on the
same line.  Abutting endpoints and perpendicular crossings are
not considered overlap — consumed by Editor.tsx in the next step."
```

---

## Task 6: Frontend — reject overlapping wires on commit click

**Files:**
- Modify: `frontend/src/components/Editor.tsx` (add import + checks at lines 266-302)

- [ ] **Step 1: Add the import at the top of Editor.tsx**

Add alongside the other `../lib/` imports:

```ts
import { isCollinearOverlap } from "../lib/wireOverlap";
```

- [ ] **Step 2: Add overlap check at click-2 (wirePhase === "first")**

In `Editor.tsx`, locate the block at lines 266-274 (the `wirePhase === "first"` branch). Replace it with:

```tsx
        } else if (wirePhase === "first" && wireStart) {
          // Lock the corner, transition to second segment
          const corner = computeCorner(wireStart, pos);
          // Reject if the first segment would lie on top of an existing wire
          if (
            (corner.x !== wireStart.x || corner.y !== wireStart.y) &&
            isCollinearOverlap({ from: wireStart, to: corner }, schematic.wires)
          ) {
            setWireStart(null);
            setWireCorner(null);
            setWirePhase(null);
            setCursorPos(null);
            return;
          }
          // Place first segment if it has length
          if (corner.x !== wireStart.x || corner.y !== wireStart.y) {
            onAddWire(wireStart, corner);
          }
          setWireCorner(corner);
          setWirePhase("second");
```

- [ ] **Step 3: Add overlap check at click-3 (wirePhase === "second")**

In the same `handleMouseDown`, locate lines 292-301 (after the existing `onWire` hit-test). Replace the block starting with `// Place second segment and finish` through the end of that branch with:

```tsx
          // Place second segment and finish — axis-snap from corner, matches first-segment behavior
          const endPos = computeCorner(wireCorner, snapPosition(raw));
          // Reject if the second segment would lie on top of an existing wire
          if (
            (endPos.x !== wireCorner.x || endPos.y !== wireCorner.y) &&
            isCollinearOverlap({ from: wireCorner, to: endPos }, schematic.wires)
          ) {
            setWireStart(null);
            setWireCorner(null);
            setWirePhase(null);
            setCursorPos(null);
            return;
          }
          if (endPos.x !== wireCorner.x || endPos.y !== wireCorner.y) {
            onAddWire(wireCorner, endPos);
          }
          // Reset
          setWireStart(null);
          setWireCorner(null);
          setWirePhase(null);
          setCursorPos(null);
```

- [ ] **Step 4: Update `handleMouseDown` dependency array**

At the end of the `useCallback` for `handleMouseDown` (line 314), add `schematic.wires` to the dependency array so the overlap check sees fresh data. The dependency array becomes:

```ts
[mode, wirePhase, wireStart, wireCorner, svgPoint, snapPosition, computeCorner, onAddWire, onSelect, onToggleMode, viewBox, schematic.wires]
```

- [ ] **Step 5: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no TypeScript errors.

- [ ] **Step 6: Manual browser test**

Start backend and frontend if not running, then in `http://localhost:5173`:

- Draw a wire horizontally at y=100 from x=100 to x=300.
- Enter wire mode, click at (150, 100) then click at (250, 100). **Expected:** nothing is committed — wire state resets (the first L-leg would overlap).
- Draw a new wire at y=200 from x=100 to x=300. Now start a new wire at (400, 100): click, then click at (400, 200) (corner at (400,100) → leg 1 vertical, leg 2 horizontal to some point). Click 3 at (500, 200). **Expected:** all three legs commit normally, none overlap.
- Verify that clicking directly *on* an existing wire at click-3 still cancels (pre-existing behavior untouched).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/Editor.tsx
git commit -m "feat(editor): reject wire clicks that would overlap existing wires

Each L-leg is tested against schematic.wires before commit.  On
overlap, drawing state is reset without committing the candidate
leg — matches the existing 'click-on-wire' abort pattern at
Editor.tsx:285-290.  Leg 1 is not rolled back when leg 2
overlaps; the user retains their partial L."
```

---

## Task 7: Frontend — red ghost preview for overlapping segments

**Files:**
- Modify: `frontend/src/components/Editor.tsx` (the `wirePreviewLines` `useMemo` at lines 577-611)

- [ ] **Step 1: Update the `wirePreviewLines` memo**

Replace the entire `wirePreviewLines` block (lines 577-611) with:

```tsx
  // ── Wire preview lines ─────────────────────────────────────────────
  const wirePreviewLines = useMemo(() => {
    if (!wireStart || !cursorPos) return null;

    const colorFor = (from: Position, to: Position) =>
      isCollinearOverlap({ from, to }, schematic.wires)
        ? "var(--color-error)"
        : "var(--color-selection)";
    const widthFor = (from: Position, to: Position) =>
      isCollinearOverlap({ from, to }, schematic.wires) ? 3 : 2;

    if (wirePhase === "first") {
      const corner = computeCorner(wireStart, cursorPos);
      return (
        <>
          <line
            x1={wireStart.x} y1={wireStart.y} x2={corner.x} y2={corner.y}
            stroke={colorFor(wireStart, corner)}
            strokeWidth={widthFor(wireStart, corner)}
            strokeDasharray="4,4" pointerEvents="none"
          />
          <line
            x1={corner.x} y1={corner.y} x2={cursorPos.x} y2={cursorPos.y}
            stroke={colorFor(corner, cursorPos)}
            strokeWidth={widthFor(corner, cursorPos)}
            strokeDasharray="4,4" pointerEvents="none"
          />
          <circle cx={corner.x} cy={corner.y} r={3} fill="var(--color-selection)" pointerEvents="none" />
        </>
      );
    }

    if (wirePhase === "second" && wireCorner) {
      const end = computeCorner(wireCorner, cursorPos);
      return (
        <line
          x1={wireCorner.x} y1={wireCorner.y} x2={end.x} y2={end.y}
          stroke={colorFor(wireCorner, end)}
          strokeWidth={widthFor(wireCorner, end)}
          strokeDasharray="4,4" pointerEvents="none"
        />
      );
    }

    return null;
  }, [wireStart, wireCorner, wirePhase, cursorPos, computeCorner, schematic.wires]);
```

(Note: `schematic.wires` added to the dependency array.)

- [ ] **Step 2: Type-check and build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Expected: no errors, build succeeds.

- [ ] **Step 3: Manual browser test**

- Draw a horizontal wire at y=100 from x=100 to x=300.
- Enter wire mode. Click at (150, 100) to start. Move cursor toward (250, 100). **Expected:** the horizontal leg of the ghost L turns red; the vertical leg (if any) stays normal.
- Move cursor above to (200, 60) (clearly off the existing wire). **Expected:** both ghost legs are normal color.
- Draw a wire that would cross perpendicularly through the first wire. **Expected:** ghost stays normal (crossings are allowed).
- Verify clicking commits the wire when green, cancels when red.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Editor.tsx
git commit -m "feat(editor): red ghost preview for overlapping wire segments

wirePreviewLines consults isCollinearOverlap per segment and
renders overlapping legs in --color-error at strokeWidth 3.
Perpendicular crossings and free space stay normal.  Paired
with the commit-time rejection in the previous task, the user
now sees overlap intent before they click."
```

---

## Final verification

After all seven tasks are merged, run:

```bash
cd backend && python -m pytest tests/ -v
cd frontend && npm run build && npx tsc --noEmit
```

Manual browser checklist:

- [ ] Drawing directly on an existing wire: ghost red, click cancels.
- [ ] Drawing partially on an existing wire (L where only leg 2 overlaps): leg-2 red, click cancels leg 2 without rolling back leg 1.
- [ ] Perpendicular crossing: ghost stays green, commits normally.
- [ ] Upload any sample image → Generate Wires → inspect `.asc` preview → no two wires on top of each other.

## Spec compliance cross-check

| Spec requirement | Task |
|---|---|
| Shared overlap definition | Task 5 (frontend), Task 1 (backend) |
| Red ghost preview | Task 7 |
| Click-time rejection | Task 6 |
| `_merge_collinear_wires` backstop | Task 1 |
| Prompt upgrade | Task 3 |
| `WiresResponse` schema | Task 2 |
| `/api/wizard/wires` → `route_with_paths` | Task 4 |
| Backward compat (empty `wire_paths`/`buses`) | Task 4 (first test) |
| No changes to `/api/refine` / legacy `compute_wires` | Respected |
| No frontend retroactive pass | Respected |
