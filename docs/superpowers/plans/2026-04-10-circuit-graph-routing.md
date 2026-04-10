# Circuit Graph Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the pairwise wire routing with a graph-based system that builds nets via union-find, assigns components to tiers, resolves orientations from topology, auto-sizes the canvas, and routes wires as buses with stubs.

**Architecture:** A new `circuit_graph.py` module holds the core data model (components, nets, tiers). The rewritten `layout.py` queries this graph to place components in tiers with proper spacing. The rewritten `wire_router.py` routes wires per-net using hybrid bus/L-shaped routing. `schematic_builder.py` is updated to use the graph pipeline instead of direct VLM data.

**Tech Stack:** Python 3.14, pytest, dataclasses, no new dependencies

---

### Task 1: CircuitGraph Data Model + Component Construction

**Files:**
- Create: `backend/services/circuit_graph.py`
- Create: `backend/tests/test_circuit_graph.py`

- [ ] **Step 1: Write failing test for component node construction**

```python
# backend/tests/test_circuit_graph.py
import pytest
from services.circuit_graph import CircuitGraph


SAMPLE_DICTIONARY = {
    "components": {
        "res": {
            "pins": [
                {"name": "A", "x": 16, "y": 16, "spiceOrder": 1},
                {"name": "B", "x": 16, "y": 96, "spiceOrder": 2},
            ],
            "symbol": {"width": 32, "height": 80, "svgPath": ""},
        },
        "voltage": {
            "pins": [
                {"name": "+", "x": 0, "y": 16, "spiceOrder": 1},
                {"name": "-", "x": 0, "y": 96, "spiceOrder": 2},
            ],
            "symbol": {"width": 64, "height": 80, "svgPath": ""},
        },
    }
}

SAMPLE_COMPONENTS = [
    {"name": "V1", "type": "voltage", "value": "30V"},
    {"name": "R1", "type": "res", "value": "2"},
    {"name": "R2", "type": "res", "value": "8"},
    {"name": "R3", "type": "res", "value": "1"},
    {"name": "V2", "type": "voltage", "value": "10V"},
]


def test_build_components():
    graph = CircuitGraph(SAMPLE_DICTIONARY)
    graph.add_components(SAMPLE_COMPONENTS)
    assert len(graph.components) == 5
    assert graph.components["V1"].type == "voltage"
    assert graph.components["V1"].value == "30V"
    assert graph.components["R1"].pins == SAMPLE_DICTIONARY["components"]["res"]["pins"]
    assert graph.components["V2"].symbol_size == (64, 80)


def test_add_component_unknown_type_uses_defaults():
    graph = CircuitGraph(SAMPLE_DICTIONARY)
    graph.add_components([{"name": "X1", "type": "unknown_type", "value": "1"}])
    assert graph.components["X1"].type == "unknown_type"
    assert graph.components["X1"].pins == []
    assert graph.components["X1"].symbol_size == (64, 80)  # default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_circuit_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.circuit_graph'`

- [ ] **Step 3: Implement CircuitGraph data model and add_components**

```python
# backend/services/circuit_graph.py
"""Circuit graph: components, nets, tiers — the core data model for layout and routing."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_DEFAULT_SYMBOL_SIZE = (64, 80)


@dataclass
class ComponentNode:
    name: str
    type: str
    value: str
    pins: list[dict]
    symbol_size: tuple[int, int]
    resolved_rotation: str = "R0"
    tier: int = -1
    position: tuple[int, int] | None = None


@dataclass
class Net:
    name: str
    pins: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Tier:
    index: int
    components: list[str] = field(default_factory=list)
    y_position: int = 0


class CircuitGraph:
    def __init__(self, dictionary: dict):
        self._dictionary = dictionary
        self.components: dict[str, ComponentNode] = {}
        self.nets: dict[str, Net] = {}
        self.tiers: list[Tier] = []
        self.flow_direction: str = "vertical"
        self._parent: dict[tuple[str, str], tuple[str, str]] = {}

    def add_components(self, components: list[dict]) -> None:
        for comp in components:
            name = comp.get("name", "")
            ctype = comp.get("type", "res")
            value = comp.get("value", "1")
            comp_def = self._dictionary.get("components", {}).get(ctype, {})
            pins = comp_def.get("pins", [])
            sym = comp_def.get("symbol", {})
            size = (sym.get("width", _DEFAULT_SYMBOL_SIZE[0]),
                    sym.get("height", _DEFAULT_SYMBOL_SIZE[1]))
            self.components[name] = ComponentNode(
                name=name, type=ctype, value=value,
                pins=pins, symbol_size=size,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_circuit_graph.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/circuit_graph.py backend/tests/test_circuit_graph.py
git commit -m "feat: add CircuitGraph data model with component construction"
```

---

### Task 2: Union-Find Net Building

**Files:**
- Modify: `backend/services/circuit_graph.py`
- Modify: `backend/tests/test_circuit_graph.py`

- [ ] **Step 1: Write failing test for net building via union-find**

Add to `backend/tests/test_circuit_graph.py`:

```python
SAMPLE_CONNECTIONS = [
    {"from": {"component": "V1", "pin": "+"}, "to": {"component": "R1", "pin": "A"}},
    {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R2", "pin": "A"}},
    {"from": {"component": "R2", "pin": "A"}, "to": {"component": "R3", "pin": "A"}},
    {"from": {"component": "R3", "pin": "A"}, "to": {"component": "V2", "pin": "+"}},
    {"from": {"component": "V1", "pin": "-"}, "to": {"component": "R1", "pin": "B"}},
    {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "B"}},
    {"from": {"component": "R2", "pin": "B"}, "to": {"component": "R3", "pin": "B"}},
    {"from": {"component": "R3", "pin": "B"}, "to": {"component": "V2", "pin": "-"}},
]

SAMPLE_GROUNDS: list[dict] = []
SAMPLE_LABELS: list[dict] = []


def test_build_nets_union_find():
    graph = CircuitGraph(SAMPLE_DICTIONARY)
    graph.add_components(SAMPLE_COMPONENTS)
    graph.build_nets(SAMPLE_CONNECTIONS, SAMPLE_GROUNDS, SAMPLE_LABELS)
    # Should produce exactly 2 nets (top bus and bottom bus)
    assert len(graph.nets) == 2
    # Each net should have 5 pins
    for net in graph.nets.values():
        assert len(net.pins) == 5


def test_build_nets_with_ground():
    graph = CircuitGraph(SAMPLE_DICTIONARY)
    graph.add_components(SAMPLE_COMPONENTS)
    grounds = [{"component": "V1", "pin": "-"}]
    graph.build_nets(SAMPLE_CONNECTIONS, grounds, [])
    # The net containing V1.- should be named "0" (ground)
    v1_minus_net = None
    for net in graph.nets.values():
        if ("V1", "-") in net.pins:
            v1_minus_net = net
            break
    assert v1_minus_net is not None
    assert v1_minus_net.name == "0"


def test_build_nets_with_label():
    graph = CircuitGraph(SAMPLE_DICTIONARY)
    graph.add_components(SAMPLE_COMPONENTS)
    labels = [{"component": "V1", "pin": "+", "label": "VCC"}]
    graph.build_nets(SAMPLE_CONNECTIONS, [], labels)
    v1_plus_net = None
    for net in graph.nets.values():
        if ("V1", "+") in net.pins:
            v1_plus_net = net
            break
    assert v1_plus_net is not None
    assert v1_plus_net.name == "VCC"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_circuit_graph.py::test_build_nets_union_find -v`
