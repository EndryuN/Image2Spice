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


def _snap(value: int) -> int:
    return round(value / 16) * 16


def compute_layout(
    layout_desc: list[dict],
    component_sizes: dict[str, dict],
    sheet_width: int = 880,
    sheet_height: int = 680,
) -> dict[str, dict]:
    positions: dict[str, dict] = {}

    # Phase 1: Place by region
    for item in layout_desc:
        name = item["instanceName"]
        region = item.get("region", "center")
        base_x, base_y = REGION_COORDS.get(region, (432, 336))
        positions[name] = {"x": base_x, "y": base_y}

    # Phase 2: Adjust by nearby relationships
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
            positions[name] = {"x": ref_pos["x"] + dx, "y": ref_pos["y"] + dy}

    # Phase 3: Grid snap
    for name in positions:
        positions[name]["x"] = _snap(positions[name]["x"])
        positions[name]["y"] = _snap(positions[name]["y"])

    # Phase 4: Clamp to sheet bounds
    for name in positions:
        positions[name]["x"] = max(32, min(sheet_width - 32, positions[name]["x"]))
        positions[name]["y"] = max(32, min(sheet_height - 32, positions[name]["y"]))

    return positions
