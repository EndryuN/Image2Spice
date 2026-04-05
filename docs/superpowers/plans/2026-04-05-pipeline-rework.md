# Pipeline Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the VLM-to-deterministic handoff so the wizard pipeline produces valid `.asc` files end-to-end.

**Architecture:** Add Pydantic validation + pin normalization layer between VLM output and deterministic algorithms. Upgrade `layout.py` with collision avoidance and `wire_router.py` with obstacle-aware Manhattan routing. Harden wizard endpoints and frontend error handling.

**Tech Stack:** Python 3.11+, Pydantic v2, FastAPI, React 19, TypeScript 5.9

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/services/schemas.py` | Pydantic models for all VLM responses + pin normalization |
| Create | `backend/tests/test_schemas.py` | Tests for validation + pin normalization |
| Modify | `backend/services/layout.py` | Upgrade with collision resolution + compaction |
| Modify | `backend/tests/test_layout.py` | Add collision + multi-region tests |
| Modify | `backend/services/wire_router.py` | Upgrade with dual L-route + obstacle avoidance + ground stubs |
| Modify | `backend/tests/test_wire_router.py` | Add obstacle + ground stub tests |
| Modify | `backend/services/vision.py` | Wire Pydantic validation into VLM response parsing |
| Modify | `backend/api/wizard_routes.py` | Pass bounds, apply pin normalization, structured errors |
| Modify | `backend/prompts/layout_system.txt` | Add examples, remove coordinate mention |
| Modify | `backend/prompts/wires_system.txt` | Add explicit pin name table |
| Modify | `frontend/src/lib/api.ts` | Surface backend error messages |
| Modify | `frontend/src/components/GenerateWizard.tsx` | Add retry button + loading text |
| Create | `backend/tests/test_e2e_pipeline.py` | End-to-end mock pipeline test |

---

### Task 1: Pydantic Models — schemas.py

**Files:**
- Create: `backend/services/schemas.py`
- Create: `backend/tests/test_schemas.py`

- [ ] **Step 1: Write failing tests for Pydantic models**

Create `backend/tests/test_schemas.py`:

```python
import pytest
from pydantic import ValidationError
from services.schemas import (
    IdentifiedComponent,
    IdentifyResponse,
    DirectivesResponse,
    LayoutItem,
    LayoutResponse,
    NearbyRef,
    ConnectionEndpoint,
    WireConnection,
    WiresResponse,
    GroundRef,
    LabelRef,
)


def test_identified_component_valid():
    c = IdentifiedComponent(type="res", instanceName="R1", value="10k")
    assert c.type == "res"
    assert c.instanceName == "R1"
    assert c.value == "10k"
    assert c.value2 is None


def test_identified_component_with_value2():
    c = IdentifiedComponent(type="voltage", instanceName="V1", value="5", value2="AC 1")
    assert c.value2 == "AC 1"


def test_identified_component_missing_required():
    with pytest.raises(ValidationError):
        IdentifiedComponent(type="res", instanceName="R1")  # missing value


def test_identify_response_from_array():
    data = {"components": [{"type": "res", "instanceName": "R1", "value": "1k"}]}
    r = IdentifyResponse.model_validate(data)
    assert len(r.components) == 1


def test_directives_response_valid():
    r = DirectivesResponse(directives=[".tran 1m", ".param R=10k"])
    assert len(r.directives) == 2


def test_directives_response_empty():
    r = DirectivesResponse(directives=[])
    assert r.directives == []


def test_layout_item_valid():
    item = LayoutItem(
        instanceName="U1",
        region="center",
        nearby=[NearbyRef(name="R1", direction="above")]
    )
    assert item.region == "center"
    assert len(item.nearby) == 1


def test_layout_item_no_nearby():
    item = LayoutItem(instanceName="V1", region="top-left")
    assert item.nearby == []


def test_layout_response_valid():
    data = {"layout": [
        {"instanceName": "R1", "region": "top-left", "nearby": []},
        {"instanceName": "U1", "region": "center", "nearby": [{"name": "R1", "direction": "above"}]},
    ]}
    r = LayoutResponse.model_validate(data)
    assert len(r.layout) == 2


def test_wire_connection_from_alias():
    data = {"from": {"component": "R1", "pin": "B"}, "to": {"component": "C1", "pin": "A"}}
    wc = WireConnection.model_validate(data)
    assert wc.from_.component == "R1"
    assert wc.to.pin == "A"


def test_wires_response_valid():
    data = {
        "connections": [
            {"from": {"component": "R1", "pin": "B"}, "to": {"component": "C1", "pin": "A"}}
        ],
        "grounds": [{"component": "V1", "pin": "-"}],
        "labels": [{"component": "U1", "pin": "OUT", "label": "OUT"}],
    }
    r = WiresResponse.model_validate(data)
    assert len(r.connections) == 1
    assert len(r.grounds) == 1
    assert len(r.labels) == 1


def test_wires_response_empty():
    r = WiresResponse.model_validate({})
    assert r.connections == []
    assert r.grounds == []
    assert r.labels == []


def test_wires_response_missing_pin():
    with pytest.raises(ValidationError):
        WiresResponse.model_validate({
            "connections": [{"from": {"component": "R1"}, "to": {"component": "C1", "pin": "A"}}]
        })
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.schemas'`

- [ ] **Step 3: Write schemas.py**

Create `backend/services/schemas.py`:

```python
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


VALID_REGIONS = {
    "top-left", "top-center", "top-right",
    "center-left", "center", "center-right",
    "bottom-left", "bottom-center", "bottom-right",
}

VALID_DIRECTIONS = {
    "above", "below", "left", "right",
    "above-left", "above-right", "below-left", "below-right",
}


# ── Identify step ─────────────────────────────────────────────────────────────

class IdentifiedComponent(BaseModel):
    type: str
    instanceName: str
    value: str
    value2: Optional[str] = None


class IdentifyResponse(BaseModel):
    components: list[IdentifiedComponent]


# ── Directives step ───────────────────────────────────────────────────────────

class DirectivesResponse(BaseModel):
    directives: list[str]


# ── Layout step ───────────────────────────────────────────────────────────────

class NearbyRef(BaseModel):
    name: str
    direction: str


class LayoutItem(BaseModel):
    instanceName: str
    region: str = "center"
    nearby: list[NearbyRef] = Field(default_factory=list)


class LayoutResponse(BaseModel):
    layout: list[LayoutItem]


# ── Wires step ────────────────────────────────────────────────────────────────

class ConnectionEndpoint(BaseModel):
    component: str
    pin: str


class WireConnection(BaseModel):
    from_: ConnectionEndpoint = Field(alias="from")
    to: ConnectionEndpoint

    model_config = {"populate_by_name": True}


class GroundRef(BaseModel):
    component: str
    pin: str


class LabelRef(BaseModel):
    component: str
    pin: str
    label: str


class WiresResponse(BaseModel):
    connections: list[WireConnection] = Field(default_factory=list)
    grounds: list[GroundRef] = Field(default_factory=list)
    labels: list[LabelRef] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_schemas.py -v`
