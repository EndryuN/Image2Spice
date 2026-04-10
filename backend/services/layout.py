from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.circuit_graph import CircuitGraph

TIER_SPACING = 160
COMP_SPACING = 128
MARGIN = 64
GRID = 16
MIN_WIDTH = 800
MIN_HEIGHT = 600


def _snap(value: int) -> int:
    return round(value / GRID) * GRID


def compute_layout_from_graph(
    graph: "CircuitGraph",
) -> tuple[dict[str, tuple[int, int]], tuple[int, int]]:
    """Place components on a grid using tier information from the circuit graph.

    Returns (positions dict mapping name->(x,y), sheet_size (width, height)).
    Also sets node.position and tier.y_position on the graph objects.
    """
    positions: dict[str, tuple[int, int]] = {}

    if not graph.components:
        return positions, (MIN_WIDTH, MIN_HEIGHT)

    if not graph.tiers:
        # No tiers: place all components in a single row
        names = list(graph.components.keys())
        total_width = (len(names) - 1) * COMP_SPACING if len(names) > 1 else 0
        width = max(MIN_WIDTH, MARGIN + total_width + MARGIN)
        height = MIN_HEIGHT
        start_x = (width - total_width) // 2
        y = _snap(MARGIN)
        for i, name in enumerate(names):
            x = _snap(start_x + i * COMP_SPACING)
            positions[name] = (x, y)
            graph.components[name].position = (x, y)
        return positions, (width, height)

    # Find the maximum number of components in any tier
    max_in_tier = max(len(tier.components) for tier in graph.tiers)
    num_tiers = len(graph.tiers)

    # Auto-size canvas
    width = max(MIN_WIDTH, MARGIN + max_in_tier * COMP_SPACING + MARGIN)
    height = max(MIN_HEIGHT, MARGIN + num_tiers * TIER_SPACING + MARGIN)

    for tier in graph.tiers:
        y = _snap(MARGIN + tier.index * TIER_SPACING)
        tier.y_position = y

        n = len(tier.components)
        total_width = (n - 1) * COMP_SPACING if n > 1 else 0
        start_x = (width - total_width) // 2

        for i, name in enumerate(tier.components):
            x = _snap(start_x + i * COMP_SPACING)
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
