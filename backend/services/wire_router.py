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
    bounds: list | None = None,
) -> tuple[int, int]:
    """Compute absolute pin position given component origin, pin def, rotation, and symbol size.

    Pin coords in the dictionary are in LTspice local space.  The SVG path
    is shifted so that bounds.min is at (0,0).  Apply the same shift here
    so wires connect at the visual pin locations.
    """
    px, py = float(pin["x"]), float(pin["y"])
    # Convert from LTspice coords to SVG coords using bounds offset
    if bounds:
        px = px - bounds[0]
        py = py - bounds[1]
    w, h = symbol_size
    # Rotate around SVG bounding box center — must match the SVG
    # rotate(θ, cx, cy) transform used in the frontend Editor
    cx, cy = w / 2, h / 2
    if rotation == "R90":
        px, py = cx - (py - cy), cy + (px - cx)
    elif rotation == "R180":
        px, py = 2 * cx - px, 2 * cy - py
    elif rotation == "R270":
        px, py = cx + (py - cy), cy - (px - cx)
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
    # Get bounds from dictionary for coordinate offset
    comp_def = graph._dictionary.get("components", {}).get(node.type, {})
    bounds = comp_def.get("geometry", {}).get("bounds")
    return _abs_pin_pos(
        node.position[0], node.position[1],
        pin, node.resolved_rotation, node.symbol_size, bounds,
    )


# ── Routing helpers ──────────────────────────────────────────────────────────

def _l_route(x1: int, y1: int, x2: int, y2: int) -> list[tuple[int, int, int, int]]:
    """Create an L-shaped orthogonal route between two points."""
    if x1 == x2 or y1 == y2:
        return [(x1, y1, x2, y2)]
    # Horizontal first, then vertical
    return [(x1, y1, x2, y1), (x2, y1, x2, y2)]


def _most_common(values: list[int]) -> int:
    """Return the most frequently occurring value (mode)."""
    from collections import Counter
    counts = Counter(values)
    return counts.most_common(1)[0][0]


_BUS_GAP = 16  # gap between bus and nearest pin


def _best_bus_y(pin_positions: list[tuple[int, int]]) -> int:
    """Pick the best horizontal bus Y.

    If all pins share the same Y, use that Y (pure horizontal bus).
    Otherwise, place the bus outside the pin cluster — above the topmost
    pin or below the bottommost — whichever produces shorter total stubs.
    """
    ys = [py for _, py in pin_positions]
    if max(ys) == min(ys):
        return ys[0]  # All pins aligned — bus at their level

    # Try bus above (min Y - gap) vs below (max Y + gap)
    bus_above = min(ys) - _BUS_GAP
    bus_below = max(ys) + _BUS_GAP
    cost_above = sum(abs(y - bus_above) for y in ys)
    cost_below = sum(abs(y - bus_below) for y in ys)

    return bus_above if cost_above <= cost_below else bus_below


def _best_bus_x(pin_positions: list[tuple[int, int]]) -> int:
    """Pick the best vertical bus X."""
    xs = [px for px, _ in pin_positions]
    if max(xs) == min(xs):
        return xs[0]
    bus_left = min(xs) - _BUS_GAP
    bus_right = max(xs) + _BUS_GAP
    cost_left = sum(abs(x - bus_left) for x in xs)
    cost_right = sum(abs(x - bus_right) for x in xs)
    return bus_left if cost_left <= cost_right else bus_right


def _bus_route_horizontal(
    pin_positions: list[tuple[int, int]],
) -> list[tuple[int, int, int, int]]:
    """Route pins along a horizontal bus. Pick the Y most pins share as the bus level."""
    if len(pin_positions) < 2:
        return []

    sorted_pins = sorted(pin_positions, key=lambda p: p[0])
    bus_y = _best_bus_y(pin_positions)

    wires: list[tuple[int, int, int, int]] = []
    # Main bus wire from leftmost to rightmost X at bus_y
    wires.append((sorted_pins[0][0], bus_y, sorted_pins[-1][0], bus_y))

    # Vertical stubs for pins not on bus_y
    for px, py in sorted_pins:
        if py != bus_y:
            wires.append((px, py, px, bus_y))

    return wires


def _bus_route_vertical(
    pin_positions: list[tuple[int, int]],
) -> list[tuple[int, int, int, int]]:
    """Route pins along a vertical bus. Pick the X most pins share as the bus level."""
    if len(pin_positions) < 2:
        return []

    sorted_pins = sorted(pin_positions, key=lambda p: p[1])
    bus_x = _best_bus_x(pin_positions)

    wires: list[tuple[int, int, int, int]] = []
    wires.append((bus_x, sorted_pins[0][1], bus_x, sorted_pins[-1][1]))

    for px, py in sorted_pins:
        if px != bus_x:
            wires.append((px, py, bus_x, py))

    return wires