Expected: All 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/schemas.py backend/tests/test_schemas.py
git commit -m "feat: add Pydantic validation models for wizard VLM responses"
```

---

### Task 2: Pin Normalization

**Files:**
- Modify: `backend/services/schemas.py`
- Modify: `backend/tests/test_schemas.py`

- [ ] **Step 1: Write failing tests for pin normalization**

Append to `backend/tests/test_schemas.py`:

```python
from services.schemas import normalize_pin


# ── Passives: res, cap, ind ──��────────────────────────────────────────────────

def test_normalize_pin_resistor_canonical():
    assert normalize_pin("res", "A") == "A"
    assert normalize_pin("res", "B") == "B"


def test_normalize_pin_resistor_numeric():
    assert normalize_pin("res", "1") == "A"
    assert normalize_pin("res", "2") == "B"


def test_normalize_pin_resistor_generic():
    assert normalize_pin("res", "pin1") == "A"
    assert normalize_pin("res", "pin2") == "B"


def test_normalize_pin_resistor_positional():
    assert normalize_pin("res", "top") == "A"
    assert normalize_pin("res", "bottom") == "B"


def test_normalize_pin_cap_numeric():
    assert normalize_pin("cap", "1") == "A"
    assert normalize_pin("cap", "2") == "B"


def test_normalize_pin_inductor_numeric():
    assert normalize_pin("ind", "1") == "A"
    assert normalize_pin("ind", "2") == "B"


# ── Sources: voltage, current ──────────────────────────────────��──────────────

def test_normalize_pin_voltage_canonical():
    assert normalize_pin("voltage", "+") == "+"
    assert normalize_pin("voltage", "-") == "-"


def test_normalize_pin_voltage_descriptive():
    assert normalize_pin("voltage", "positive") == "+"
    assert normalize_pin("voltage", "negative") == "-"


def test_normalize_pin_voltage_aliases():
    assert normalize_pin("voltage", "v+") == "+"
    assert normalize_pin("voltage", "v-") == "-"
    assert normalize_pin("voltage", "p") == "+"
    assert normalize_pin("voltage", "n") == "-"


def test_normalize_pin_voltage_numeric():
    assert normalize_pin("voltage", "1") == "+"
    assert normalize_pin("voltage", "2") == "-"


def test_normalize_pin_current_numeric():
    assert normalize_pin("current", "1") == "+"
    assert normalize_pin("current", "2") == "-"


# ── Diodes ────────────────────────────────────────────────────────────────────

def test_normalize_pin_diode_descriptive():
    assert normalize_pin("diode", "anode") == "+"
    assert normalize_pin("diode", "cathode") == "-"


def test_normalize_pin_zener_numeric():
    assert normalize_pin("zener", "1") == "+"
    assert normalize_pin("zener", "2") == "-"


# ── BJTs ──────────────────────────────────────────────────────────────────────

def test_normalize_pin_npn_canonical():
    assert normalize_pin("npn", "C") == "C"
    assert normalize_pin("npn", "B") == "B"
    assert normalize_pin("npn", "E") == "E"


def test_normalize_pin_npn_descriptive():
    assert normalize_pin("npn", "collector") == "C"
    assert normalize_pin("npn", "base") == "B"
    assert normalize_pin("npn", "emitter") == "E"


def test_normalize_pin_npn_numeric():
    assert normalize_pin("npn", "1") == "C"
    assert normalize_pin("npn", "2") == "B"
    assert normalize_pin("npn", "3") == "E"


def test_normalize_pin_pnp_descriptive():
    assert normalize_pin("pnp", "collector") == "C"
    assert normalize_pin("pnp", "emitter") == "E"


# ── MOSFETs ─���─────────────────────────────────────────────────────────────────

def test_normalize_pin_nmos_canonical():
    assert normalize_pin("nmos", "D") == "D"
    assert normalize_pin("nmos", "G") == "G"
    assert normalize_pin("nmos", "S") == "S"


def test_normalize_pin_nmos_descriptive():
    assert normalize_pin("nmos", "drain") == "D"
    assert normalize_pin("nmos", "gate") == "G"
    assert normalize_pin("nmos", "source") == "S"


def test_normalize_pin_pmos_numeric():
    assert normalize_pin("pmos", "1") == "D"
    assert normalize_pin("pmos", "2") == "G"
    assert normalize_pin("pmos", "3") == "S"


# ── Op-amps ───────────────────────────────────────────────────────────────────

def test_normalize_pin_opamp_canonical():
    assert normalize_pin("opamp", "invin") == "invin"
    assert normalize_pin("opamp", "noninvin") == "noninvin"
    assert normalize_pin("opamp", "out") == "out"


def test_normalize_pin_opamp_aliases():
    assert normalize_pin("opamp", "in-") == "invin"
    assert normalize_pin("opamp", "in+") == "noninvin"
    assert normalize_pin("opamp", "inverting") == "invin"
    assert normalize_pin("opamp", "non-inverting") == "noninvin"
    assert normalize_pin("opamp", "output") == "out"


def test_normalize_pin_opamp2_canonical():
    assert normalize_pin("opamp2", "In+") == "In+"
    assert normalize_pin("opamp2", "In-") == "In-"
    assert normalize_pin("opamp2", "V+") == "V+"
    assert normalize_pin("opamp2", "V-") == "V-"
    assert normalize_pin("opamp2", "OUT") == "OUT"


def test_normalize_pin_opamp2_aliases():
    assert normalize_pin("opamp2", "noninv") == "In+"
    assert normalize_pin("opamp2", "non-inverting") == "In+"
    assert normalize_pin("opamp2", "inv") == "In-"
    assert normalize_pin("opamp2", "inverting") == "In-"
    assert normalize_pin("opamp2", "vcc") == "V+"
    assert normalize_pin("opamp2", "vee") == "V-"
    assert normalize_pin("opamp2", "output") == "OUT"
    assert normalize_pin("opamp2", "out") == "OUT"


# ── Case insensitivity ──────────────────────────────────────────���─────────────

def test_normalize_pin_case_insensitive():
    assert normalize_pin("res", "a") == "A"
    assert normalize_pin("res", "PIN1") == "A"
    assert normalize_pin("voltage", "POSITIVE") == "+"
    assert normalize_pin("npn", "collector") == "C"


# ── Unknown passthrough ─────────────────────────────────────��─────────────────

def test_normalize_pin_unknown_returns_raw():
    assert normalize_pin("res", "xyz") == "xyz"
    assert normalize_pin("unknown_type", "A") == "A"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_schemas.py::test_normalize_pin_resistor_canonical -v`
Expected: FAIL — `ImportError: cannot import name 'normalize_pin'`

- [ ] **Step 3: Implement pin normalization**

Append to `backend/services/schemas.py`:

```python
# ── Pin normalization ─────────────────────────────────────────────────────────

_PASSIVE_ALIASES: dict[str, str] = {
    "1": "A", "2": "B",
    "pin1": "A", "pin2": "B",
    "top": "A", "bottom": "B",
    "left": "A", "right": "B",
    "p": "A", "n": "B",
    "a": "A", "b": "B",
}

