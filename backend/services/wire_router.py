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


def compute_wires(
    components: dict[str, dict],
    pin_defs: dict[str, list[dict]],
    connections_data: dict,
) -> WireResult:
    result = WireResult()

    for conn in connections_data.get("connections", []):
        from_comp = components.get(conn["from"]["component"])
        to_comp = components.get(conn["to"]["component"])
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
            result.wires.append((fx, fy, tx, fy))
            result.wires.append((tx, fy, tx, ty))

    for gnd in connections_data.get("grounds", []):
        comp = components.get(gnd["component"])
        if not comp:
            continue
        pin = _find_pin(pin_defs, comp["type"], gnd["pin"])
        if not pin:
            continue
        px, py = _abs_pin_pos(comp, pin)
        result.flags.append({"name": "0", "x": px, "y": py})

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