def _stub_cost_h(pin_positions: list[tuple[int, int]]) -> int:
    """Total vertical stub length if we route as a horizontal bus."""
    ys = [py for _, py in pin_positions]
    # Cost for bus above vs below
    bus_above = min(ys) - _BUS_GAP
    bus_below = max(ys) + _BUS_GAP
    return min(
        sum(abs(y - bus_above) for y in ys),
        sum(abs(y - bus_below) for y in ys),
    )


def _stub_cost_v(pin_positions: list[tuple[int, int]]) -> int:
    """Total horizontal stub length if we route as a vertical bus."""
    xs = [px for px, _ in pin_positions]
    bus_left = min(xs) - _BUS_GAP
    bus_right = max(xs) + _BUS_GAP
    return min(
        sum(abs(x - bus_left) for x in xs),
        sum(abs(x - bus_right) for x in xs),
    )


def _route_net_with_direct_wires(
    pin_positions: list[tuple[int, int]],
    pin_components: list[str],
) -> list[tuple[int, int, int, int]]:
    """Route a multi-pin net: direct wires for aligned pins, bus for the rest.

    1. Find vertically-aligned pin pairs (same X) → direct vertical wires
    2. Find horizontally-aligned pin pairs (same Y) → direct horizontal wires
    3. Draw a bus connecting all column/row endpoints
    4. Add stubs only for pins not already on the bus line
    """
    _ALIGN = 16
    wires: list[tuple[int, int, int, int]] = []

    # Group pins by X coordinate (columns)
    columns: dict[int, list[tuple[int, int, int]]] = {}  # x -> [(x, y, index)]
    for i, (px, py) in enumerate(pin_positions):
        # Snap to nearest column
        placed = False
        for col_x in list(columns.keys()):
            if abs(px - col_x) <= _ALIGN:
                columns[col_x].append((px, py, i))
                placed = True
                break
        if not placed:
            columns[px] = [(px, py, i)]

    # Draw direct vertical wires within each column (between different components)
    column_endpoints: list[tuple[int, int]] = []  # points that need bus connection
    for col_x, col_pins in columns.items():
        if len(col_pins) >= 2:
            # Sort by Y and connect adjacent pins vertically
            col_pins.sort(key=lambda p: p[1])
            for k in range(len(col_pins) - 1):
                _, y1, i1 = col_pins[k]
                _, y2, i2 = col_pins[k + 1]
                if pin_components[i1] != pin_components[i2]:
                    wires.append((col_x, y1, col_x, y2))
            # The top and bottom of this column need bus connection
            column_endpoints.append((col_x, col_pins[0][1]))   # topmost
            column_endpoints.append((col_x, col_pins[-1][1]))  # bottommost
        else:
            # Single pin in this column — needs bus connection
            column_endpoints.append((col_pins[0][0], col_pins[0][1]))

    # If all pins are in one column, we're done (direct wires handle it)
    unique_x = set(p[0] for p in column_endpoints)
    if len(unique_x) <= 1:
        return _deduplicate_wires(wires)

    # Reduce endpoints to one per column — pick the one closest to the bus
    # (the direct wire already connects the rest of the column)
    best_per_col: dict[int, tuple[int, int]] = {}
    for col_x in columns:
        col_pins = columns[col_x]
        # Pick the endpoint closest to where a bus would be (topmost = smallest Y)
        topmost = min(col_pins, key=lambda p: p[1])
        bottommost = max(col_pins, key=lambda p: p[1])
        best_per_col[col_x] = (col_x, topmost[1])  # tentative — refine after bus Y

    bus_candidates = list(best_per_col.values())
    all_ys = [p[1] for p in bus_candidates]
    bus_above = min(all_ys) - _BUS_GAP
    bus_below = max(all_ys) + _BUS_GAP
    cost_above = sum(abs(y - bus_above) for y in all_ys)
    cost_below = sum(abs(y - bus_below) for y in all_ys)
    bus_y = bus_above if cost_above <= cost_below else bus_below

    # Now pick the column endpoint closest to the bus_y
    bus_points: list[tuple[int, int]] = []
    for col_x, col_pins in columns.items():
        closest = min(col_pins, key=lambda p: abs(p[1] - bus_y))
        bus_points.append((col_x, closest[1]))

    # Main bus wire
    sorted_by_x = sorted(bus_points, key=lambda p: p[0])
    wires.append((sorted_by_x[0][0], bus_y, sorted_by_x[-1][0], bus_y))

    # One stub per column from the closest pin to the bus
    for px, py in bus_points:
        if py != bus_y:
            wires.append((px, py, px, bus_y))

    return _deduplicate_wires(wires)


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