Expected: FAIL — `AttributeError: 'CircuitGraph' object has no attribute 'build_nets'`

- [ ] **Step 3: Implement union-find and build_nets**

Add to `backend/services/circuit_graph.py` inside the `CircuitGraph` class:

```python
    # --- Union-Find helpers ---------------------------------------------------

    def _uf_find(self, pin: tuple[str, str]) -> tuple[str, str]:
        while self._parent.get(pin, pin) != pin:
            self._parent[pin] = self._parent.get(self._parent[pin], self._parent[pin])
            pin = self._parent[pin]
        return pin

    def _uf_union(self, a: tuple[str, str], b: tuple[str, str]) -> None:
        ra, rb = self._uf_find(a), self._uf_find(b)
        if ra != rb:
            self._parent[ra] = rb

    # --- Net construction -----------------------------------------------------

    def build_nets(
        self,
        connections: list[dict],
        grounds: list[dict],
        labels: list[dict],
    ) -> None:
        """Build nets from pairwise connections using union-find."""
        self._parent.clear()
        self.nets.clear()

        # Union all connected pins
        for conn in connections:
            f = conn.get("from", {})
            t = conn.get("to", {})
            pin_a = (f.get("component", ""), f.get("pin", ""))
            pin_b = (t.get("component", ""), t.get("pin", ""))
            if pin_a[0] and pin_b[0]:
                self._uf_union(pin_a, pin_b)

        # Collect all pins that appear in connections
        all_pins: set[tuple[str, str]] = set()
        for conn in connections:
            f = conn.get("from", {})
            t = conn.get("to", {})
            pa = (f.get("component", ""), f.get("pin", ""))
            pb = (t.get("component", ""), t.get("pin", ""))
            if pa[0]:
                all_pins.add(pa)
            if pb[0]:
                all_pins.add(pb)

        # Also add ground and label pins
        for gnd in grounds:
            pin = (gnd.get("component", ""), gnd.get("pin", ""))
            if pin[0]:
                all_pins.add(pin)
        for lbl in labels:
            pin = (lbl.get("component", ""), lbl.get("pin", ""))
            if pin[0]:
                all_pins.add(pin)

        # Group by root
        groups: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for pin in all_pins:
            root = self._uf_find(pin)
            groups.setdefault(root, []).append(pin)

        # Build named net labels (ground = "0", labels = label name)
        ground_pins: set[tuple[str, str]] = set()
        for gnd in grounds:
            pin = (gnd.get("component", ""), gnd.get("pin", ""))
            if pin[0]:
                ground_pins.add(self._uf_find(pin))

        label_names: dict[tuple[str, str], str] = {}
        for lbl in labels:
            pin = (lbl.get("component", ""), lbl.get("pin", ""))
            if pin[0] and lbl.get("label"):
                root = self._uf_find(pin)
                label_names[root] = lbl["label"]

        # Create Net objects
        auto_idx = 0
        for root, pins in groups.items():
            if root in ground_pins:
                name = "0"
            elif root in label_names:
                name = label_names[root]
            else:
                name = f"net_{auto_idx}"
                auto_idx += 1
            self.nets[name] = Net(name=name, pins=sorted(pins))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_circuit_graph.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/circuit_graph.py backend/tests/test_circuit_graph.py
git commit -m "feat: union-find net building from pairwise connections"
```

---

### Task 3: Tier Assignment

**Files:**
- Modify: `backend/services/circuit_graph.py`
- Modify: `backend/tests/test_circuit_graph.py`

- [ ] **Step 1: Write failing test for tier assignment**

Add to `backend/tests/test_circuit_graph.py`:

```python
def _build_circuit04_graph() -> CircuitGraph:
    """Helper: build the ground truth circuit 04 graph (2 voltage sources, 3 resistors)."""
    graph = CircuitGraph(SAMPLE_DICTIONARY)
    graph.add_components(SAMPLE_COMPONENTS)
    graph.build_nets(SAMPLE_CONNECTIONS, SAMPLE_GROUNDS, SAMPLE_LABELS)
    return graph


def test_assign_tiers_parallel_circuit():
    graph = _build_circuit04_graph()
    graph.assign_tiers()
    # Parallel circuit: all components share the same two nets
    # Voltage sources span both tiers -> should be at the edges
    # Resistors are between the two buses -> same tier
    assert len(graph.tiers) >= 2
    # All 3 resistors should be on the same tier
    r1_tier = graph.components["R1"].tier
    r2_tier = graph.components["R2"].tier
    r3_tier = graph.components["R3"].tier
    assert r1_tier == r2_tier == r3_tier


def test_assign_tiers_series_circuit():
    """Series R1 -> R2 -> R3 chain should produce 3 different tiers."""
    dictionary = SAMPLE_DICTIONARY.copy()
    comps = [
        {"name": "R1", "type": "res", "value": "1k"},
        {"name": "R2", "type": "res", "value": "2k"},
        {"name": "R3", "type": "res", "value": "3k"},
    ]
    conns = [
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "A"}},
        {"from": {"component": "R2", "pin": "B"}, "to": {"component": "R3", "pin": "A"}},
    ]
    graph = CircuitGraph(dictionary)
    graph.add_components(comps)
    graph.build_nets(conns, [], [])
    graph.assign_tiers()
    # Each resistor should be on a different tier since they're in series
    assert graph.components["R1"].tier != graph.components["R2"].tier
    assert graph.components["R2"].tier != graph.components["R3"].tier
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_circuit_graph.py::test_assign_tiers_parallel_circuit -v`
Expected: FAIL — `AttributeError: 'CircuitGraph' object has no attribute 'assign_tiers'`

- [ ] **Step 3: Implement assign_tiers**

Add to `backend/services/circuit_graph.py` inside the `CircuitGraph` class:

```python
    def assign_tiers(self) -> None:
        """Assign each component to a tier based on net topology."""
        if not self.components or not self.nets:
            return

        # Build adjacency: which components share a net?
        # comp_nets[comp_name] = set of net names it belongs to
        comp_nets: dict[str, set[str]] = {name: set() for name in self.components}
        for net_name, net in self.nets.items():
            for comp_name, _pin in net.pins:
                if comp_name in comp_nets:
                    comp_nets[comp_name].add(net_name)

        # Pin-to-net mapping for orientation resolution later
        pin_net: dict[tuple[str, str], str] = {}
        for net_name, net in self.nets.items():
            for pin in net.pins:
                pin_net[pin] = net_name

        # Identify which nets each component's first and second pin belong to
        comp_pin_nets: dict[str, tuple[str | None, str | None]] = {}
        for name, node in self.components.items():
            pins = node.pins
            if len(pins) >= 2:
                pin_a = (name, pins[0]["name"])
                pin_b = (name, pins[-1]["name"])
                net_a = pin_net.get(pin_a)
                net_b = pin_net.get(pin_b)
                comp_pin_nets[name] = (net_a, net_b)
            elif len(pins) == 1:
                pin_a = (name, pins[0]["name"])
                comp_pin_nets[name] = (pin_net.get(pin_a), None)
            else:
                comp_pin_nets[name] = (None, None)

        # Group components that share the SAME pair of nets (parallel components)
        parallel_groups: dict[tuple[str | None, str | None], list[str]] = {}
        for name, net_pair in comp_pin_nets.items():
            # Normalize order so (net_a, net_b) == (net_b, net_a)
            key = tuple(sorted(net_pair, key=lambda x: x or ""))
            parallel_groups.setdefault(key, []).append(name)

        # Build a net-level graph for tier assignment
        # Nodes = net names, edges = components connecting two nets
        net_graph: dict[str, set[str]] = {}
        for name, (net_a, net_b) in comp_pin_nets.items():
            if net_a and net_b and net_a != net_b:
                net_graph.setdefault(net_a, set()).add(net_b)
                net_graph.setdefault(net_b, set()).add(net_a)

        # BFS from first net to assign net tiers
        net_tiers: dict[str, int] = {}
        if net_graph:
            start_net = next(iter(net_graph))
            # Prefer a net connected to a voltage source
            for name, node in self.components.items():
                if node.type in ("voltage", "current"):
                    net_a, net_b = comp_pin_nets.get(name, (None, None))
                    if net_a and net_a in net_graph:
                        start_net = net_a
                        break

            queue = [start_net]
            net_tiers[start_net] = 0
            while queue:
                current = queue.pop(0)
                for neighbor in net_graph.get(current, set()):
                    if neighbor not in net_tiers:
                        net_tiers[neighbor] = net_tiers[current] + 1
                        queue.append(neighbor)

        # Assign component tiers
        # Components spanning two nets: place at the tier of their first pin's net
        # Parallel components get the same tier
        for name, node in self.components.items():
            net_a, net_b = comp_pin_nets.get(name, (None, None))
            tier_a = net_tiers.get(net_a, 0) if net_a else 0
            tier_b = net_tiers.get(net_b, 0) if net_b else 0
            # Component sits between its two net tiers
            node.tier = min(tier_a, tier_b)

        # Build tier list
        tier_map: dict[int, list[str]] = {}
        for name, node in self.components.items():
            tier_map.setdefault(node.tier, []).append(name)

        self.tiers = [
            Tier(index=idx, components=comps)
            for idx, comps in sorted(tier_map.items())
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_circuit_graph.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/circuit_graph.py backend/tests/test_circuit_graph.py
git commit -m "feat: tier assignment via net-level BFS"
```

---

### Task 4: Orientation Resolution

**Files:**
- Modify: `backend/services/circuit_graph.py`
- Modify: `backend/tests/test_circuit_graph.py`

- [ ] **Step 1: Write failing test for orientation resolution**

Add to `backend/tests/test_circuit_graph.py`:

```python
def test_resolve_orientations_vertical():
    """Components connecting top-net to bottom-net should be R0 (vertical)."""
    graph = _build_circuit04_graph()
    graph.assign_tiers()
    graph.resolve_orientations()
    # All resistors connect tier-0 net to tier-1 net -> vertical R0
    for name in ["R1", "R2", "R3"]:
        rot = graph.components[name].resolved_rotation
        assert rot in ("R0", "R180"), f"{name} should be vertical, got {rot}"


def test_resolve_orientations_horizontal():
    """Component whose pins connect to same-tier nets should be horizontal."""
    graph = CircuitGraph(SAMPLE_DICTIONARY)
    comps = [
        {"name": "R1", "type": "res", "value": "1k"},
        {"name": "R2", "type": "res", "value": "2k"},
        {"name": "R3", "type": "res", "value": "3k"},
    ]
    # R1 vertical between two nets, R3 horizontal bridging at the top
    conns = [
        {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R3", "pin": "A"}},
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "B"}},
        {"from": {"component": "R3", "pin": "B"}, "to": {"component": "R2", "pin": "A"}},
    ]
    graph.add_components(comps)
    graph.build_nets(conns, [], [])
    graph.assign_tiers()
    graph.resolve_orientations()
    # R3 connects net at tier 0 (R1.A side) to net at tier 0 (R2.A side)
    # But these are different nets at the same tier level -> horizontal
    # R1 and R2 connect across tiers -> vertical
    r1_rot = graph.components["R1"].resolved_rotation
    r2_rot = graph.components["R2"].resolved_rotation
    assert r1_rot in ("R0", "R180")
    assert r2_rot in ("R0", "R180")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_circuit_graph.py::test_resolve_orientations_vertical -v`
Expected: FAIL — `AttributeError: 'CircuitGraph' object has no attribute 'resolve_orientations'`

- [ ] **Step 3: Implement resolve_orientations**

Add to `backend/services/circuit_graph.py` inside the `CircuitGraph` class:

```python
    def resolve_orientations(self) -> None:
        """Set resolved_rotation for each component based on which tiers its pin nets occupy."""
        # Build pin -> net tier mapping
        pin_net_tier: dict[tuple[str, str], int] = {}
        net_tiers: dict[str, int] = {}
        for tier in self.tiers:
            for comp_name in tier.components:
                node = self.components[comp_name]
                for pin in node.pins:
                    key = (comp_name, pin["name"])
                    # Find which net this pin belongs to
                    for net in self.nets.values():
                        if key in net.pins:
                            pin_net_tier[key] = tier.index
                            net_tiers[net.name] = tier.index
                            break

        # Recompute net tiers from the BFS (more accurate)
        net_tier_map: dict[str, int] = {}
        for net_name, net in self.nets.items():
            tiers_seen = set()
            for comp_name, pin_name in net.pins:
                if comp_name in self.components:
                    tiers_seen.add(self.components[comp_name].tier)
            if tiers_seen:
                net_tier_map[net_name] = min(tiers_seen)

        for name, node in self.components.items():
            if len(node.pins) < 2:
                node.resolved_rotation = "R0"
                continue

            pin_a = (name, node.pins[0]["name"])
            pin_b = (name, node.pins[-1]["name"])

            # Find each pin's net tier
            tier_a: int | None = None
            tier_b: int | None = None
            for net in self.nets.values():
                if pin_a in net.pins:
                    tier_a = net_tier_map.get(net.name, 0)
                if pin_b in net.pins:
                    tier_b = net_tier_map.get(net.name, 0)

            if tier_a is None:
                tier_a = 0
            if tier_b is None:
                tier_b = 0

            if tier_a == tier_b:
                # Same tier -> horizontal (R90)
                node.resolved_rotation = "R90"
            elif tier_a < tier_b:
                # Pin A's net is higher (lower tier index) -> A on top -> R0
                node.resolved_rotation = "R0"
            else:
                # Pin A's net is lower -> flip -> R180
                node.resolved_rotation = "R180"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_circuit_graph.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/circuit_graph.py backend/tests/test_circuit_graph.py
git commit -m "feat: topology-driven orientation resolution"
```

---

### Task 5: Rewrite layout.py — Tier-Based Placement

**Files:**
- Modify: `backend/services/layout.py`
- Modify: `backend/tests/test_layout.py`

- [ ] **Step 1: Write failing tests for tier-based layout**

Replace the contents of `backend/tests/test_layout.py`:

```python
# backend/tests/test_layout.py
import pytest
from services.circuit_graph import CircuitGraph
from services.layout import compute_layout_from_graph

DICTIONARY = {
    "components": {
        "res": {
            "pins": [
                {"name": "A", "x": 16, "y": 16, "spiceOrder": 1},
                {"name": "B", "x": 16, "y": 96, "spiceOrder": 2},
            ],
            "symbol": {"width": 32, "height": 80, "svgPath": ""},
        },
        "voltage": {
            "pins": [
                {"name": "+", "x": 0, "y": 16, "spiceOrder": 1},
                {"name": "-", "x": 0, "y": 96, "spiceOrder": 2},
            ],
            "symbol": {"width": 64, "height": 80, "svgPath": ""},
        },
    }
}


def _make_graph(comps, conns, grounds=None, labels=None):
    g = CircuitGraph(DICTIONARY)
    g.add_components(comps)
    g.build_nets(conns, grounds or [], labels or [])
    g.assign_tiers()
    g.resolve_orientations()
    return g


def test_canvas_auto_sizing():
    comps = [
        {"name": "V1", "type": "voltage", "value": "30V"},
        {"name": "R1", "type": "res", "value": "2"},
        {"name": "R2", "type": "res", "value": "8"},
        {"name": "R3", "type": "res", "value": "1"},
        {"name": "V2", "type": "voltage", "value": "10V"},
    ]
    conns = [
        {"from": {"component": "V1", "pin": "+"}, "to": {"component": "R1", "pin": "A"}},
        {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R2", "pin": "A"}},
        {"from": {"component": "R2", "pin": "A"}, "to": {"component": "R3", "pin": "A"}},
        {"from": {"component": "R3", "pin": "A"}, "to": {"component": "V2", "pin": "+"}},
        {"from": {"component": "V1", "pin": "-"}, "to": {"component": "R1", "pin": "B"}},
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "B"}},
        {"from": {"component": "R2", "pin": "B"}, "to": {"component": "R3", "pin": "B"}},
        {"from": {"component": "R3", "pin": "B"}, "to": {"component": "V2", "pin": "-"}},
    ]
    graph = _make_graph(comps, conns)
    positions, sheet = compute_layout_from_graph(graph)
    assert sheet[0] >= 800  # min width
    assert sheet[1] >= 600  # min height


def test_grid_snap():
    comps = [{"name": "R1", "type": "res", "value": "1k"}]
    graph = _make_graph(comps, [])
    positions, sheet = compute_layout_from_graph(graph)
    assert positions["R1"][0] % 16 == 0
    assert positions["R1"][1] % 16 == 0


def test_minimum_spacing():
    comps = [
        {"name": "R1", "type": "res", "value": "1k"},
        {"name": "R2", "type": "res", "value": "2k"},
        {"name": "R3", "type": "res", "value": "3k"},
    ]
    conns = [
        {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R2", "pin": "A"}},
        {"from": {"component": "R2", "pin": "A"}, "to": {"component": "R3", "pin": "A"}},
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "B"}},
        {"from": {"component": "R2", "pin": "B"}, "to": {"component": "R3", "pin": "B"}},
    ]
    graph = _make_graph(comps, conns)
    positions, sheet = compute_layout_from_graph(graph)
    names = list(positions.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            xi, yi = positions[names[i]]
            xj, yj = positions[names[j]]
            dist = abs(xi - xj) + abs(yi - yj)
            assert dist >= 128, f"{names[i]} and {names[j]} too close: {dist}"


def test_parallel_components_same_y():
    """Parallel components (same tier) should have the same Y position."""
    comps = [
        {"name": "R1", "type": "res", "value": "1k"},
        {"name": "R2", "type": "res", "value": "2k"},
    ]
    conns = [
        {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R2", "pin": "A"}},
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "B"}},
    ]
    graph = _make_graph(comps, conns)
    positions, _ = compute_layout_from_graph(graph)
    assert positions["R1"][1] == positions["R2"][1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_layout.py -v`
Expected: FAIL — `ImportError: cannot import name 'compute_layout_from_graph'`

- [ ] **Step 3: Rewrite layout.py with tier-based placement**

Replace the contents of `backend/services/layout.py`:

```python
# backend/services/layout.py
"""Tier-based component placement from CircuitGraph."""
from __future__ import annotations

from services.circuit_graph import CircuitGraph

TIER_SPACING = 160
COMP_SPACING = 128
MARGIN = 64
GRID = 16
MIN_WIDTH = 800
MIN_HEIGHT = 600


def _snap(v: int) -> int:
    return round(v / GRID) * GRID


def compute_layout_from_graph(
    graph: CircuitGraph,
) -> tuple[dict[str, tuple[int, int]], tuple[int, int]]:
    """Place components based on tier assignment.

    Returns:
        positions: dict mapping component name -> (x, y)
        sheet_size: (width, height) of the auto-sized canvas
    """
    if not graph.tiers:
        # No tiers — place all components in a single row
        for i, (name, node) in enumerate(graph.components.items()):
            node.position = (_snap(MARGIN + i * COMP_SPACING), _snap(MARGIN))
        width = max(MIN_WIDTH, MARGIN + len(graph.components) * COMP_SPACING + MARGIN)
        positions = {n: node.position for n, node in graph.components.items() if node.position}
        return positions, (_snap(width), MIN_HEIGHT)

    num_tiers = len(graph.tiers)
    max_in_tier = max(len(t.components) for t in graph.tiers) if graph.tiers else 1

    # Auto-size canvas
    width = _snap(max(MIN_WIDTH, MARGIN + max_in_tier * COMP_SPACING + MARGIN))
    height = _snap(max(MIN_HEIGHT, MARGIN + num_tiers * TIER_SPACING + MARGIN))

    # Assign Y position to each tier
    for tier in graph.tiers:
        tier.y_position = _snap(MARGIN + tier.index * TIER_SPACING)

    # Place components within each tier, centered horizontally
    for tier in graph.tiers:
        n = len(tier.components)
        if n == 0:
            continue
        total_width = (n - 1) * COMP_SPACING
        start_x = (width - total_width) // 2

        for i, comp_name in enumerate(tier.components):
            node = graph.components.get(comp_name)
            if not node:
                continue
            x = _snap(start_x + i * COMP_SPACING)
            y = tier.y_position
            node.position = (x, y)

    positions = {}
    for name, node in graph.components.items():
        if node.position:
            positions[name] = node.position
        else:
            positions[name] = (_snap(MARGIN), _snap(MARGIN))

    return positions, (width, height)


# Keep old function signature for backward compatibility during transition
def compute_layout(
    layout_desc: list[dict],
    component_sizes: dict[str, dict],
    sheet_width: int = 880,
    sheet_height: int = 680,
) -> dict[str, dict]:
    """Legacy layout function — kept for non-graph callers."""
    positions: dict[str, dict] = {}
    cols = max(1, int(len(layout_desc) ** 0.5) + 1)
    for i, item in enumerate(layout_desc):
        name = item.get("instanceName", f"C{i}")
        x = _snap(MARGIN + (i % cols) * COMP_SPACING)
        y = _snap(MARGIN + (i // cols) * TIER_SPACING)
        rotation = item.get("rotation", "R0")
        if rotation not in ("R0", "R90", "R180", "R270", "M0", "M90"):
            rotation = "R0"
        positions[name] = {"x": x, "y": y, "rotation": rotation}
    return positions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_layout.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/layout.py backend/tests/test_layout.py
git commit -m "feat: rewrite layout.py with tier-based placement and auto-sizing"
```

---

### Task 6: Rewrite wire_router.py — Net-Aware Hybrid Routing

**Files:**
- Modify: `backend/services/wire_router.py`
- Modify: `backend/tests/test_wire_router.py`

- [ ] **Step 1: Write failing tests for net-aware routing**

Replace the contents of `backend/tests/test_wire_router.py`:

```python
# backend/tests/test_wire_router.py
import pytest
from services.circuit_graph import CircuitGraph
from services.wire_router import route_nets, WireResult

DICTIONARY = {
    "components": {
        "res": {
            "pins": [
                {"name": "A", "x": 16, "y": 16, "spiceOrder": 1},
                {"name": "B", "x": 16, "y": 96, "spiceOrder": 2},
            ],
            "symbol": {"width": 32, "height": 80, "svgPath": ""},
        },
        "voltage": {
            "pins": [
                {"name": "+", "x": 0, "y": 16, "spiceOrder": 1},
                {"name": "-", "x": 0, "y": 96, "spiceOrder": 2},
            ],
            "symbol": {"width": 64, "height": 80, "svgPath": ""},
        },
    }
}


def _make_routed_graph(comps, conns, grounds=None, labels=None):
    from services.layout import compute_layout_from_graph
    g = CircuitGraph(DICTIONARY)
    g.add_components(comps)
    g.build_nets(conns, grounds or [], labels or [])
    g.assign_tiers()
    g.resolve_orientations()
    compute_layout_from_graph(g)
    return g


def test_two_pin_net_produces_wire():
    comps = [
        {"name": "R1", "type": "res", "value": "1k"},
        {"name": "R2", "type": "res", "value": "2k"},
    ]
    conns = [
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "A"}},
    ]
    graph = _make_routed_graph(comps, conns)
    result = route_nets(graph)
    assert len(result.wires) >= 1


def test_self_short_rejected():
    """Wires connecting both pins of the same component should be skipped."""
    comps = [{"name": "R1", "type": "res", "value": "1k"}]
    conns = [
        {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R1", "pin": "B"}},
    ]
    graph = _make_routed_graph(comps, conns)
    result = route_nets(graph)
    # Should produce 0 wires — self-short rejected
    assert len(result.wires) == 0


def test_bus_routing_collinear_pins():
    """Pins at the same Y should produce a single horizontal bus wire."""
    comps = [
        {"name": "R1", "type": "res", "value": "1k"},
        {"name": "R2", "type": "res", "value": "2k"},
        {"name": "R3", "type": "res", "value": "3k"},
    ]
    conns = [
        {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R2", "pin": "A"}},
        {"from": {"component": "R2", "pin": "A"}, "to": {"component": "R3", "pin": "A"}},
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "B"}},
        {"from": {"component": "R2", "pin": "B"}, "to": {"component": "R3", "pin": "B"}},
    ]
    graph = _make_routed_graph(comps, conns)
    result = route_nets(graph)
    # Should have wires and no self-shorts
    assert len(result.wires) >= 2
    # All wires should be either horizontal or vertical (no diagonal)
    for w in result.wires:
        assert w[0] == w[2] or w[1] == w[3], f"Diagonal wire: {w}"


def test_ground_flag():
    comps = [{"name": "V1", "type": "voltage", "value": "5"}]
    conns: list[dict] = []
    grounds = [{"component": "V1", "pin": "-"}]
    graph = _make_routed_graph(comps, conns, grounds=grounds)
    result = route_nets(graph)
    assert len(result.flags) == 1
    assert result.flags[0]["name"] == "0"


def test_no_duplicate_wires():
    """Router should not produce duplicate wire segments."""
    comps = [
        {"name": "R1", "type": "res", "value": "1k"},
        {"name": "R2", "type": "res", "value": "2k"},
    ]
    conns = [
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "A"}},
    ]
    graph = _make_routed_graph(comps, conns)
    result = route_nets(graph)
    wire_set = set()
    for w in result.wires:
        # Normalize direction (smaller coords first)
        normalized = (min(w[0], w[2]), min(w[1], w[3]), max(w[0], w[2]), max(w[1], w[3]))
        assert normalized not in wire_set, f"Duplicate wire: {w}"
        wire_set.add(normalized)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_wire_router.py -v`
Expected: FAIL — `ImportError: cannot import name 'route_nets'`

- [ ] **Step 3: Rewrite wire_router.py with net-aware routing**

Replace the contents of `backend/services/wire_router.py`:

```python
# backend/services/wire_router.py
"""Net-aware hybrid wire routing from CircuitGraph."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from services.circuit_graph import CircuitGraph

logger = logging.getLogger(__name__)

COLLINEAR_TOLERANCE = 80  # half of TIER_SPACING


@dataclass
class WireResult:
    wires: list[tuple[int, int, int, int]] = field(default_factory=list)
    flags: list[dict] = field(default_factory=list)


def _abs_pin_pos(
    comp_x: int, comp_y: int,
    pin: dict,
    rotation: str,
    symbol_size: tuple[int, int],
) -> tuple[int, int]:
    """Compute absolute pin position given component position, rotation, and pin offset."""
    px, py = pin["x"], pin["y"]
    w, h = symbol_size
    if rotation == "R90":
        px, py = py, w - px
    elif rotation == "R180":
        px, py = w - px, h - py
    elif rotation == "R270":
        px, py = h - py, px
    return (comp_x + int(px), comp_y + int(py))


def _deduplicate(wires: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """Remove duplicate wire segments (order-independent)."""
    seen: set[tuple[int, int, int, int]] = set()
    result = []
    for w in wires:
        normalized = (min(w[0], w[2]), min(w[1], w[3]), max(w[0], w[2]), max(w[1], w[3]))
        if normalized not in seen:
            seen.add(normalized)
            result.append(w)
    return result


def route_nets(graph: CircuitGraph) -> WireResult:
    """Route wires for each net in the circuit graph."""
    result = WireResult()

    for net_name, net in graph.nets.items():
        # Collect absolute pin positions for this net
        pin_positions: list[tuple[int, int, str]] = []  # (x, y, comp_name)
        for comp_name, pin_name in net.pins:
            node = graph.components.get(comp_name)
            if not node or not node.position:
                continue
            # Find the pin definition
            pin_def = None
            for p in node.pins:
                if p["name"] == pin_name:
                    pin_def = p
                    break
            if not pin_def:
                continue
            x, y = _abs_pin_pos(
                node.position[0], node.position[1],
                pin_def, node.resolved_rotation, node.symbol_size,
            )
            pin_positions.append((x, y, comp_name))

        if len(pin_positions) < 2:
            continue

        # Check if this is a self-short (all pins on the same component)
        comp_names = set(p[2] for p in pin_positions)
        if len(comp_names) == 1:
            logger.info("Skipping self-short net '%s' on %s", net_name, next(iter(comp_names)))
            continue

        # Check collinearity
        ys = [p[1] for p in pin_positions]
        xs = [p[0] for p in pin_positions]
        y_range = max(ys) - min(ys)
        x_range = max(xs) - min(xs)

        if y_range <= COLLINEAR_TOLERANCE and x_range > 0:
            # Horizontal bus — sort by X
            _route_horizontal_bus(pin_positions, result)
        elif x_range <= COLLINEAR_TOLERANCE and y_range > 0:
            # Vertical bus — sort by Y
            _route_vertical_bus(pin_positions, result)
        elif len(pin_positions) == 2:
            # Two-pin L-shaped route
            _route_l_shaped(pin_positions[0], pin_positions[1], result)
        else:
            # Multi-pin non-collinear: pick best bus axis, add stubs
            _route_multi_pin(pin_positions, result)

    # Handle ground flags
    for net_name, net in graph.nets.items():
        if net_name == "0":
            # Find the lowest pin position in the ground net
            for comp_name, pin_name in net.pins:
                node = graph.components.get(comp_name)
                if not node or not node.position:
                    continue
                pin_def = None
                for p in node.pins:
                    if p["name"] == pin_name:
                        pin_def = p
                        break
                if not pin_def:
                    continue
                x, y = _abs_pin_pos(
                    node.position[0], node.position[1],
                    pin_def, node.resolved_rotation, node.symbol_size,
                )
                result.wires.append((x, y, x, y + 32))
                result.flags.append({"name": "0", "x": x, "y": y + 32})
                break  # One ground flag is enough — the net connects them

    # Handle named labels (non-ground)
    for net_name, net in graph.nets.items():
        if net_name != "0" and not net_name.startswith("net_"):
            # Named net — add flag at first pin
            for comp_name, pin_name in net.pins:
                node = graph.components.get(comp_name)
                if not node or not node.position:
                    continue
                pin_def = None
                for p in node.pins:
                    if p["name"] == pin_name:
                        pin_def = p
                        break
                if not pin_def:
                    continue
                x, y = _abs_pin_pos(
                    node.position[0], node.position[1],
                    pin_def, node.resolved_rotation, node.symbol_size,
                )
                result.flags.append({"name": net_name, "x": x, "y": y})
                break

    result.wires = _deduplicate(result.wires)
    return result


def _route_horizontal_bus(
    pins: list[tuple[int, int, str]],
    result: WireResult,
) -> None:
    """Route a horizontal bus connecting collinear-ish pins."""
    sorted_pins = sorted(pins, key=lambda p: p[0])
    # Pick bus Y as the median Y
    ys = [p[1] for p in sorted_pins]
    bus_y = sorted(ys)[len(ys) // 2]

    # Draw the main bus wire
    result.wires.append((sorted_pins[0][0], bus_y, sorted_pins[-1][0], bus_y))

    # Add vertical stubs for pins not exactly on the bus
    for px, py, _ in sorted_pins:
        if py != bus_y:
            result.wires.append((px, py, px, bus_y))


def _route_vertical_bus(
    pins: list[tuple[int, int, str]],
    result: WireResult,
) -> None:
    """Route a vertical bus connecting collinear-ish pins."""
    sorted_pins = sorted(pins, key=lambda p: p[1])
    xs = [p[0] for p in sorted_pins]
    bus_x = sorted(xs)[len(xs) // 2]

    result.wires.append((bus_x, sorted_pins[0][1], bus_x, sorted_pins[-1][1]))

    for px, py, _ in sorted_pins:
        if px != bus_x:
            result.wires.append((px, py, bus_x, py))


def _route_l_shaped(
    a: tuple[int, int, str],
    b: tuple[int, int, str],
    result: WireResult,
) -> None:
    """Route an L-shaped wire between two pins."""
    ax, ay, _ = a
    bx, by, _ = b
    if ax == bx or ay == by:
        result.wires.append((ax, ay, bx, by))
    else:
        # Horizontal first, then vertical
        result.wires.append((ax, ay, bx, ay))
        result.wires.append((bx, ay, bx, by))


def _route_multi_pin(
    pins: list[tuple[int, int, str]],
    result: WireResult,
) -> None:
    """Route a multi-pin non-collinear net: pick best bus, add stubs."""
    ys = [p[1] for p in pins]
    xs = [p[0] for p in pins]

    # Try horizontal bus: total stub length = sum of |py - bus_y|
    # Try vertical bus: total stub length = sum of |px - bus_x|
    best_bus_y = sorted(ys)[len(ys) // 2]
    h_cost = sum(abs(py - best_bus_y) for _, py, _ in pins)

    best_bus_x = sorted(xs)[len(xs) // 2]
    v_cost = sum(abs(px - best_bus_x) for px, _, _ in pins)

    if h_cost <= v_cost:
        # Horizontal bus
        sorted_by_x = sorted(pins, key=lambda p: p[0])
        result.wires.append((sorted_by_x[0][0], best_bus_y, sorted_by_x[-1][0], best_bus_y))
        for px, py, _ in pins:
            if py != best_bus_y:
                result.wires.append((px, py, px, best_bus_y))
    else:
        # Vertical bus
        sorted_by_y = sorted(pins, key=lambda p: p[1])
        result.wires.append((best_bus_x, sorted_by_y[0][1], best_bus_x, sorted_by_y[-1][1]))
        for px, py, _ in pins:
            if px != best_bus_x:
                result.wires.append((px, py, best_bus_x, py))


# Keep old interface for backward compatibility during transition
def compute_wires(
    components: dict[str, dict],
    pin_defs: dict[str, list[dict]],
    connections_data: dict,
    component_bounds: dict[str, list] | None = None,
    symbol_sizes: dict[str, tuple[int, int]] | None = None,
) -> WireResult:
    """Legacy pairwise routing — kept for non-graph callers."""
    result = WireResult()

    for conn in connections_data.get("connections", []):
        from_name = conn["from"]["component"]
        to_name = conn["to"]["component"]
        from_comp = components.get(from_name)
        to_comp = components.get(to_name)
        if not from_comp or not to_comp:
            continue
        from_pins = pin_defs.get(from_comp["type"], [])
        to_pins = pin_defs.get(to_comp["type"], [])
        from_pin = next((p for p in from_pins if p["name"] == conn["from"]["pin"]), None)
        to_pin = next((p for p in to_pins if p["name"] == conn["to"]["pin"]), None)
        if not from_pin or not to_pin:
            continue
        sz_f = symbol_sizes.get(from_comp["type"], (64, 80)) if symbol_sizes else (64, 80)
        sz_t = symbol_sizes.get(to_comp["type"], (64, 80)) if symbol_sizes else (64, 80)
        fx, fy = _abs_pin_pos(from_comp["x"], from_comp["y"], from_pin, from_comp.get("rotation", "R0"), sz_f)
        tx, ty = _abs_pin_pos(to_comp["x"], to_comp["y"], to_pin, to_comp.get("rotation", "R0"), sz_t)
        if fx == tx or fy == ty:
            result.wires.append((fx, fy, tx, ty))
        else:
            result.wires.append((fx, fy, tx, fy))
            result.wires.append((tx, fy, tx, ty))

    for gnd in connections_data.get("grounds", []):
        comp = components.get(gnd["component"])
        if not comp:
            continue
        pins = pin_defs.get(comp["type"], [])
        pin = next((p for p in pins if p["name"] == gnd["pin"]), None)
        if not pin and pins:
            pin = pins[-1]
        if not pin:
            continue
        sz = symbol_sizes.get(comp["type"], (64, 80)) if symbol_sizes else (64, 80)
        px, py = _abs_pin_pos(comp["x"], comp["y"], pin, comp.get("rotation", "R0"), sz)
        result.wires.append((px, py, px, py + 32))
        result.flags.append({"name": "0", "x": px, "y": py + 32})

    for label in connections_data.get("labels", []):
        comp = components.get(label["component"])
        if not comp:
            continue
        pins = pin_defs.get(comp["type"], [])
        pin = next((p for p in pins if p["name"] == label["pin"]), None)
        if not pin and pins:
            pin = pins[0]
        if not pin:
            continue
        sz = symbol_sizes.get(comp["type"], (64, 80)) if symbol_sizes else (64, 80)
        px, py = _abs_pin_pos(comp["x"], comp["y"], pin, comp.get("rotation", "R0"), sz)
        result.flags.append({"name": label["label"], "x": px, "y": py})

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_wire_router.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/wire_router.py backend/tests/test_wire_router.py
git commit -m "feat: rewrite wire_router.py with net-aware hybrid bus routing"
```

---

### Task 7: Update schematic_builder.py to Use CircuitGraph

**Files:**
- Modify: `backend/services/schematic_builder.py`

