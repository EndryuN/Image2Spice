# Circuit Graph Routing Design

**Date:** 2026-04-10
**Status:** Approved

## Problem

The current wire routing system has critical flaws:
- Wires short components (both pins of the same component connected)
- Wires route through component bodies
- No bus-style routing — individual pairwise L-shaped wires instead of clean buses
- Canvas too small squishes components together
- No T-junction or intersection handling
- Component orientation (pin +/- facing) is taken from VLM verbatim, which is often wrong
- Text labels overlap wires

## Design Decisions

| Question | Choice | Rationale |
|----------|--------|-----------|
| Orientation | Topology-driven | Infer from connectivity graph before layout, not from VLM |
| Canvas sizing | Tier-driven | Compute from circuit tier count and widest tier |
| Wire routing | Hybrid bus/L-shaped | Bus for collinear pins, L-shaped for others |
| Obstacle avoidance | Rely on layout + safety net | Tier spacing prevents most conflicts; post-process catches edge cases |
| VLM-to-nets bridge | Union-find on connections | No VLM prompt changes needed |
| Architecture | Graph-first core | Central `circuit_graph.py` as single source of truth |

## Architecture

```
Image
  -> VLM (Claude Sonnet / qwen3-vl:8b): components + pairwise connections + grounds + labels
  -> circuit_graph.py:
      1. Build component nodes (with dictionary pin defs)
      2. Union-find connections -> nets
      3. Detect flow direction (vertical vs horizontal)
      4. Assign tiers from topology (anchors + connectivity distance)
      5. Resolve component orientations (pin nets -> tier positions)
  -> layout.py (rewritten):
      6. Size canvas from tier count x max tier width
      7. Place components per tier with spacing rules
      8. Horizontal bridging components detected and oriented R90
      9. Snap everything to 16px grid
  -> wire_router.py (rewritten):
      10. For each net, collect absolute pin positions
      11. Collinear pins -> bus wire + stubs
      12. Non-collinear -> L-shaped routing
      13. Post-process: reject self-shorts, check body overlap, deduplicate
  -> asc_generator.py (unchanged):
      14. Emit .asc with WINDOW lines from dictionary
```

## Module: circuit_graph.py (new)

Pure data structure built from VLM connections. No I/O or rendering.

### Data Model

```python
@dataclass
class ComponentNode:
    name: str            # e.g., "R1"
    type: str            # e.g., "res"
    value: str           # e.g., "1k"
    pins: list[dict]     # from dictionary pin defs
    symbol_size: tuple[int, int]  # (width, height) from dictionary
    resolved_rotation: str  # computed from topology, not VLM
    tier: int            # assigned during analysis
    position: tuple[int, int] | None  # assigned during layout

@dataclass
class Net:
    name: str            # auto-generated "net_0" or from labels "VCC", "GND"
    pins: list[tuple[str, str]]  # [(component_name, pin_name), ...]
    orientation: str     # "horizontal" | "vertical" (computed from tier analysis)

@dataclass
class Tier:
    index: int
    components: list[str]  # component names
    y_position: int        # assigned during layout

class CircuitGraph:
    components: dict[str, ComponentNode]
    nets: dict[str, Net]
    tiers: list[Tier]
    flow_direction: str   # "vertical" (top-to-bottom) or "horizontal" (left-to-right)
```

### Construction Steps

1. **Build component nodes** from VLM identification + dictionary pin definitions
2. **Build nets via union-find** on VLM pairwise connections. If V1.+ connects to R1.A and R1.A connects to R2.A, they all merge into one net.
3. **Detect flow direction** — if most nets connect components vertically (same X, different Y) -> vertical flow; if horizontally -> horizontal flow. Default: vertical.
4. **Assign tiers:**
   - Anchor components: voltage sources with ground connections -> tier edges. VCC-connected -> tier 0. Ground-connected -> last tier.
   - Remaining components: tier = number of components on the shortest path to the nearest anchor. For example, if R1 connects directly to V1 (anchor at tier 0), R1 is tier 1. If R2 connects to R1 but not directly to V1, R2 is tier 2. Components sharing the same nets on the same pins -> same tier (parallel components, e.g., R1/R2/R3 in circuit 04 all connect to the same top and bottom nets -> same tier).
   - Within a tier, sort left-to-right by connectivity order.
5. **Resolve orientations:**
   - For each component, check which tier its pin A's net occupies vs pin B's net.
   - If pin A's net is on a higher tier (lower Y) -> R0 (A on top).
   - If pin A's net is on a lower tier -> R180 (A on bottom).
   - If both nets are on the same tier -> R90/R270 (horizontal), direction based on position relative to connected components.

## Module: layout.py (rewritten)

Queries CircuitGraph to place components. Replaces current percentage-based positioning.

