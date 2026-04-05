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

_MIN_SPACING = 96
_MAX_COLLISION_ITERS = 50


def _snap(value: int) -> int:
    return round(value / 16) * 16


def compute_layout(
    layout_desc: list[dict],
    component_sizes: dict[str, dict],
    sheet_width: int = 880,
    sheet_height: int = 680,
) -> dict[str, dict]:
    positions: dict[str, dict] = {}

    # ── Phase 1: Region placement with same-region scatter ────────────────
    region_groups: dict[str, list[str]] = {}
    for item in layout_desc:
        name = item["instanceName"]
        region = item.get("region", "center")
        region_groups.setdefault(region, []).append(name)

    for region, names in region_groups.items():
        base_x, base_y = REGION_COORDS.get(region, (432, 336))
        count = len(names)
        if count == 1:
            positions[names[0]] = {"x": base_x, "y": base_y}
        else:
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