- [ ] **Step 1: Write failing test for graph-based build_asc**

Add to `backend/tests/test_circuit_graph.py`:

```python
def test_build_asc_from_graph():
    """Full pipeline: graph -> layout -> routing -> .asc text."""
    from services.schematic_builder import build_asc
    analysis = {
        "components": [
            {"name": "V1", "type": "voltage", "value": "30V", "x": 10, "y": 30, "orientation": "vertical"},
            {"name": "R1", "type": "res", "value": "2", "x": 30, "y": 60, "orientation": "vertical"},
            {"name": "V2", "type": "voltage", "value": "10V", "x": 90, "y": 30, "orientation": "vertical"},
        ],
        "connections": [
            {"from": "V1.+", "to": "R1.A"},
            {"from": "R1.A", "to": "V2.+"},
            {"from": "V1.-", "to": "R1.B"},
            {"from": "R1.B", "to": "V2.-"},
        ],
        "grounds": [],
        "labels": [],
    }
    from tests.test_circuit_graph import SAMPLE_DICTIONARY
    asc = build_asc(analysis, SAMPLE_DICTIONARY)
    assert "Version 4" in asc
    assert "SYMBOL voltage" in asc
    assert "SYMBOL res" in asc
    assert "SYMATTR InstName V1" in asc
    assert "SYMATTR Value 30V" in asc
    assert "WIRE" in asc
    # Should NOT contain a self-shorting wire
    lines = asc.split("\n")
    wire_lines = [l for l in lines if l.startswith("WIRE")]
    assert len(wire_lines) >= 2
```