### Canvas Sizing

```python
TIER_SPACING = 160    # vertical distance between tiers
COMP_SPACING = 128    # horizontal distance within a tier
MARGIN = 64           # canvas edge padding
GRID = 16             # LTspice snap grid

height = MARGIN + (num_tiers * TIER_SPACING) + MARGIN
width = MARGIN + (max_components_in_any_tier * COMP_SPACING) + MARGIN
```

Canvas grows to fit the circuit. Minimum 800x600.

### Placement Rules

1. Each tier gets a Y position: `y = MARGIN + tier_index * TIER_SPACING`
2. Components within a tier are centered horizontally on the canvas
3. Components spanning multiple tiers (e.g., voltage sources connecting tier 0 and tier N): Y position is midpoint between their top and bottom tier
4. Spanning components placed at left/right margins, not mixed with mid-tier components
5. All positions snapped to 16px grid
6. Minimum 128px between component centers horizontally

### Horizontal Bridging

When a component's two pins connect to nets in the same tier but at different horizontal positions:
- Orient R90 (horizontal)
- Place it spanning between those positions
- This handles resistors/inductors across the top of circuits (e.g., test images 03, 07, 08)

## Module: wire_router.py (rewritten)

Net-aware hybrid routing that queries CircuitGraph.

### Routing Algorithm

For each net in the circuit graph:

1. **Collect absolute pin positions** for all pins in the net (using component position + pin offset + rotation transform)
2. **Check collinearity** — are all pins within half a TIER_SPACING (80px) of the same Y (horizontal bus) or same X (vertical bus)?
3. **If collinear -> bus route:**
   - Sort pins by position along the bus axis
   - Draw one straight wire from first to last pin
   - For pins not exactly on the bus line, add perpendicular stubs
4. **If not collinear -> L-shaped/Z-shaped:**
   - For 2-pin nets: single L-shaped route (horizontal then vertical)
   - For 3+ pin nets: pick the bus line (Y or X) that minimizes total stub length, route bus, add stubs

### Post-Processing

- **Self-short rejection:** If both endpoints of a proposed wire are pins on the same component, skip it
- **Body overlap check:** If a wire segment intersects a component bounding box (excluding that component's own pins), offset the wire by component width + 16px
- **Deduplication:** Remove duplicate or overlapping wire segments
- **Junction detection:** Where 3+ wires meet at a point, that's a valid T-junction (no special handling needed in .asc format, LTspice infers junctions)

## Topology Patterns

The system handles these patterns from the ground truth test images:

| Pattern | Circuits | How Handled |
|---------|----------|-------------|
| Two-bus parallel | 03, 04, 07, 08 | Two tiers, bus routing on each tier |
| Horizontal bridging | 03, 07, 08 | Detected as same-tier-different-X, component oriented R90 |
| Signal-flow (L-to-R) | 02, 05, 06 | Flow direction = horizontal, tiers become vertical columns |
| Diamond/bridge | 01 | Approximated as rectangular: 2 components top tier, 2 bottom tier, both R90 |

## Files Changed

| File | Change |
|------|--------|
| `backend/services/circuit_graph.py` | **New** — core data model, union-find, tier analysis, orientation resolution |
| `backend/services/layout.py` | **Rewritten** — tier-based placement, auto-sizing canvas |
| `backend/services/wire_router.py` | **Rewritten** — net-aware hybrid bus/L-shaped routing |
| `backend/services/schematic_builder.py` | **Updated** — use CircuitGraph instead of direct VLM data |
| `backend/api/wizard_routes.py` | **Updated** — wire endpoint constructs CircuitGraph, passes to layout + router |
| `backend/tests/test_circuit_graph.py` | **New** — unit tests for graph construction, tier assignment, orientation |
| `backend/tests/test_layout.py` | **Updated** — tests for tier-based placement |
| `backend/tests/test_wire_router.py` | **Updated** — tests for net-aware routing |

## Files Unchanged

- `backend/services/asc_generator.py` — deterministic .asc emission, already works
- `backend/services/llm_client.py` — provider system already supports Claude
- `backend/services/vision.py` — VLM calls unchanged
- `backend/prompts/*` — no prompt changes needed
- `frontend/*` — no frontend changes (text positioning already fixed)
- `dictionary/*` — component definitions unchanged

## Test Strategy

1. **Unit tests for circuit_graph.py:** Build graph from known connections, verify nets, tiers, orientations
2. **Unit tests for layout.py:** Verify canvas sizing, component placement, spacing rules
3. **Unit tests for wire_router.py:** Verify bus detection, routing, self-short rejection
4. **Integration test:** Run ground truth image 04 (parallel resistors) through full pipeline, compare .asc output
5. **Visual validation:** Test all 8 ground truth images through the app with Claude Sonnet