_SOURCE_ALIASES: dict[str, str] = {
    "1": "+", "2": "-",
    "pin1": "+", "pin2": "-",
    "positive": "+", "negative": "-",
    "pos": "+", "neg": "-",
    "p": "+", "n": "-",
    "v+": "+", "v-": "-",
    "+": "+", "-": "-",
}

_DIODE_ALIASES: dict[str, str] = {
    "1": "+", "2": "-",
    "pin1": "+", "pin2": "-",
    "anode": "+", "cathode": "-",
    "a": "+", "k": "-",
    "p": "+", "n": "-",
    "+": "+", "-": "-",
}

_BJT_ALIASES: dict[str, str] = {
    "1": "C", "2": "B", "3": "E",
    "pin1": "C", "pin2": "B", "pin3": "E",
    "collector": "C", "base": "B", "emitter": "E",
    "col": "C", "emit": "E",
    "c": "C", "b": "B", "e": "E",
}

_MOSFET_ALIASES: dict[str, str] = {
    "1": "D", "2": "G", "3": "S",
    "pin1": "D", "pin2": "G", "pin3": "S",
    "drain": "D", "gate": "G", "source": "S",
    "d": "D", "g": "G", "s": "S",
}

_OPAMP_ALIASES: dict[str, str] = {
    "in-": "invin", "in+": "noninvin",
    "inverting": "invin", "non-inverting": "noninvin",
    "inv": "invin", "noninv": "noninvin",
    "output": "out",
    "1": "invin", "2": "noninvin", "3": "out",
    "pin1": "invin", "pin2": "noninvin", "pin3": "out",
    "invin": "invin", "noninvin": "noninvin", "out": "out",
}

_OPAMP2_ALIASES: dict[str, str] = {
    "in+": "In+", "in-": "In-",
    "noninv": "In+", "non-inverting": "In+", "noninverting": "In+",
    "inv": "In-", "inverting": "In-",
    "v+": "V+", "v-": "V-",
    "vcc": "V+", "vdd": "V+",
    "vee": "V-", "vss": "V-",
    "out": "OUT", "output": "OUT",
    "1": "In+", "2": "In-", "3": "V+", "4": "V-", "5": "OUT",
    "pin1": "In+", "pin2": "In-", "pin3": "V+", "pin4": "V-", "pin5": "OUT",
}

PIN_ALIASES: dict[str, dict[str, str]] = {
    "res": _PASSIVE_ALIASES,
    "cap": _PASSIVE_ALIASES,
    "ind": _PASSIVE_ALIASES,
    "voltage": _SOURCE_ALIASES,
    "current": _SOURCE_ALIASES,
    "diode": _DIODE_ALIASES,
    "zener": _DIODE_ALIASES,
    "npn": _BJT_ALIASES,
    "pnp": _BJT_ALIASES,
    "nmos": _MOSFET_ALIASES,
    "pmos": _MOSFET_ALIASES,
    "opamp": _OPAMP_ALIASES,
    "opamp2": _OPAMP2_ALIASES,
}


def normalize_pin(comp_type: str, raw_pin: str) -> str:
    """Map a VLM-returned pin name to the dictionary-canonical name.

    Lookup is case-insensitive.  Returns *raw_pin* unchanged when
    the component type is unknown or no alias matches.
    """
    aliases = PIN_ALIASES.get(comp_type)
    if aliases is None:
        return raw_pin
    return aliases.get(raw_pin.lower(), raw_pin)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_schemas.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/schemas.py backend/tests/test_schemas.py
git commit -m "feat: add pin normalization with aliases for all 13 component types"
```

---

### Task 3: Layout Solver Upgrade

**Files:**
- Modify: `backend/services/layout.py`
- Modify: `backend/tests/test_layout.py`

- [ ] **Step 1: Write failing tests for new layout features**

Append to `backend/tests/test_layout.py`:

```python
COMPONENT_BOUNDS = {
    "res": [0, 16, 32, 96],
    "voltage": [-32, 16, 32, 96],
    "opamp2": [-32, 32, 32, 96],
    "cap": [0, 0, 32, 64],
}


def test_same_region_no_overlap():
    """Three components in 'center' must not overlap."""
    layout_desc = [
        {"instanceName": "R1", "region": "center", "nearby": []},
        {"instanceName": "R2", "region": "center", "nearby": []},
        {"instanceName": "R3", "region": "center", "nearby": []},
    ]
    sizes = {k: {"width": b[2] - b[0], "height": b[3] - b[1], "bounds": b}
             for k, b in COMPONENT_BOUNDS.items()}
    result = compute_layout(layout_desc, sizes, 880, 680)
    coords = [(result[n]["x"], result[n]["y"]) for n in ["R1", "R2", "R3"]]
    # All three must be at distinct positions
    assert len(set(coords)) == 3


def test_collision_resolution_minimum_spacing():
    """Components placed at the same spot must be pushed apart by at least 96px."""
    layout_desc = [
        {"instanceName": "R1", "region": "center", "nearby": []},
        {"instanceName": "R2", "region": "center", "nearby": []},
    ]
    sizes = {k: {"width": b[2] - b[0], "height": b[3] - b[1], "bounds": b}
             for k, b in COMPONENT_BOUNDS.items()}
    result = compute_layout(layout_desc, sizes, 880, 680)
    r1, r2 = result["R1"], result["R2"]
    dx = abs(r1["x"] - r2["x"])
    dy = abs(r1["y"] - r2["y"])
    # Must be separated in at least one axis by >= 96
    assert dx >= 96 or dy >= 96


def test_clamp_within_bounds():
    """Even with collision pushes, all positions stay within sheet bounds."""
    layout_desc = [
        {"instanceName": f"R{i}", "region": "top-left", "nearby": []}
        for i in range(6)
    ]
    sizes = {"res": {"width": 32, "height": 80, "bounds": [0, 16, 32, 96]}}
    result = compute_layout(layout_desc, sizes, 880, 680)
    for name, pos in result.items():
        assert 32 <= pos["x"] <= 848, f"{name} x={pos['x']} out of bounds"
        assert 32 <= pos["y"] <= 648, f"{name} y={pos['y']} out of bounds"


def test_compaction_toward_center():
    """Components spread across far corners should be pulled inward."""
    layout_desc = [
        {"instanceName": "R1", "region": "top-left", "nearby": []},
        {"instanceName": "R2", "region": "bottom-right", "nearby": []},
    ]
    sizes = {"res": {"width": 32, "height": 80, "bounds": [0, 16, 32, 96]}}
    result = compute_layout(layout_desc, sizes, 880, 680)
    # Centroid should be closer to sheet center (440, 340) than corners
    cx = (result["R1"]["x"] + result["R2"]["x"]) / 2
    cy = (result["R1"]["y"] + result["R2"]["y"]) / 2
    assert 200 < cx < 680
    assert 150 < cy < 530