# ── Image-aware router (uses VLM wire path descriptions) ────────────────────

def route_with_paths(
    graph: "CircuitGraph",
    wire_paths: list[dict],
    buses: list[dict],
    connections: list[dict],
    grounds: list[dict] | None = None,
    labels: list[dict] | None = None,
    sheet_width: int = 880,
    sheet_height: int = 680,
) -> WireResult:
    """Route wires using VLM-described wire paths from the source image.

    wire_paths: [{from_pin, to_pin, path, bus_y/bus_x}, ...]
    buses: [{orientation, y_pct/x_pct, connects: [pin_refs]}, ...]
    """
    result = WireResult()
    _MARGIN = 48
    routed_pairs: set[tuple[str, str]] = set()

    def _parse_ref(ref: str) -> tuple[str, str] | None:
        parts = ref.rsplit(".", 1)
        return (parts[0], parts[1]) if len(parts) == 2 else None

    def _pct_to_y(pct: float) -> int:
        return round(_MARGIN + (pct / 100) * (sheet_height - 2 * _MARGIN) / 16) * 16

    def _pct_to_x(pct: float) -> int:
        return round(_MARGIN + (pct / 100) * (sheet_width - 2 * _MARGIN) / 16) * 16

    # Step 1: Route buses first
    for bus in buses:
        orientation = bus.get("orientation", "horizontal")
        pin_refs = bus.get("connects", [])
        pin_positions: list[tuple[int, int]] = []

        for ref in pin_refs:
            parsed = _parse_ref(ref) if isinstance(ref, str) else None
            if parsed:
                pos = _get_pin_abs(graph, parsed[0], parsed[1])
                if pos:
                    pin_positions.append(pos)

        if len(pin_positions) < 2:
            continue

        if orientation == "horizontal":
            bus_y_pct = bus.get("y_pct", bus.get("y", 50))
            bus_y = _pct_to_y(float(bus_y_pct))
            sorted_pins = sorted(pin_positions, key=lambda p: p[0])
            # Main bus wire
            result.wires.append((sorted_pins[0][0], bus_y, sorted_pins[-1][0], bus_y))
            # Vertical stubs
            for px, py in sorted_pins:
                if py != bus_y:
                    result.wires.append((px, py, px, bus_y))
        else:
            bus_x_pct = bus.get("x_pct", bus.get("x", 50))
            bus_x = _pct_to_x(float(bus_x_pct))
            sorted_pins = sorted(pin_positions, key=lambda p: p[1])
            result.wires.append((bus_x, sorted_pins[0][1], bus_x, sorted_pins[-1][1]))
            for px, py in sorted_pins:
                if px != bus_x:
                    result.wires.append((px, py, bus_x, py))

        # Mark these connections as routed
        for i in range(len(pin_refs)):
            for j in range(i + 1, len(pin_refs)):
                pair = tuple(sorted([pin_refs[i], pin_refs[j]]))
                routed_pairs.add(pair)

    # Step 2: Route individual wire paths
    for wp in wire_paths:
        from_ref = wp.get("from_pin", wp.get("from", ""))
        to_ref = wp.get("to_pin", wp.get("to", ""))
        path_type = wp.get("path", "L_horizontal_first")

        pair = tuple(sorted([from_ref, to_ref]))
        if pair in routed_pairs:
            continue

        from_parsed = _parse_ref(from_ref) if isinstance(from_ref, str) else None
        to_parsed = _parse_ref(to_ref) if isinstance(to_ref, str) else None
        if not from_parsed or not to_parsed:
            continue

        pos_a = _get_pin_abs(graph, from_parsed[0], from_parsed[1])
        pos_b = _get_pin_abs(graph, to_parsed[0], to_parsed[1])
        if not pos_a or not pos_b:
            continue
        if from_parsed[0] == to_parsed[0]:
            continue  # skip self-shorts

        ax, ay = pos_a
        bx, by = pos_b

        if path_type == "direct_vertical":
            result.wires.append((ax, ay, ax, by))
        elif path_type == "direct_horizontal":
            result.wires.append((ax, ay, bx, ay))
        elif path_type == "L_vertical_first":
            result.wires.append((ax, ay, ax, by))
            result.wires.append((ax, by, bx, by))
        else:  # L_horizontal_first or default
            result.wires.append((ax, ay, bx, ay))
            result.wires.append((bx, ay, bx, by))

        routed_pairs.add(pair)

    # Step 3: Any connections not yet routed — fallback to L-route
    for conn in connections:
        f = conn.get("from", {})
        t = conn.get("to", {})
        if isinstance(f, str) and isinstance(t, str):
            from_ref, to_ref = f, t
        elif isinstance(f, dict) and isinstance(t, dict):
            from_ref = f"{f.get('component','')}.{f.get('pin','')}"
            to_ref = f"{t.get('component','')}.{t.get('pin','')}"
        else:
            continue

        pair = tuple(sorted([from_ref, to_ref]))
        if pair in routed_pairs:
            continue

        from_parsed = _parse_ref(from_ref)
        to_parsed = _parse_ref(to_ref)
        if not from_parsed or not to_parsed:
            continue
        if from_parsed[0] == to_parsed[0]:
            continue

        pos_a = _get_pin_abs(graph, from_parsed[0], from_parsed[1])
        pos_b = _get_pin_abs(graph, to_parsed[0], to_parsed[1])
        if not pos_a or not pos_b:
            continue

        result.wires.extend(_l_route(pos_a[0], pos_a[1], pos_b[0], pos_b[1]))

    # Ground flags
    for gnd in (grounds or []):
        comp_name = gnd.get("component", "")
        pin_name = gnd.get("pin", "")
        pos = _get_pin_abs(graph, comp_name, pin_name)
        if pos:
            px, py = pos
            result.wires.append((px, py, px, py + 32))
            result.flags.append({"name": "0", "x": px, "y": py + 32})

    # Net labels
    for lbl in (labels or []):
        comp_name = lbl.get("component", "")
        pin_name = lbl.get("pin", "")
        label_name = lbl.get("label", "")
        pos = _get_pin_abs(graph, comp_name, pin_name)
        if pos and label_name:
            result.flags.append({"name": label_name, "x": pos[0], "y": pos[1]})

    result.wires = _deduplicate_wires(result.wires)
    return result


