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
            result.wires.append((fx, fy, tx, ty))
        else:
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