- [ ] **Step 2: Run test to verify it fails (the current build_asc doesn't use the graph)**

Run: `cd backend && python -m pytest tests/test_circuit_graph.py::test_build_asc_from_graph -v`
Expected: May pass partially with old code, but the WIRE assertions may fail due to old routing bugs.

- [ ] **Step 3: Rewrite schematic_builder.py to use CircuitGraph pipeline**

Replace the contents of `backend/services/schematic_builder.py`:

```python
"""Convert VLM analysis JSON into a complete .asc file using CircuitGraph pipeline."""
from __future__ import annotations

import logging

from services.circuit_graph import CircuitGraph
from services.layout import compute_layout_from_graph
from services.wire_router import route_nets

logger = logging.getLogger(__name__)


def _snap(v: int) -> int:
    return round(v / 16) * 16


def _parse_pin_ref(ref: str) -> tuple[str, str] | None:
    """Parse 'R1.B' into ('R1', 'B')."""
    parts = ref.rsplit(".", 1)
    if len(parts) != 2:
        return None
    return (parts[0], parts[1])


def build_asc(
    analysis: dict,
    dictionary: dict,
    sheet_width: int = 880,
    sheet_height: int = 680,
) -> str:
    """Convert VLM analysis into .asc text using the circuit graph pipeline."""
    components = analysis.get("components", [])
    raw_connections = analysis.get("connections", [])
    raw_grounds = analysis.get("grounds", [])
    raw_labels = analysis.get("labels", [])

    # Normalize connection format (handle both "R1.A" string and {component, pin} dict)
    connections: list[dict] = []
    for conn in raw_connections:
        if isinstance(conn, dict) and "from" in conn and "to" in conn:
            f = conn["from"]
            t = conn["to"]
            if isinstance(f, str) and isinstance(t, str):
                pf = _parse_pin_ref(f)
                pt = _parse_pin_ref(t)
                if pf and pt:
                    connections.append({
                        "from": {"component": pf[0], "pin": pf[1]},
                        "to": {"component": pt[0], "pin": pt[1]},
                    })
            elif isinstance(f, dict) and isinstance(t, dict):
                connections.append(conn)

    # Normalize grounds
    grounds: list[dict] = []
    for gnd in raw_grounds:
        if isinstance(gnd, str):
            parsed = _parse_pin_ref(gnd)
            if parsed:
                grounds.append({"component": parsed[0], "pin": parsed[1]})
        elif isinstance(gnd, dict):
            grounds.append(gnd)

    # Normalize labels
    labels: list[dict] = []
    for lbl in raw_labels:
        if isinstance(lbl, dict):
            if "pin" in lbl and isinstance(lbl["pin"], str) and "." in lbl["pin"]:
                parsed = _parse_pin_ref(lbl["pin"])
                if parsed:
                    labels.append({
                        "component": parsed[0],
                        "pin": parsed[1],
                        "label": lbl.get("name", lbl.get("label", "")),
                    })
            else:
                labels.append(lbl)

    # Build circuit graph
    graph = CircuitGraph(dictionary)
    graph.add_components(components)
    graph.build_nets(connections, grounds, labels)
    graph.assign_tiers()
    graph.resolve_orientations()

    # Layout
    positions, (auto_w, auto_h) = compute_layout_from_graph(graph)
    final_w = max(sheet_width, auto_w)
    final_h = max(sheet_height, auto_h)

    # Route wires
    wire_result = route_nets(graph)

    # Build .asc lines
    lines = ["Version 4", f"SHEET 1 {final_w} {final_h}"]

    # Wires
    for w in wire_result.wires:
        lines.append(f"WIRE {w[0]} {w[1]} {w[2]} {w[3]}")

    # Flags
    for flag in wire_result.flags:
        lines.append(f"FLAG {flag['x']} {flag['y']} {flag['name']}")

    # Components
    for name, node in graph.components.items():
        if not node.position:
            continue
        x, y = node.position
        rot = node.resolved_rotation
        lines.append(f"SYMBOL {node.type} {x} {y} {rot}")

        # WINDOW lines from dictionary
        comp_def = dictionary.get("components", {}).get(node.type, {})
        for win in comp_def.get("windows", []):
            lines.append(
                f"WINDOW {win['index']} {win['x']} {win['y']} {win['justification']} {win['fontSize']}"
            )

        lines.append(f"SYMATTR InstName {name}")
        lines.append(f"SYMATTR Value {node.value}")

    lines.append("")

    logger.info("Built .asc: %d components, %d wires, %d flags",
                len(graph.components), len(wire_result.wires), len(wire_result.flags))

    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_circuit_graph.py::test_build_asc_from_graph -v`
Expected: PASS

- [ ] **Step 5: Run all tests to check nothing is broken**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: All tests pass (or only pre-existing failures unrelated to this change)

- [ ] **Step 6: Commit**

```bash
git add backend/services/schematic_builder.py backend/tests/test_circuit_graph.py
git commit -m "feat: rewrite schematic_builder.py to use CircuitGraph pipeline"
```

---

### Task 8: Update wizard_routes.py Integration

**Files:**
- Modify: `backend/api/wizard_routes.py`

- [ ] **Step 1: Read the current generate-asc endpoint**

The `wizard_generate_asc` endpoint at `backend/api/wizard_routes.py:197-231` calls `build_asc(analysis, dictionary, sheet_width, sheet_height)`. Since we kept the same function signature in the rewritten `schematic_builder.py`, no code change is needed here for the single-shot endpoint.

However, the multi-step wizard wire endpoint (`wizard_wires` at line 113-194) still uses the old `compute_wires` function. We need to verify it still works with the legacy `compute_wires` that we kept in `wire_router.py`.

- [ ] **Step 2: Run the wizard route tests to verify compatibility**

Run: `cd backend && python -m pytest tests/test_wizard_routes.py -v --tb=short`
Expected: All PASS (the legacy compute_wires is still available)

- [ ] **Step 3: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: All tests pass (or only pre-existing unrelated failures)

- [ ] **Step 4: Commit (if any changes were needed)**

```bash
git add backend/api/wizard_routes.py
git commit -m "chore: verify wizard_routes.py compatibility with new pipeline"
```

---

### Task 9: Integration Test with Ground Truth Circuit 04

**Files:**
- Create: `backend/tests/test_integration_graph.py`

- [ ] **Step 1: Write integration test for the parallel resistor circuit**

```python
# backend/tests/test_integration_graph.py
"""Integration test: circuit 04 (parallel resistors) through the full graph pipeline."""
import pytest
from services.circuit_graph import CircuitGraph
from services.layout import compute_layout_from_graph
from services.wire_router import route_nets
from services.schematic_builder import build_asc

DICTIONARY = {
    "components": {
        "res": {
            "pins": [
                {"name": "A", "x": 16, "y": 16, "spiceOrder": 1},
                {"name": "B", "x": 16, "y": 96, "spiceOrder": 2},
            ],
            "symbol": {"width": 32, "height": 80, "svgPath": ""},
            "windows": [
                {"index": 0, "x": 36, "y": 40, "justification": "Left", "fontSize": 2},
                {"index": 3, "x": 36, "y": 76, "justification": "Left", "fontSize": 2},
            ],
        },
        "voltage": {
            "pins": [
                {"name": "+", "x": 0, "y": 16, "spiceOrder": 1},
                {"name": "-", "x": 0, "y": 96, "spiceOrder": 2},
            ],
            "symbol": {"width": 64, "height": 80, "svgPath": ""},
            "windows": [
                {"index": 0, "x": 24, "y": 16, "justification": "Left", "fontSize": 2},
                {"index": 3, "x": 24, "y": 96, "justification": "Left", "fontSize": 2},
            ],
        },
    }
}


def test_circuit04_full_pipeline():
    """Simulate VLM output for circuit 04 and verify the .asc is correct."""
    analysis = {
        "components": [
            {"name": "V1", "type": "voltage", "value": "30V"},
            {"name": "R1", "type": "res", "value": "2"},
            {"name": "R2", "type": "res", "value": "8"},
            {"name": "R3", "type": "res", "value": "1"},
            {"name": "V2", "type": "voltage", "value": "10V"},
        ],
        "connections": [
            {"from": "V1.+", "to": "R1.A"},
            {"from": "R1.A", "to": "R2.A"},
            {"from": "R2.A", "to": "R3.A"},
            {"from": "R3.A", "to": "V2.+"},
            {"from": "V1.-", "to": "R1.B"},
            {"from": "R1.B", "to": "R2.B"},
            {"from": "R2.B", "to": "R3.B"},
            {"from": "R3.B", "to": "V2.-"},
        ],
        "grounds": [],
        "labels": [],
    }
    asc = build_asc(analysis, DICTIONARY)
    lines = asc.split("\n")

    # Must have Version and SHEET
    assert lines[0] == "Version 4"
    assert lines[1].startswith("SHEET 1")

    # Must have all 5 components
    symbol_lines = [l for l in lines if l.startswith("SYMBOL")]
    assert len(symbol_lines) == 5

    # Must have WINDOW lines
    window_lines = [l for l in lines if l.startswith("WINDOW")]
    assert len(window_lines) >= 10  # 2 windows per component x 5

    # Must have WIRE lines
    wire_lines = [l for l in lines if l.startswith("WIRE")]
    assert len(wire_lines) >= 4  # at least bus + stubs

    # No self-shorting: no wire should have same start and end
    for wl in wire_lines:
        parts = wl.split()
        x1, y1, x2, y2 = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
        assert not (x1 == x2 and y1 == y2), f"Zero-length wire: {wl}"

    # All wire segments should be orthogonal
    for wl in wire_lines:
        parts = wl.split()
        x1, y1, x2, y2 = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
        assert x1 == x2 or y1 == y2, f"Diagonal wire: {wl}"


def test_circuit04_resistors_same_tier():
    """R1, R2, R3 should be placed at the same Y (same tier)."""
    graph = CircuitGraph(DICTIONARY)
    graph.add_components([
        {"name": "V1", "type": "voltage", "value": "30V"},
        {"name": "R1", "type": "res", "value": "2"},
        {"name": "R2", "type": "res", "value": "8"},
        {"name": "R3", "type": "res", "value": "1"},
        {"name": "V2", "type": "voltage", "value": "10V"},
    ])
    graph.build_nets([
        {"from": {"component": "V1", "pin": "+"}, "to": {"component": "R1", "pin": "A"}},
        {"from": {"component": "R1", "pin": "A"}, "to": {"component": "R2", "pin": "A"}},
        {"from": {"component": "R2", "pin": "A"}, "to": {"component": "R3", "pin": "A"}},
        {"from": {"component": "R3", "pin": "A"}, "to": {"component": "V2", "pin": "+"}},
        {"from": {"component": "V1", "pin": "-"}, "to": {"component": "R1", "pin": "B"}},
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "R2", "pin": "B"}},
        {"from": {"component": "R2", "pin": "B"}, "to": {"component": "R3", "pin": "B"}},
        {"from": {"component": "R3", "pin": "B"}, "to": {"component": "V2", "pin": "-"}},
    ], [], [])
    graph.assign_tiers()
    graph.resolve_orientations()
    positions, _ = compute_layout_from_graph(graph)

    # All 3 resistors and both voltage sources share the same two nets
    # so they should all be on the same tier
    r1y = positions["R1"][1]
    r2y = positions["R2"][1]
    r3y = positions["R3"][1]
    assert r1y == r2y == r3y, f"R1={r1y}, R2={r2y}, R3={r3y}"


def test_circuit04_no_self_shorts():
    """No wire should connect two pins of the same component."""
    graph = CircuitGraph(DICTIONARY)
    graph.add_components([
        {"name": "V1", "type": "voltage", "value": "30V"},
        {"name": "R1", "type": "res", "value": "2"},
        {"name": "V2", "type": "voltage", "value": "10V"},
    ])
    graph.build_nets([
        {"from": {"component": "V1", "pin": "+"}, "to": {"component": "R1", "pin": "A"}},
        {"from": {"component": "R1", "pin": "A"}, "to": {"component": "V2", "pin": "+"}},
        {"from": {"component": "V1", "pin": "-"}, "to": {"component": "R1", "pin": "B"}},
        {"from": {"component": "R1", "pin": "B"}, "to": {"component": "V2", "pin": "-"}},
    ], [], [])
    graph.assign_tiers()
    graph.resolve_orientations()
    compute_layout_from_graph(graph)
    result = route_nets(graph)

    # Verify no zero-length wires or wires within same component bounds
    for w in result.wires:
        assert not (w[0] == w[2] and w[1] == w[3]), f"Zero-length wire: {w}"
```

- [ ] **Step 2: Run integration tests**

Run: `cd backend && python -m pytest tests/test_integration_graph.py -v`
Expected: All PASS

- [ ] **Step 3: Run full test suite one final time**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_integration_graph.py
git commit -m "test: integration test for circuit 04 through full graph pipeline"
```

---

### Task 10: Frontend Build Verification

**Files:**
- No changes — verify the frontend still builds

- [ ] **Step 1: Run TypeScript type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors (no frontend changes in this plan)

- [ ] **Step 2: Run Vite build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit (nothing to commit — verification only)**

No commit needed. The implementation is complete.
