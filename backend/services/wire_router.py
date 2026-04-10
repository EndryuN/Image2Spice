from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from services.schemas import normalize_pin

if TYPE_CHECKING:
    from services.circuit_graph import CircuitGraph

logger = logging.getLogger(__name__)

_COLLINEAR_THRESHOLD = 80  # max deviation in px to be considered collinear


@dataclass
class WireResult:
    wires: list[tuple[int, int, int, int]] = field(default_factory=list)
    flags: list[dict] = field(default_factory=list)


# ── Pin position helpers ─────────────────────────────────────────────────────

def _abs_pin_pos(
    comp_x: int,
    comp_y: int,
    pin: dict,
    rotation: str,
    symbol_size: tuple[int, int],
) -> tuple[int, int]:
    """Compute absolute pin position given component origin, pin def, rotation, and symbol size."""
    px, py = pin["x"], pin["y"]
    w, h = symbol_size
    if rotation == "R90":
        px, py = py, w - px
    elif rotation == "R180":
        px, py = w - px, h - py
    elif rotation == "R270":
        px, py = h - py, px
    return (comp_x + int(px), comp_y + int(py))


def _resolve_pin(node, pin_name: str) -> dict | None:
    """Find a pin dict on a component node by name (case-insensitive + alias)."""
    for pin in node.pins:
        if pin["name"].lower() == pin_name.lower():
            return pin
    # Try alias normalization
    normalized = normalize_pin(node.type, pin_name)
    for pin in node.pins:
        if pin["name"].lower() == normalized.lower():
            return pin
    return None


def _get_pin_abs(graph: "CircuitGraph", comp_name: str, pin_name: str) -> tuple[int, int] | None:
    """Get absolute position of a specific pin on a placed component."""
    node = graph.components.get(comp_name)
    if node is None or node.position is None:
        return None
    pin = _resolve_pin(node, pin_name)
    if pin is None:
        return None
    return _abs_pin_pos(
        node.position[0], node.position[1],
        pin, node.resolved_rotation, node.symbol_size,
    )


# ── Routing helpers ──────────────────────────────────────────────────────────

def _l_route(x1: int, y1: int, x2: int, y2: int) -> list[tuple[int, int, int, int]]:
    """Create an L-shaped orthogonal route between two points."""
    if x1 == x2 or y1 == y2:
        return [(x1, y1, x2, y2)]
    # Horizontal first, then vertical
    return [(x1, y1, x2, y1), (x2, y1, x2, y2)]


def _bus_route_horizontal(
    pin_positions: list[tuple[int, int]],
) -> list[tuple[int, int, int, int]]:
    """Route pins along a horizontal bus (similar Y). Sort by X, draw main bus, add vertical stubs."""
    if len(pin_positions) < 2:
        return []

    sorted_pins = sorted(pin_positions, key=lambda p: p[0])
    bus_y = sorted_pins[0][1]  # use first pin's Y as bus level

    wires: list[tuple[int, int, int, int]] = []
    # Main bus wire from leftmost to rightmost
    wires.append((sorted_pins[0][0], bus_y, sorted_pins[-1][0], bus_y))

    # Perpendicular stubs for pins not on bus_y
    for px, py in sorted_pins:
        if py != bus_y:
            wires.append((px, py, px, bus_y))

    return wires


def _bus_route_vertical(
    pin_positions: list[tuple[int, int]],
) -> list[tuple[int, int, int, int]]:
    """Route pins along a vertical bus (similar X). Sort by Y, draw main bus, add horizontal stubs."""
    if len(pin_positions) < 2:
        return []

    sorted_pins = sorted(pin_positions, key=lambda p: p[1])
    bus_x = sorted_pins[0][0]  # use first pin's X as bus level

    wires: list[tuple[int, int, int, int]] = []
    # Main bus wire from top to bottom
    wires.append((bus_x, sorted_pins[0][1], bus_x, sorted_pins[-1][1]))

    # Perpendicular stubs for pins not on bus_x
    for px, py in sorted_pins:
        if px != bus_x:
            wires.append((px, py, bus_x, py))

    return wires


