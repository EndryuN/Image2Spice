"""Convert VLM analysis JSON into a complete .asc file using CircuitGraph pipeline."""
from __future__ import annotations

import logging

from services.circuit_graph import CircuitGraph
from services.layout import compute_layout_from_graph
from services.wire_router import route_nets

logger = logging.getLogger(__name__)


def _snap(v: int) -> int:
    return round(v / 16) * 16


def _parse_pin_ref(ref: str) -> tuple[str, str] | None:
    parts = ref.rsplit(".", 1)
    if len(parts) != 2:
        return None
    return (parts[0], parts[1])


def build_asc(
    analysis: dict,
    dictionary: dict,
    sheet_width: int = 880,
    sheet_height: int = 680,
) -> str:
    components = analysis.get("components", [])
    raw_connections = analysis.get("connections", [])
    raw_grounds = analysis.get("grounds", [])
    raw_labels = analysis.get("labels", [])

    # Normalize connections
    connections: list[dict] = []
    for conn in raw_connections:
        if isinstance(conn, dict) and "from" in conn and "to" in conn:
            f = conn["from"]
            t = conn["to"]
            if isinstance(f, str) and isinstance(t, str):
                pf = _parse_pin_ref(f)
                pt = _parse_pin_ref(t)
                if pf and pt:
                    connections.append({
                        "from": {"component": pf[0], "pin": pf[1]},
                        "to": {"component": pt[0], "pin": pt[1]},
                    })
            elif isinstance(f, dict) and isinstance(t, dict):
                connections.append(conn)

    # Normalize grounds
    grounds: list[dict] = []
    for gnd in raw_grounds:
        if isinstance(gnd, str):
            parsed = _parse_pin_ref(gnd)
            if parsed:
                grounds.append({"component": parsed[0], "pin": parsed[1]})
        elif isinstance(gnd, dict):
            grounds.append(gnd)

    # Normalize labels
    labels: list[dict] = []
    for lbl in raw_labels:
        if isinstance(lbl, dict):
            if "pin" in lbl and isinstance(lbl["pin"], str) and "." in lbl["pin"]:
                parsed = _parse_pin_ref(lbl["pin"])
                if parsed:
                    labels.append({
                        "component": parsed[0],
                        "pin": parsed[1],
                        "label": lbl.get("name", lbl.get("label", "")),
                    })
            else:
                labels.append(lbl)

    # Build circuit graph
    graph = CircuitGraph(dictionary)
    graph.add_components(components)
    graph.build_nets(connections, grounds, labels)
    graph.assign_tiers()
    graph.resolve_orientations()

    # Layout
    positions, (auto_w, auto_h) = compute_layout_from_graph(graph)
    final_w = max(sheet_width, auto_w)
    final_h = max(sheet_height, auto_h)

    # Route wires
    wire_result = route_nets(graph)

    # Build .asc lines
    lines = ["Version 4", f"SHEET 1 {final_w} {final_h}"]

    for w in wire_result.wires:
        lines.append(f"WIRE {w[0]} {w[1]} {w[2]} {w[3]}")

    for flag in wire_result.flags:
        lines.append(f"FLAG {flag['x']} {flag['y']} {flag['name']}")

    for name, node in graph.components.items():
        if not node.position:
            continue
        x, y = node.position
        rot = node.resolved_rotation
        lines.append(f"SYMBOL {node.type} {x} {y} {rot}")
        comp_def = dictionary.get("components", {}).get(node.type, {})
        for win in comp_def.get("windows", []):
            lines.append(f"WINDOW {win['index']} {win['x']} {win['y']} {win['justification']} {win['fontSize']}")
        lines.append(f"SYMATTR InstName {name}")
        lines.append(f"SYMATTR Value {node.value}")

    lines.append("")

    logger.info("Built .asc: %d components, %d wires, %d flags",
                len(graph.components), len(wire_result.wires), len(wire_result.flags))

    return "\n".join(lines)
