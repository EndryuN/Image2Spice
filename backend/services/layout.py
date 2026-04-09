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

_MIN_SPACING = 96
_MAX_COLLISION_ITERS = 50
_MARGIN = 32


def _snap(value: int) -> int:
    return round(value / 16) * 16


def compute_layout(
    layout_desc: list[dict],
    component_sizes: dict[str, dict],
    sheet_width: int = 880,
    sheet_height: int = 680,
) -> dict[str, dict]:
    positions: dict[str, dict] = {}

    # Check if we have percentage-based coordinates (new format)
    has_coords = any(
        "x" in item and "y" in item and item.get("x", 50) != 50 or item.get("y", 50) != 50
        for item in layout_desc
    )

    if has_coords:
        # ── New path: percentage coordinates → sheet coordinates ─────────
        for item in layout_desc:
            name = item["instanceName"]
            pct_x = max(0, min(100, float(item.get("x", 50))))
            pct_y = max(0, min(100, float(item.get("y", 50))))
            x = int(_MARGIN + (pct_x / 100) * (sheet_width - 2 * _MARGIN))
            y = int(_MARGIN + (pct_y / 100) * (sheet_height - 2 * _MARGIN))
            positions[name] = {"x": x, "y": y}
    else:
        # ── Legacy path: region-based placement ──────────────────────────
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

    # ── Collision resolution ─────────────────────────────────────────────
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

    # ── Grid snap + clamp ────────────────────────────────────────────────
    for name in positions:
        positions[name]["x"] = _snap(positions[name]["x"])
        positions[name]["y"] = _snap(positions[name]["y"])
        positions[name]["x"] = max(_MARGIN, min(sheet_width - _MARGIN, positions[name]["x"]))
        positions[name]["y"] = max(_MARGIN, min(sheet_height - _MARGIN, positions[name]["y"]))

    return positions