# ── Simple pairwise L-router (first pass) ───────────────────────────────────

def route_connections(
    graph: "CircuitGraph",
    connections: list[dict],
    grounds: list[dict] | None = None,
    labels: list[dict] | None = None,
) -> WireResult:
    """Route each pairwise connection as an L-shaped wire.

    This is the first-pass router: it takes the raw VLM connections and
    L-routes each one directly between pin positions.  Buses emerge
    naturally when adjacent pins share a coordinate.
    """
    result = WireResult()

    for conn in connections:
        f = conn.get("from", {})
        t = conn.get("to", {})
        from_comp = f.get("component", "")
        from_pin = f.get("pin", "")
        to_comp = t.get("component", "")
        to_pin = t.get("pin", "")

        if not from_comp or not to_comp:
            continue
        # Skip self-shorts
        if from_comp == to_comp:
            continue

        pos_a = _get_pin_abs(graph, from_comp, from_pin)
        pos_b = _get_pin_abs(graph, to_comp, to_pin)
        if pos_a is None or pos_b is None:
            logger.warning("Cannot resolve pin: %s.%s -> %s.%s", from_comp, from_pin, to_comp, to_pin)
            continue

        result.wires.extend(_l_route(pos_a[0], pos_a[1], pos_b[0], pos_b[1]))

    # Ground flags
    for gnd in (grounds or []):
        comp_name = gnd.get("component", "")
        pin_name = gnd.get("pin", "")
        pos = _get_pin_abs(graph, comp_name, pin_name)
        if pos:
            px, py = pos
            result.wires.append((px, py, px, py + 32))
            result.flags.append({"name": "0", "x": px, "y": py + 32})

    # Net labels
    for lbl in (labels or []):
        comp_name = lbl.get("component", "")
        pin_name = lbl.get("pin", "")
        label_name = lbl.get("label", "")
        pos = _get_pin_abs(graph, comp_name, pin_name)
        if pos and label_name:
            result.flags.append({"name": label_name, "x": pos[0], "y": pos[1]})

    result.wires = _deduplicate_wires(result.wires)
    return result


# ── Net-aware bus router (redraw / advanced) ────────────────────────────────

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

            if len(pin_positions) == 2 and x_range > 0 and y_range > 0:
                p1, p2 = pin_positions
                result.wires.extend(_l_route(p1[0], p1[1], p2[0], p2[1]))
            elif len(pin_positions) >= 2:
                result.wires.extend(
                    _route_net_with_direct_wires(pin_positions, pin_components)
                )

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
