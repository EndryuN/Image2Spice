from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.circuit_graph import CircuitGraph

TIER_SPACING = 256
COMP_SPACING = 160
MARGIN = 80
GRID = 16
MIN_WIDTH = 800
MIN_HEIGHT = 600


def _snap(value: int) -> int:
    return round(value / GRID) * GRID


def compute_layout_from_graph(
    graph: "CircuitGraph",
) -> tuple[dict[str, tuple[int, int]], tuple[int, int]]:
    """Place components on a grid using tier information from the circuit graph.

    Spanning components (those connecting nets on different tiers, e.g. voltage
    sources) are placed at the left/right edges.  Non-spanning components are
    spread evenly between them.

    Returns (positions dict mapping name->(x,y), sheet_size (width, height)).
    Also sets node.position and tier.y_position on the graph objects.
    """
    positions: dict[str, tuple[int, int]] = {}

    if not graph.components:
        return positions, (MIN_WIDTH, MIN_HEIGHT)

    if not graph.tiers:
        names = list(graph.components.keys())
        total_w = (len(names) - 1) * COMP_SPACING if len(names) > 1 else 0
        width = max(MIN_WIDTH, MARGIN + total_w + MARGIN)
        start_x = (width - total_w) // 2
        y = _snap(MARGIN)
        for i, name in enumerate(names):
            x = _snap(start_x + i * COMP_SPACING)
            positions[name] = (x, y)
            graph.components[name].position = (x, y)
        return positions, (width, MIN_HEIGHT)

    num_tiers = len(graph.tiers)

    # ── Identify edge components ──────────────────────────────────────
    # Source components (voltage, current) that span multiple tiers are
    # placed at the left/right edges of the canvas.
    _EDGE_TYPES = {"voltage", "current"}
    spanning: list[str] = []
    non_spanning: dict[int, list[str]] = {}  # tier_index -> [names]

    for tier in graph.tiers:
        for name in tier.components:
            node = graph.components[name]
            if node.type in _EDGE_TYPES and len(node.pins) >= 2:
                pin_a = (name, node.pins[0]["name"])
                pin_b = (name, node.pins[-1]["name"])
                net_a = graph._pin_net.get(pin_a)
                net_b = graph._pin_net.get(pin_b)
                tier_a = graph._net_tiers.get(net_a, 0) if net_a else 0
                tier_b = graph._net_tiers.get(net_b, 0) if net_b else 0
                if tier_a != tier_b:
                    spanning.append(name)
                    continue
            non_spanning.setdefault(tier.index, []).append(name)

    # ── Count total components in widest row ─────────────────────────────
    max_non_spanning = max((len(v) for v in non_spanning.values()), default=0)
    # Total horizontal slots = spanning edges + non-spanning middle
    total_slots = len(spanning) + max_non_spanning
    total_slots = max(total_slots, 1)

    # ── Auto-size canvas ────────────────────────────────────────────────
    width = _snap(max(MIN_WIDTH, MARGIN + total_slots * COMP_SPACING + MARGIN))
    height = _snap(max(MIN_HEIGHT, MARGIN + num_tiers * TIER_SPACING + MARGIN))

    # ── Compute ideal Y for each tier ──────────────────────────────────
    # If a tier has spanning components, the ideal Y is the midpoint
    # between the net-tiers they span. Non-spanning components on the
    # same tier share that Y so all pins align on the same buses.
    tier_y: dict[int, int] = {}
    for tier in graph.tiers:
        tier_y[tier.index] = _snap(MARGIN + tier.index * TIER_SPACING)

    # Check if any spanning component defines a better Y for its tier
    spanning_y: int | None = None
    for name in spanning:
        node = graph.components[name]
        pin_a = (name, node.pins[0]["name"])
        pin_b = (name, node.pins[-1]["name"])
        net_a = graph._pin_net.get(pin_a)
        net_b = graph._pin_net.get(pin_b)
        tier_a = graph._net_tiers.get(net_a, 0) if net_a else 0
        tier_b = graph._net_tiers.get(net_b, 0) if net_b else 0
        y_top = _snap(MARGIN + min(tier_a, tier_b) * TIER_SPACING)
        y_bot = _snap(MARGIN + max(tier_a, tier_b) * TIER_SPACING)
        spanning_y = _snap((y_top + y_bot) // 2)
        # Update tier Y for the tier these components are on
        comp_tier = node.tier
        tier_y[comp_tier] = spanning_y

    for tier in graph.tiers:
        tier.y_position = tier_y.get(tier.index, _snap(MARGIN + tier.index * TIER_SPACING))

    # ── Place spanning components at left/right edges ───────────────────
    for i, name in enumerate(spanning):
        node = graph.components[name]
        y = tier_y.get(node.tier, _snap(MARGIN))

        if len(spanning) == 1:
            x = _snap(MARGIN)
        elif i == 0:
            x = _snap(MARGIN)
        else:
            x = _snap(width - MARGIN - node.symbol_size[0])

        positions[name] = (x, y)
        node.position = (x, y)

    # ── Place non-spanning components between the edges ──────────────────
    if spanning:
        left_edge = MARGIN + COMP_SPACING
        right_edge = width - MARGIN - COMP_SPACING
        if len(spanning) == 1:
            right_edge = width - MARGIN
    else:
        left_edge = MARGIN
        right_edge = width - MARGIN

    for tier_idx, names in non_spanning.items():
        n = len(names)
        if n == 0:
            continue

        y = tier_y.get(tier_idx, _snap(MARGIN + tier_idx * TIER_SPACING))

        if n == 1:
            x = _snap((left_edge + right_edge) // 2)
            positions[names[0]] = (x, y)
            graph.components[names[0]].position = (x, y)
        else:
            spacing = (right_edge - left_edge) // max(n - 1, 1)
            spacing = max(spacing, COMP_SPACING)
            for i, name in enumerate(names):
                x = _snap(left_edge + i * spacing)
                positions[name] = (x, y)
                graph.components[name].position = (x, y)

    return positions, (width, height)


# ── Legacy wrapper ───────────────────────────────────────────────────────────

def compute_layout(
    layout_desc: list[dict],
    component_sizes: dict[str, dict],
    sheet_width: int = 880,
    sheet_height: int = 680,
) -> dict[str, dict]:
    """Legacy grid-based layout (no graph required)."""
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