def _stub_cost(pin_positions: list[tuple[int, int]], axis: str) -> int:
    """Compute total stub length for a given bus axis."""
    if axis == "horizontal":
        bus_y = pin_positions[0][1]
        return sum(abs(py - bus_y) for _, py in pin_positions)
    else:
        bus_x = pin_positions[0][0]
        return sum(abs(px - bus_x) for px, _ in pin_positions)


def _deduplicate_wires(
    wires: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    """Remove duplicate wires (order-independent)."""
    seen: set[tuple[int, int, int, int]] = set()
    result: list[tuple[int, int, int, int]] = []
    for w in wires:
        normalized = (min(w[0], w[2]), min(w[1], w[3]), max(w[0], w[2]), max(w[1], w[3]))
        if normalized not in seen:
            seen.add(normalized)
            result.append(w)
    return result


# ── Main net-aware router ────────────────────────────────────────────────────

def route_nets(graph: "CircuitGraph") -> WireResult:
    """Route wires for all nets in the circuit graph.

    Requires that components have been placed (node.position set).
    """
    result = WireResult()

    for net_name, net in graph.nets.items():
        # Collect absolute pin positions for this net
        pin_positions: list[tuple[int, int]] = []
        pin_components: list[str] = []

        for comp_name, pin_name in net.pins:
            pos = _get_pin_abs(graph, comp_name, pin_name)
            if pos is not None:
                pin_positions.append(pos)
                pin_components.append(comp_name)

        if len(pin_positions) < 2:
            # Single-pin nets: handle ground/label flags below
            pass
        else:
            # Skip self-short nets (all pins on same component)
            unique_comps = set(pin_components)
            if len(unique_comps) <= 1:
                continue

            # Check collinearity
            xs = [p[0] for p in pin_positions]
            ys = [p[1] for p in pin_positions]
            x_range = max(xs) - min(xs)
            y_range = max(ys) - min(ys)

            if y_range <= _COLLINEAR_THRESHOLD and len(pin_positions) >= 2:
                # Horizontal bus
                result.wires.extend(_bus_route_horizontal(pin_positions))
            elif x_range <= _COLLINEAR_THRESHOLD and len(pin_positions) >= 2:
                # Vertical bus
                result.wires.extend(_bus_route_vertical(pin_positions))
            elif len(pin_positions) == 2:
                # L-shaped route for 2-pin non-collinear nets
                p1, p2 = pin_positions
                result.wires.extend(_l_route(p1[0], p1[1], p2[0], p2[1]))
            else:
                # Multi-pin non-collinear: pick best bus axis
                h_cost = _stub_cost(pin_positions, "horizontal")
                v_cost = _stub_cost(pin_positions, "vertical")
                if h_cost <= v_cost:
                    result.wires.extend(_bus_route_horizontal(pin_positions))
                else:
                    result.wires.extend(_bus_route_vertical(pin_positions))

        # Ground nets: add flag with 32px stub wire
        if net_name == "0":
            # Place ground flag at first pin
            if pin_positions:
                px, py = pin_positions[0]
                result.wires.append((px, py, px, py + 32))
                result.flags.append({"name": "0", "x": px, "y": py + 32})

        # Named nets (not auto-generated, not ground): add label flag at first pin
        elif not net_name.startswith("net_") and not net_name.startswith("_virtual_"):
            if pin_positions:
                px, py = pin_positions[0]
                result.flags.append({"name": net_name, "x": px, "y": py})

    # Deduplicate wires
    result.wires = _deduplicate_wires(result.wires)

    return result


# ── Legacy wrapper ───────────────────────────────────────────────────────────

def _find_pin_by_name(pins: list[dict], comp_type: str, pin_name: str) -> dict | None:
    """Try to match a pin by name using multiple strategies."""
    if not pins:
        return None

    pin_lower = pin_name.lower().strip()

    # Exact case-insensitive match
    for pin in pins:
        if pin["name"].lower() == pin_lower:
            return pin

    # Normalize through aliases
    normalized = normalize_pin(comp_type, pin_name)
    if normalized != pin_name:
        for pin in pins:
            if pin["name"].lower() == normalized.lower():
                return pin

    # Numeric index
    if pin_lower.isdigit():
        idx = int(pin_lower)
        for pin in pins:
            if pin.get("spiceOrder") == idx:
                return pin
        if 1 <= idx <= len(pins):
            return pins[idx - 1]

    return None


def compute_wires(
    components: dict[str, dict],
    pin_defs: dict[str, list[dict]],
    connections_data: dict,
    component_bounds: dict[str, list] | None = None,
    symbol_sizes: dict[str, tuple[int, int]] | None = None,
) -> WireResult:
    """Legacy wire router (no graph required)."""
    result = WireResult()

    def _get_size(comp_type: str) -> tuple[int, int] | None:
        return symbol_sizes.get(comp_type) if symbol_sizes else None

    def _get_comp(name: str) -> dict | None:
        comp = components.get(name)
        if comp:
            return comp
        for k, v in components.items():
            if k.lower() == name.lower():
                return v
        return None

    def _legacy_abs_pin_pos(comp: dict, pin: dict, symbol_size: tuple[int, int] | None = None) -> tuple[int, int]:
        px, py = pin["x"], pin["y"]
        rotation = comp.get("rotation", "R0")
        if rotation != "R0" and symbol_size:
            w, h = symbol_size
            if rotation == "R90":
                px, py = py, w - px
            elif rotation == "R180":
                px, py = w - px, h - py
            elif rotation == "R270":
                px, py = h - py, px
        return (comp["x"] + int(px), comp["y"] + int(py))

    for conn in connections_data.get("connections", []):
        from_name = conn["from"]["component"]
        to_name = conn["to"]["component"]
        from_comp = _get_comp(from_name)
        to_comp = _get_comp(to_name)

        if not from_comp or not to_comp:
            logger.warning("Connection skipped: component not found (%s or %s)", from_name, to_name)
            continue

        from_pins = pin_defs.get(from_comp["type"], [])
        to_pins = pin_defs.get(to_comp["type"], [])

        from_pin = _find_pin_by_name(from_pins, from_comp["type"], conn["from"]["pin"])
        to_pin = _find_pin_by_name(to_pins, to_comp["type"], conn["to"]["pin"])

        if not from_pin or not to_pin:
            logger.warning("No pins available for %s -> %s", from_name, to_name)
            continue

        fx, fy = _legacy_abs_pin_pos(from_comp, from_pin, _get_size(from_comp["type"]))
        tx, ty = _legacy_abs_pin_pos(to_comp, to_pin, _get_size(to_comp["type"]))

        if fx == tx or fy == ty:
            result.wires.append((fx, fy, tx, ty))
        else:
            result.wires.extend([(fx, fy, tx, fy), (tx, fy, tx, ty)])

    for gnd in connections_data.get("grounds", []):
        comp = _get_comp(gnd["component"])
        if not comp:
            continue
        pins = pin_defs.get(comp["type"], [])
        pin = _find_pin_by_name(pins, comp["type"], gnd["pin"])
        if not pin and pins:
            pin = pins[-1]
        if not pin:
            continue
        px, py = _legacy_abs_pin_pos(comp, pin, _get_size(comp["type"]))
        result.wires.append((px, py, px, py + 32))
        result.flags.append({"name": "0", "x": px, "y": py + 32})

    for label in connections_data.get("labels", []):
        comp = _get_comp(label["component"])
        if not comp:
            continue
        pins = pin_defs.get(comp["type"], [])
        pin = _find_pin_by_name(pins, comp["type"], label["pin"])
        if not pin and pins:
            pin = pins[0]
        if not pin:
            continue
        px, py = _legacy_abs_pin_pos(comp, pin, _get_size(comp["type"]))
        result.flags.append({"name": label["label"], "x": px, "y": py})

    return result