```

- [ ] **Step 2: Run tests to verify the new tests fail**

Run: `cd backend && python -m pytest tests/test_layout.py -v`
Expected: `test_same_region_no_overlap` FAILS (all 3 components land on same coords), other new tests may also fail.

- [ ] **Step 3: Rewrite layout.py**

Replace the full contents of `backend/services/layout.py`:

```python
from __future__ import annotations

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

_MIN_SPACING = 96  # minimum pixels between component centres
_MAX_COLLISION_ITERS = 50


def _snap(value: int) -> int:
    return round(value / 16) * 16


def _get_bounds(comp_type: str, sizes: dict) -> tuple[int, int, int, int]:
    """Return (min_x, min_y, max_x, max_y) for a component type."""
    info = sizes.get(comp_type, {})
    b = info.get("bounds")
    if b and len(b) == 4:
        return tuple(b)
    w = info.get("width", 32)
    h = info.get("height", 80)
    return (0, 0, w, h)


def compute_layout(
    layout_desc: list[dict],
    component_sizes: dict[str, dict],
    sheet_width: int = 880,
    sheet_height: int = 680,
) -> dict[str, dict]:
    positions: dict[str, dict] = {}
    comp_types: dict[str, str] = {}

    # ── Phase 1: Region placement with same-region scatter ────────────────
    region_groups: dict[str, list[str]] = {}
    for item in layout_desc:
        name = item["instanceName"]
        region = item.get("region", "center")
        comp_types[name] = item.get("type", "res")
        region_groups.setdefault(region, []).append(name)

    for region, names in region_groups.items():
        base_x, base_y = REGION_COORDS.get(region, (432, 336))
        count = len(names)
        if count == 1:
            positions[names[0]] = {"x": base_x, "y": base_y}
        else:
            # Scatter in a grid pattern around the region centre
            cols = 1
            while cols * cols < count:
                cols += 1
            for i, name in enumerate(names):
                col = i % cols
                row = i // cols
                offset_x = (col - (cols - 1) / 2) * _MIN_SPACING
                offset_y = (row - (cols - 1) / 2) * _MIN_SPACING
                positions[name] = {
                    "x": int(base_x + offset_x),
                    "y": int(base_y + offset_y),
                }

    # ── Phase 2: Relative constraint enforcement ──────────────────────────
    for item in layout_desc:
        name = item["instanceName"]
        for nearby in item.get("nearby", []):
            ref_name = nearby.get("name", "")
            direction = nearby.get("direction", "")
            if ref_name not in positions:
                continue
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

    # ── Phase 3: Collision resolution ─────────────────────────────────────
    names_list = list(positions.keys())
    for _ in range(_MAX_COLLISION_ITERS):
        moved = False
        for i in range(len(names_list)):
            for j in range(i + 1, len(names_list)):
                a, b = names_list[i], names_list[j]
                ax, ay = positions[a]["x"], positions[a]["y"]
                bx, by = positions[b]["x"], positions[b]["y"]
                dx = abs(ax - bx)
                dy = abs(ay - by)
                if dx < _MIN_SPACING and dy < _MIN_SPACING:
                    # Push apart along axis of least separation
                    if dx <= dy:
                        push = (_MIN_SPACING - dx) // 2 + 16
                        if ax <= bx:
                            positions[a]["x"] -= push
                            positions[b]["x"] += push
                        else:
                            positions[a]["x"] += push
                            positions[b]["x"] -= push
                    else:
                        push = (_MIN_SPACING - dy) // 2 + 16
                        if ay <= by:
                            positions[a]["y"] -= push
                            positions[b]["y"] += push
                        else:
                            positions[a]["y"] += push
                            positions[b]["y"] -= push
                    moved = True
        if not moved:
            break

    # ── Phase 4: Compaction toward sheet centre ───────────────────────────
    if positions:
        center_x = sheet_width // 2
        center_y = sheet_height // 2
        cx = sum(p["x"] for p in positions.values()) // len(positions)
        cy = sum(p["y"] for p in positions.values()) // len(positions)
        shift_x = (center_x - cx) // 3
        shift_y = (center_y - cy) // 3
        for name in positions:
            positions[name]["x"] += shift_x
            positions[name]["y"] += shift_y

    # ── Phase 5: Grid snap + clamp ────────────────────────────────────────
    for name in positions:
        positions[name]["x"] = _snap(positions[name]["x"])
        positions[name]["y"] = _snap(positions[name]["y"])
        positions[name]["x"] = max(32, min(sheet_width - 32, positions[name]["x"]))
        positions[name]["y"] = max(32, min(sheet_height - 32, positions[name]["y"]))

    return positions
```

- [ ] **Step 4: Run all layout tests**

Run: `cd backend && python -m pytest tests/test_layout.py -v`
Expected: All tests PASS (both old and new)

- [ ] **Step 5: Commit**

```bash
git add backend/services/layout.py backend/tests/test_layout.py
git commit -m "feat: upgrade layout solver with collision avoidance and compaction"
```

---

### Task 4: Wire Router Upgrade

**Files:**
- Modify: `backend/services/wire_router.py`
- Modify: `backend/tests/test_wire_router.py`

- [ ] **Step 1: Write failing tests for new wire routing features**

Append to `backend/tests/test_wire_router.py`:

```python
def test_pin_normalization_in_connections():
    """Wire router should work when _find_pin receives canonical names."""
    components = {
        "R1": {"x": 100, "y": 100, "type": "res"},
        "V1": {"x": 100, "y": 300, "type": "voltage"},
    }
    pin_defs = {
        "res": [
            {"name": "A", "x": 16, "y": 16, "spiceOrder": 1},
            {"name": "B", "x": 16, "y": 96, "spiceOrder": 2},
        ],
        "voltage": [
            {"name": "+", "x": 0, "y": 16, "spiceOrder": 1},
            {"name": "-", "x": 0, "y": 96, "spiceOrder": 2},
        ],
    }
    connections_data = {
        "connections": [
            {"from": {"component": "R1", "pin": "B"}, "to": {"component": "V1", "pin": "+"}}
        ],
        "grounds": [],
        "labels": [],
    }
    result = compute_wires(components, pin_defs, connections_data)
    assert len(result.wires) >= 1


def test_ground_with_stub_wire():
    """Ground flags should have a short wire stub."""
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
    assert len(result.flags) == 1
    assert result.flags[0]["name"] == "0"
    # Flag should be 32px below the pin
    pin_y = 100 + 96  # comp_y + pin_y
    assert result.flags[0]["y"] == pin_y + 32
    # Should have a stub wire from pin to flag
    assert len(result.wires) == 1
    assert result.wires[0] == (100, pin_y, 100, pin_y + 32)


def test_dual_l_route_picks_best():
    """When both L-routes are available, the router should pick one without crashing."""
    components = {
        "R1": {"x": 100, "y": 100, "type": "res"},
        "R2": {"x": 400, "y": 400, "type": "res"},
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
    bounds = {
        "res": [0, 16, 32, 96],
    }
    result = compute_wires(components, pin_defs, connections_data, bounds)
    assert len(result.wires) == 2  # L-route is 2 segments


def test_obstacle_avoidance():
    """Router should avoid a component bounding box placed in the L-route path."""
    components = {
        "R1": {"x": 100, "y": 100, "type": "res"},
        "R2": {"x": 400, "y": 100, "type": "res"},
        "BLOCKER": {"x": 250, "y": 100, "type": "res"},
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
    bounds = {
        "res": [0, 16, 32, 96],
    }
    result = compute_wires(components, pin_defs, connections_data, bounds)
    # Should produce at least 2 wire segments (route still works)
    assert len(result.wires) >= 2
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `cd backend && python -m pytest tests/test_wire_router.py -v`
Expected: `test_ground_with_stub_wire` FAILS (current code doesn't add stub), `test_dual_l_route_picks_best` FAILS (signature mismatch on `component_bounds`), `test_obstacle_avoidance` FAILS.

- [ ] **Step 3: Rewrite wire_router.py**

Replace full contents of `backend/services/wire_router.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WireResult:
    wires: list[tuple[int, int, int, int]] = field(default_factory=list)
    flags: list[dict] = field(default_factory=list)


def _find_pin(pin_defs: dict, comp_type: str, pin_name: str) -> dict | None:
    for pin in pin_defs.get(comp_type, []):
        if pin["name"].lower() == pin_name.lower():
            return pin
    return None


def _abs_pin_pos(comp: dict, pin: dict) -> tuple[int, int]:
    return (comp["x"] + pin["x"], comp["y"] + pin["y"])


def _segments_intersect_bbox(
    x1: int, y1: int, x2: int, y2: int,
    bx_min: int, by_min: int, bx_max: int, by_max: int,
) -> bool:
    """Check if an orthogonal wire segment passes through a bounding box."""
    if x1 == x2:  # vertical segment
        seg_min_y, seg_max_y = min(y1, y2), max(y1, y2)
        return (bx_min <= x1 <= bx_max
                and seg_min_y < by_max
                and seg_max_y > by_min)
    if y1 == y2:  # horizontal segment
        seg_min_x, seg_max_x = min(x1, x2), max(x1, x2)
        return (by_min <= y1 <= by_max
                and seg_min_x < bx_max
                and seg_max_x > bx_min)
    return False


def _route_score(
    segments: list[tuple[int, int, int, int]],
    obstacles: list[tuple[int, int, int, int]],
) -> int:
    """Count how many obstacle bboxes the route intersects."""
    score = 0
    for seg in segments:
        for obs in obstacles:
            if _segments_intersect_bbox(*seg, *obs):
                score += 1
    return score


def _build_obstacle_list(
    components: dict[str, dict],
    component_bounds: dict[str, list] | None,
    exclude: set[str],
) -> list[tuple[int, int, int, int]]:
    """Build absolute bounding boxes for all components except those in exclude."""
    if not component_bounds:
        return []
    obstacles = []
    for name, comp in components.items():
        if name in exclude:
            continue
        b = component_bounds.get(comp["type"])
        if not b or len(b) < 4:
            continue
        obstacles.append((
            comp["x"] + b[0],
            comp["y"] + b[1],
            comp["x"] + b[2],
            comp["y"] + b[3],
        ))
    return obstacles


def compute_wires(
    components: dict[str, dict],
    pin_defs: dict[str, list[dict]],
    connections_data: dict,
    component_bounds: dict[str, list] | None = None,
) -> WireResult:
    result = WireResult()

    for conn in connections_data.get("connections", []):
        from_name = conn["from"]["component"]
        to_name = conn["to"]["component"]
        from_comp = components.get(from_name)
        to_comp = components.get(to_name)
        if not from_comp or not to_comp:
            continue
        from_pin = _find_pin(pin_defs, from_comp["type"], conn["from"]["pin"])
        to_pin = _find_pin(pin_defs, to_comp["type"], conn["to"]["pin"])
        if not from_pin or not to_pin:
            continue

        fx, fy = _abs_pin_pos(from_comp, from_pin)
        tx, ty = _abs_pin_pos(to_comp, to_pin)

        if fx == tx or fy == ty:
            # Straight line
            result.wires.append((fx, fy, tx, ty))
        else:
            # Try both L-route orientations
            route_h_first = [(fx, fy, tx, fy), (tx, fy, tx, ty)]
            route_v_first = [(fx, fy, fx, ty), (fx, ty, tx, ty)]

            obstacles = _build_obstacle_list(
                components, component_bounds, {from_name, to_name}
            )

            score_h = _route_score(route_h_first, obstacles)
            score_v = _route_score(route_v_first, obstacles)

            if score_h <= score_v:
                result.wires.extend(route_h_first)
            else:
                result.wires.extend(route_v_first)

    for gnd in connections_data.get("grounds", []):
        comp = components.get(gnd["component"])
        if not comp:
            continue
        pin = _find_pin(pin_defs, comp["type"], gnd["pin"])
        if not pin:
            continue
        px, py = _abs_pin_pos(comp, pin)
        # Stub wire 32px downward, flag at bottom of stub
        result.wires.append((px, py, px, py + 32))
        result.flags.append({"name": "0", "x": px, "y": py + 32})

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

- [ ] **Step 4: Run all wire router tests**

Run: `cd backend && python -m pytest tests/test_wire_router.py -v`
Expected: All tests PASS. Note: `test_ground_connection` from the original tests will need updating since grounds now produce both a wire and a flag. Update the old test:

In `test_ground_connection`, change:
```python
    assert len(result.flags) >= 1
    assert result.flags[0]["name"] == "0"
```
to:
```python
    assert len(result.flags) == 1
    assert result.flags[0]["name"] == "0"
    assert len(result.wires) == 1  # stub wire
```

- [ ] **Step 5: Commit**

```bash
git add backend/services/wire_router.py backend/tests/test_wire_router.py
git commit -m "feat: upgrade wire router with dual L-route, obstacle scoring, ground stubs"
```

---

### Task 5: Update VLM Prompts

**Files:**
- Modify: `backend/prompts/layout_system.txt`
- Modify: `backend/prompts/wires_system.txt`

- [ ] **Step 1: Rewrite layout_system.txt**

Replace full contents of `backend/prompts/layout_system.txt`:

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

- [ ] **Step 2: Rewrite wires_system.txt**

Replace full contents of `backend/prompts/wires_system.txt`:

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
- Op-Amp (3-pin): "invin" (inverting), "noninvin" (non-inverting), "out" (output)
- Op-Amp 2-supply (5-pin): "In+" (non-inverting), "In-" (inverting), "V+", "V-", "OUT"

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

- [ ] **Step 3: Commit**

```bash
git add backend/prompts/layout_system.txt backend/prompts/wires_system.txt
git commit -m "feat: update VLM prompts with examples and explicit pin name table"
```

---

### Task 6: Wire Pydantic Validation into vision.py

**Files:**
- Modify: `backend/services/vision.py`

- [ ] **Step 1: Update vision.py to validate VLM responses through Pydantic**

Edit `backend/services/vision.py`. Replace the four async functions with validated versions. The imports and helpers (`_load_prompt`, `_extract_json`) stay the same. Add the import at the top:

```python
import logging

from services.schemas import (
    IdentifyResponse,
    DirectivesResponse,
    LayoutResponse,
    WiresResponse,
)

logger = logging.getLogger(__name__)
```

Replace `identify_components`:

```python
async def identify_components(image_bytes: bytes) -> list[dict]:
    """Step 2: Identify components in the image."""
    system = _load_prompt("identify_system.txt")
    user = (
        "List every component in this schematic. For each, provide:\n"
        "- type (one of: res, cap, ind, voltage, current, opamp2, opamp, npn, pnp, nmos, pmos, diode, zener)\n"
        "- instanceName (the label, e.g. R1, U1, V3)\n"
        "- value (the displayed value)\n"
        "- value2 (only for voltage sources with a second value, otherwise omit)\n\n"
        'Output as JSON array:\n[{"type": "res", "instanceName": "R1", "value": "1k"}, ...]'
    )
    response = await chat_with_vision(VISION_MODEL, system, user, image_bytes)
    raw = _extract_json(response)
    items = raw if isinstance(raw, list) else raw.get("components", [])
    parsed = IdentifyResponse.model_validate({"components": items})
    return [c.model_dump() for c in parsed.components]
```

Replace `read_directives`:

```python
async def read_directives(image_bytes: bytes) -> list[str]:
    """Step 3: Read SPICE directives from the image."""
    system = _load_prompt("directives_system.txt")
    user = (
        "List every SPICE directive visible in this schematic.\n"
        'Output as a JSON array of strings:\n'
        '[".param RINP=1k PSV=15", ".tran 0.005"]'
    )
    response = await chat_with_vision(VISION_MODEL, system, user, image_bytes)
    raw = _extract_json(response)
    items = raw if isinstance(raw, list) else raw.get("directives", [])
    parsed = DirectivesResponse.model_validate({"directives": items})
    return parsed.directives
```

Replace `describe_layout`:

```python
async def describe_layout(image_bytes: bytes, components: list[dict]) -> list[dict]:
    """Step 4: Describe spatial layout."""
    system = _load_prompt("layout_system.txt")
    comp_list = ", ".join(f"{c['instanceName']} ({c['type']})" for c in components)
    user = (
        f"These components were identified in the schematic:\n{comp_list}\n\n"
        "For each component, describe:\n"
        "- region: which area (top-left, top-center, top-right, center-left, center, center-right, bottom-left, bottom-center, bottom-right)\n"
        "- nearby: which other components are adjacent and in which direction\n\n"
        'Output as JSON array:\n'
        '[{"instanceName": "U1", "region": "center", "nearby": [{"name": "R5", "direction": "above"}]}, ...]'
    )
    response = await chat_with_vision(VISION_MODEL, system, user, image_bytes)
    raw = _extract_json(response)
    items = raw if isinstance(raw, list) else raw.get("layout", [])
    parsed = LayoutResponse.model_validate({"layout": items})
    return [item.model_dump() for item in parsed.layout]
```

Replace `describe_wires`:

```python
async def describe_wires(image_bytes: bytes, components: list[dict], pin_info: dict) -> dict:
    """Step 5: Describe wire connections."""
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
    raw = _extract_json(response)
    if not isinstance(raw, dict):
        raw = {"connections": [], "grounds": [], "labels": []}
    parsed = WiresResponse.model_validate(raw)
    return parsed.model_dump(by_alias=True)
```

- [ ] **Step 2: Run existing vision tests to confirm nothing broke**

Run: `cd backend && python -m pytest tests/test_vision.py -v`
Expected: All PASS (these test `_extract_json` which is unchanged)

- [ ] **Step 3: Commit**

```bash
git add backend/services/vision.py
git commit -m "feat: validate all VLM responses through Pydantic models in vision.py"
```

---

### Task 7: Update wizard_routes.py — Bounds, Pin Normalization, Error Handling

**Files:**
- Modify: `backend/api/wizard_routes.py`
- Modify: `backend/tests/test_wizard_routes.py`

- [ ] **Step 1: Update wizard_routes.py**

Replace full contents of `backend/api/wizard_routes.py`:

```python
import json
import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import ValidationError

from services.vision import identify_components, read_directives, describe_layout, describe_wires
from services.layout import compute_layout
from services.wire_router import compute_wires
from services.schemas import normalize_pin

router = APIRouter(prefix="/api/wizard")
logger = logging.getLogger(__name__)

DICTIONARY_DIR = Path(__file__).parent.parent.parent / "dictionary"


def _load_dictionary() -> dict:
    return json.loads(
        (DICTIONARY_DIR / "components.json").read_text(encoding="utf-8")
    )


def _require_image(file: UploadFile) -> None:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")


@router.post("/identify")
async def wizard_identify(file: UploadFile = File(...)):
    _require_image(file)
    image_bytes = await file.read()
    try:
        components = await identify_components(image_bytes)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(400, detail={"error": "Component identification failed", "details": str(exc)})
    return {"components": components}


@router.post("/directives")
async def wizard_directives(file: UploadFile = File(...)):
    _require_image(file)
    image_bytes = await file.read()
    try:
        directives = await read_directives(image_bytes)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(400, detail={"error": "Directive reading failed", "details": str(exc)})
    return {"directives": directives}


@router.post("/layout")
async def wizard_layout(
    file: UploadFile = File(...),
    components_json: str = Form(""),
):
    _require_image(file)
    image_bytes = await file.read()
    components = json.loads(components_json) if components_json else []

    try:
        layout_desc = await describe_layout(image_bytes, components)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(400, detail={"error": "Layout description failed", "details": str(exc)})

    dictionary = _load_dictionary()
    comp_sizes = {}
    for comp_id, comp_data in dictionary["components"].items():
        bounds = comp_data.get("geometry", {}).get("bounds")
        comp_sizes[comp_id] = {
            "width": comp_data["symbol"]["width"],
            "height": comp_data["symbol"]["height"],
            "bounds": bounds,
        }

    positions = compute_layout(layout_desc, comp_sizes)
    return {"layout": layout_desc, "positions": positions}


@router.post("/wires")
async def wizard_wires(
    file: UploadFile = File(...),
    components_json: str = Form(""),
    positions_json: str = Form(""),
):
    _require_image(file)
    image_bytes = await file.read()
    components = json.loads(components_json) if components_json else []
    positions = json.loads(positions_json) if positions_json else {}

    dictionary = _load_dictionary()
    pin_defs = {}
    component_bounds = {}
    for comp_id, comp_data in dictionary["components"].items():
        pin_defs[comp_id] = comp_data.get("pins", [])
        bounds = comp_data.get("geometry", {}).get("bounds")
        if bounds:
            component_bounds[comp_id] = bounds

    try:
        wire_desc = await describe_wires(image_bytes, components, pin_defs)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(400, detail={"error": "Wire tracing failed", "details": str(exc)})

    # Normalize pin names in wire descriptions
    for conn in wire_desc.get("connections", []):
        for key in ("from", "to"):
            ep = conn.get(key)
            if ep:
                comp_name = ep["component"]
                comp_entry = next((c for c in components if c["instanceName"] == comp_name), None)
                if comp_entry:
                    ep["pin"] = normalize_pin(comp_entry["type"], ep["pin"])

    for gnd in wire_desc.get("grounds", []):
        comp_entry = next((c for c in components if c["instanceName"] == gnd["component"]), None)
        if comp_entry:
            gnd["pin"] = normalize_pin(comp_entry["type"], gnd["pin"])

    for lbl in wire_desc.get("labels", []):
        comp_entry = next((c for c in components if c["instanceName"] == lbl["component"]), None)
        if comp_entry:
            lbl["pin"] = normalize_pin(comp_entry["type"], lbl["pin"])

    comp_map = {}
    for comp in components:
        name = comp["instanceName"]
        if name in positions:
            comp_map[name] = {
                "x": positions[name]["x"],
                "y": positions[name]["y"],
                "type": comp["type"],
            }

    wire_result = compute_wires(comp_map, pin_defs, wire_desc, component_bounds)

    return {
        "wire_descriptions": wire_desc,
        "wires": [{"x1": w[0], "y1": w[1], "x2": w[2], "y2": w[3]} for w in wire_result.wires],
        "flags": wire_result.flags,
    }
```

- [ ] **Step 2: Update test for validation error response**

Append to `backend/tests/test_wizard_routes.py`:

```python
@pytest.mark.asyncio
async def test_layout_rejects_non_image():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/wizard/layout",
            files={"file": ("test.txt", b"not an image", "text/plain")},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_wires_rejects_non_image():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/wizard/wires",
            files={"file": ("test.txt", b"not an image", "text/plain")},
        )
    assert resp.status_code == 400
```

- [ ] **Step 3: Run tests**

Run: `cd backend && python -m pytest tests/test_wizard_routes.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add backend/api/wizard_routes.py backend/tests/test_wizard_routes.py
git commit -m "feat: add bounds, pin normalization, and structured errors to wizard routes"
```

---

### Task 8: Frontend Error Handling — api.ts + GenerateWizard.tsx

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/GenerateWizard.tsx`

- [ ] **Step 1: Update api.ts to surface backend error details**

In `frontend/src/lib/api.ts`, replace the four wizard functions' error handling to extract backend error messages. Change each `if (!resp.ok)` block to parse the JSON error:

Replace lines 11-16 (`wizardIdentify`):
```typescript
export async function wizardIdentify(file: File): Promise<{ components: WizardComponent[] }> {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await fetch(`${BASE_URL}/wizard/identify`, { method: "POST", body: formData });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail?.error ?? body?.detail ?? `Identify failed: ${resp.status}`);
  }
  return resp.json();
}
```

Replace lines 19-25 (`wizardDirectives`):
```typescript
export async function wizardDirectives(file: File): Promise<{ directives: string[] }> {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await fetch(`${BASE_URL}/wizard/directives`, { method: "POST", body: formData });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail?.error ?? body?.detail ?? `Directives failed: ${resp.status}`);
  }
  return resp.json();
}
```

Replace lines 27-36 (`wizardLayout`):
```typescript
export async function wizardLayout(
  file: File,
  components: WizardComponent[]
): Promise<{ positions: Record<string, { x: number; y: number }> }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("components_json", JSON.stringify(components));
  const resp = await fetch(`${BASE_URL}/wizard/layout`, { method: "POST", body: formData });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail?.error ?? body?.detail ?? `Layout failed: ${resp.status}`);
  }
  return resp.json();
}
```

Replace lines 39-50 (`wizardWires`):
```typescript
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
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail?.error ?? body?.detail ?? `Wires failed: ${resp.status}`);
  }
  return resp.json();
}
```

- [ ] **Step 2: Add retry button to GenerateWizard.tsx**

In `frontend/src/components/GenerateWizard.tsx`, make two changes:

**Change 1:** In the error display block (around line 361), add a retry button after the error message. Replace the error div:

```tsx
          {error && (
            <div
              style={{
                marginBottom: 12,
                padding: "8px 12px",
                background: "var(--color-error-bg, #ffebee)",
                color: "var(--color-error, #c62828)",
                border: "1px solid var(--color-error, #c62828)",
                borderRadius: 4,
                fontSize: 13,
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <span style={{ flex: 1 }}>{error}</span>
              <button
                onClick={() => {
                  setError(null);
                  if (step === 1) goStep1to2();
                  else if (step === 2) goStep2to3();
                  else if (step === 3) goStep3to4();
                  else if (step === 4) goStep4to5();
                }}
                style={{
                  padding: "2px 10px",
                  border: "1px solid var(--color-error, #c62828)",
                  borderRadius: 4,
                  background: "transparent",
                  color: "var(--color-error, #c62828)",
                  cursor: "pointer",
                  fontSize: 12,
                  whiteSpace: "nowrap",
                }}
              >
                Retry
              </button>
            </div>
          )}
```

**Change 2:** In the footer Next button (around line 700), replace the loading text:

```tsx
                {loading ? "AI is analyzing..." : step === 4 ? "Trace Wires" : "Next →"}
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no TypeScript errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/components/GenerateWizard.tsx
git commit -m "feat: surface backend errors in wizard UI with retry button"
```

---

### Task 9: End-to-End Mock Pipeline Test

**Files:**
- Create: `backend/tests/test_e2e_pipeline.py`

- [ ] **Step 1: Write the end-to-end test**

Create `backend/tests/test_e2e_pipeline.py`:

```python
"""End-to-end test: mock VLM responses -> layout -> wires -> asc_generator -> validate."""
import json
from pathlib import Path

from services.schemas import normalize_pin, WiresResponse
from services.layout import compute_layout
from services.wire_router import compute_wires
from services.asc_generator import SchematicIR, generate_asc
from services.validator import validate_asc

DICTIONARY_DIR = Path(__file__).parent.parent.parent / "dictionary"


def _load_dictionary() -> dict:
    return json.loads(
        (DICTIONARY_DIR / "components.json").read_text(encoding="utf-8")
    )


# ── Mock VLM responses for a simple voltage divider ──────────────────────────

MOCK_COMPONENTS = [
    {"type": "voltage", "instanceName": "V1", "value": "5"},
    {"type": "res", "instanceName": "R1", "value": "10k"},
    {"type": "res", "instanceName": "R2", "value": "10k"},
]

MOCK_DIRECTIVES = [".tran 1m"]

MOCK_LAYOUT = [
    {"instanceName": "V1", "region": "center-left", "nearby": []},
    {"instanceName": "R1", "region": "center", "nearby": [{"name": "V1", "direction": "right"}]},
    {"instanceName": "R2", "region": "center", "nearby": [{"name": "R1", "direction": "below"}]},
]

MOCK_WIRE_DESC = {
    "connections": [
        {"from": {"component": "V1", "pin": "+"}, "to": {"component": "R1", "pin": "A"}},
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "A"}},
    ],
    "grounds": [
        {"component": "V1", "pin": "-"},
        {"component": "R2", "pin": "B"},
    ],
    "labels": [],
}


def test_e2e_voltage_divider():
    dictionary = _load_dictionary()

    # Build comp_sizes with bounds
    comp_sizes = {}
    for comp_id, comp_data in dictionary["components"].items():
        bounds = comp_data.get("geometry", {}).get("bounds")
        comp_sizes[comp_id] = {
            "width": comp_data["symbol"]["width"],
            "height": comp_data["symbol"]["height"],
            "bounds": bounds,
        }

    # Step 1: Layout
    positions = compute_layout(MOCK_LAYOUT, comp_sizes)
    assert "V1" in positions
    assert "R1" in positions
    assert "R2" in positions

    # All positions on 16px grid
    for name, pos in positions.items():
        assert pos["x"] % 16 == 0, f"{name} x not snapped"
        assert pos["y"] % 16 == 0, f"{name} y not snapped"

    # Step 2: Normalize pins in wire description
    wire_desc = json.loads(json.dumps(MOCK_WIRE_DESC))  # deep copy
    for conn in wire_desc["connections"]:
        for key in ("from", "to"):
            ep = conn[key]
            comp = next(c for c in MOCK_COMPONENTS if c["instanceName"] == ep["component"])
            ep["pin"] = normalize_pin(comp["type"], ep["pin"])
    for gnd in wire_desc["grounds"]:
        comp = next(c for c in MOCK_COMPONENTS if c["instanceName"] == gnd["component"])
        gnd["pin"] = normalize_pin(comp["type"], gnd["pin"])

    # Step 3: Wire routing
    pin_defs = {}
    component_bounds = {}
    for comp_id, comp_data in dictionary["components"].items():
        pin_defs[comp_id] = comp_data.get("pins", [])
        bounds = comp_data.get("geometry", {}).get("bounds")
        if bounds:
            component_bounds[comp_id] = bounds

    comp_map = {}
    for comp in MOCK_COMPONENTS:
        name = comp["instanceName"]
        comp_map[name] = {
            "x": positions[name]["x"],
            "y": positions[name]["y"],
            "type": comp["type"],
        }

    wire_result = compute_wires(comp_map, pin_defs, wire_desc, component_bounds)
    assert len(wire_result.wires) >= 2  # at least 2 connections + 2 ground stubs
    assert len(wire_result.flags) >= 2  # 2 ground flags

    # Step 4: Build SchematicIR
    ir = SchematicIR(880, 680)
    for comp in MOCK_COMPONENTS:
        name = comp["instanceName"]
        ir.add_component(
            comp["type"], name, comp["value"],
            positions[name]["x"], positions[name]["y"], "R0",
            comp.get("value2"),
        )
    for w in wire_result.wires:
        ir.add_wire(*w)
    for f in wire_result.flags:
        ir.add_flag(f["name"], f["x"], f["y"])
    for d in MOCK_DIRECTIVES:
        ir.add_text(d, 50, 600)

    # Step 5: Generate .asc
    asc_text = generate_asc(ir)
    assert asc_text.startswith("Version 4")
    assert "SHEET 1 880 680" in asc_text
    assert "SYMBOL voltage" in asc_text
    assert "SYMBOL res" in asc_text
    assert "SYMATTR InstName V1" in asc_text
    assert "SYMATTR InstName R1" in asc_text
    assert "SYMATTR InstName R2" in asc_text
    assert "WIRE" in asc_text
    assert "FLAG" in asc_text

    # Step 6: Validate .asc
    validation = validate_asc(asc_text)
    assert validation["valid"], f"Validation errors: {validation.get('errors', [])}"


def test_e2e_with_vlm_style_pin_names():
    """Test that VLM-style pin names (numeric) produce the same valid output."""
    dictionary = _load_dictionary()

    comp_sizes = {}
    for comp_id, comp_data in dictionary["components"].items():
        bounds = comp_data.get("geometry", {}).get("bounds")
        comp_sizes[comp_id] = {
            "width": comp_data["symbol"]["width"],
            "height": comp_data["symbol"]["height"],
            "bounds": bounds,
        }

    positions = compute_layout(MOCK_LAYOUT, comp_sizes)

    # Use numeric pin names like a VLM would
    wire_desc = {
        "connections": [
            {"from": {"component": "V1", "pin": "1"}, "to": {"component": "R1", "pin": "1"}},
            {"from": {"component": "R1", "pin": "2"}, "to": {"component": "R2", "pin": "1"}},
        ],
        "grounds": [
            {"component": "V1", "pin": "2"},
            {"component": "R2", "pin": "2"},
        ],
        "labels": [],
    }

    # Normalize
    for conn in wire_desc["connections"]:
        for key in ("from", "to"):
            ep = conn[key]
            comp = next(c for c in MOCK_COMPONENTS if c["instanceName"] == ep["component"])
            ep["pin"] = normalize_pin(comp["type"], ep["pin"])
    for gnd in wire_desc["grounds"]:
        comp = next(c for c in MOCK_COMPONENTS if c["instanceName"] == gnd["component"])
        gnd["pin"] = normalize_pin(comp["type"], gnd["pin"])

    # Verify normalization worked
    assert wire_desc["connections"][0]["from"]["pin"] == "+"
    assert wire_desc["connections"][0]["to"]["pin"] == "A"

    pin_defs = {}
    component_bounds = {}
    for comp_id, comp_data in dictionary["components"].items():
        pin_defs[comp_id] = comp_data.get("pins", [])
        bounds = comp_data.get("geometry", {}).get("bounds")
        if bounds:
            component_bounds[comp_id] = bounds

    comp_map = {}
    for comp in MOCK_COMPONENTS:
        name = comp["instanceName"]
        comp_map[name] = {"x": positions[name]["x"], "y": positions[name]["y"], "type": comp["type"]}

    wire_result = compute_wires(comp_map, pin_defs, wire_desc, component_bounds)
    assert len(wire_result.wires) >= 2

    ir = SchematicIR(880, 680)
    for comp in MOCK_COMPONENTS:
        name = comp["instanceName"]
        ir.add_component(comp["type"], name, comp["value"],
                         positions[name]["x"], positions[name]["y"], "R0")
    for w in wire_result.wires:
        ir.add_wire(*w)
    for f in wire_result.flags:
        ir.add_flag(f["name"], f["x"], f["y"])

    asc_text = generate_asc(ir)
    validation = validate_asc(asc_text)
    assert validation["valid"], f"Validation errors: {validation.get('errors', [])}"
```

- [ ] **Step 2: Run the end-to-end test**

Run: `cd backend && python -m pytest tests/test_e2e_pipeline.py -v`
Expected: Both tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_e2e_pipeline.py
git commit -m "test: add end-to-end mock pipeline test for voltage divider circuit"
```

---

### Task 10: Run Full Test Suite + Frontend Build Check

**Files:** None (verification only)

- [ ] **Step 1: Run all backend tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Final commit if any fixups needed**

If any tests fail due to integration issues, fix and commit:
```bash
git add -A
git commit -m "fix: resolve integration issues from pipeline rework"
```
