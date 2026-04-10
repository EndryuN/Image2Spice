"""Convert VLM analysis JSON into a complete .asc file.

Uses VLM-provided (x%, y%) positions mapped directly to canvas coordinates,
with orientation resolved from the circuit graph topology.
"""
from __future__ import annotations

import logging

from services.circuit_graph import CircuitGraph
from services.layout import compute_layout_from_graph
from services.wire_router import route_connections, route_nets, route_with_paths

logger = logging.getLogger(__name__)

_MARGIN = 48


def _snap(v: int) -> int:
    return round(v / 16) * 16


def _parse_pin_ref(ref: str) -> tuple[str, str] | None:
    parts = ref.rsplit(".", 1)
    if len(parts) != 2:
        return None
    return (parts[0], parts[1])


def _normalize_analysis(analysis: dict) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Normalize VLM analysis into (components, connections, grounds, labels)."""
    components = analysis.get("components", [])
    raw_connections = analysis.get("connections", [])
    raw_grounds = analysis.get("grounds", [])
    raw_labels = analysis.get("labels", [])

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

    grounds: list[dict] = []
    for gnd in raw_grounds:
        if isinstance(gnd, str):
            parsed = _parse_pin_ref(gnd)
            if parsed:
                grounds.append({"component": parsed[0], "pin": parsed[1]})
        elif isinstance(gnd, dict):
            grounds.append(gnd)

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

    # Filter out labels that look like component values (e.g. "15 V", "10V", "1k")
    # These are VLM errors — the value should be on the component, not a flag
    import re
    _VALUE_PATTERN = re.compile(r"^\d+\.?\d*\s*[VvAaΩ]$|^\d+\.?\d*\s*[kKmMuUnNpP][VvAaΩFfHh]?$")
    filtered_labels = [
        lbl for lbl in labels
        if not _VALUE_PATTERN.match(lbl.get("label", "").strip())
    ]

    return components, connections, grounds, filtered_labels


def build_graph_from_analysis(
    analysis: dict,
    dictionary: dict,
) -> CircuitGraph:
    """Build a CircuitGraph from VLM analysis. Used for validation."""
    components, connections, grounds, labels = _normalize_analysis(analysis)
    graph = CircuitGraph(dictionary)
    graph.add_components(components)
    graph.build_nets(connections, grounds, labels)
    graph.assign_tiers()
    graph.resolve_orientations()
    return graph


def build_asc(
    analysis: dict,
    dictionary: dict,
    sheet_width: int = 880,
    sheet_height: int = 680,
    wire_paths: list | None = None,
    buses: list | None = None,
) -> str:
    """Convert VLM analysis into .asc text.

    Uses VLM-provided (x%, y%) positions mapped to canvas coordinates.
    Orientation is resolved from circuit topology.
    If wire_paths/buses are provided (from image analysis), uses image-aware
    routing. Otherwise falls back to net-aware bus routing.
    """
    components, connections, grounds, labels = _normalize_analysis(analysis)

    # Build graph for orientation resolution + validation
    graph = CircuitGraph(dictionary)
    graph.add_components(components)
    graph.build_nets(connections, grounds, labels)
    graph.assign_tiers()
    graph.resolve_orientations()

    # Place components using VLM percentage positions → canvas coordinates
    raw_comps = analysis.get("components", [])
    vlm_positions: dict[str, tuple[int, int]] = {}
    for comp_data in raw_comps:
        name = comp_data.get("name", "")
        node = graph.components.get(name)
        if not node:
            continue

        pct_x = max(0, min(100, float(comp_data.get("x", 50))))
        pct_y = max(0, min(100, float(comp_data.get("y", 50))))

        x = _snap(int(_MARGIN + (pct_x / 100) * (sheet_width - 2 * _MARGIN)))
        y = _snap(int(_MARGIN + (pct_y / 100) * (sheet_height - 2 * _MARGIN)))

        vlm_positions[name] = (x, y)

        # Use VLM orientation if graph didn't assign horizontal
        vlm_orient = comp_data.get("orientation", "vertical")
        if vlm_orient == "horizontal" and node.resolved_rotation in ("R0", "R180"):
            node.resolved_rotation = "R90"

    # Check if VLM provided distinct positions — if all positions are
    # identical the VLM likely omitted x/y fields (they default to 50%).
    unique_positions = set(vlm_positions.values())
    vlm_useful = len(unique_positions) > 1 and len(vlm_positions) > 1

    if vlm_useful:
        for name, pos in vlm_positions.items():
            node = graph.components.get(name)
            if node:
                node.position = pos

        # Column alignment: snap directly-connected components to same X
        _COLUMN_THRESHOLD = int(sheet_width * 0.2)
        for conn in connections:
            f = conn.get("from", {})
            t = conn.get("to", {})
            name_a = f.get("component", "")
            name_b = t.get("component", "")
            node_a = graph.components.get(name_a)
            node_b = graph.components.get(name_b)
            if not node_a or not node_b or not node_a.position or not node_b.position:
                continue
            ax, ay = node_a.position
            bx, by = node_b.position
            dx = abs(ax - bx)
            dy = abs(ay - by)
            if dx < _COLUMN_THRESHOLD and dy > dx:
                avg_x = _snap((ax + bx) // 2)
                node_a.position = (avg_x, ay)
                node_b.position = (avg_x, by)
    else:
        # VLM didn't provide useful positions — use tier-based layout
        logger.info("VLM positions not distinct (%d unique for %d components), using graph layout",
                     len(unique_positions), len(vlm_positions))
        positions, (auto_w, auto_h) = compute_layout_from_graph(graph)
        sheet_width = max(sheet_width, auto_w)
        sheet_height = max(sheet_height, auto_h)

    # Route wires — net-aware bus routing with direct column wires
    wire_result = route_nets(graph)

    # Build .asc lines
    lines = ["Version 4", f"SHEET 1 {sheet_width} {sheet_height}"]

    for w in wire_result.wires:
        lines.append(f"WIRE {w[0]} {w[1]} {w[2]} {w[3]}")

    for flag in wire_result.flags:
        lines.append(f"FLAG {flag['x']} {flag['y']} {flag['name']}")

    for name, node in graph.components.items():
        if not node.position:
            continue
        sx, sy = node.position
        rot = node.resolved_rotation
        # Convert from SVG space to LTspice origin space for .asc export
        # SVG top-left is at (svg_x, svg_y); LTspice origin = svg - bounds_min
        comp_def = dictionary.get("components", {}).get(node.type, {})
        bounds = comp_def.get("geometry", {}).get("bounds", [0, 0, 0, 0])
        ltx = sx - bounds[0]
        lty = sy - bounds[1]
        lines.append(f"SYMBOL {node.type} {ltx} {lty} {rot}")
        for win in comp_def.get("windows", []):
            lines.append(f"WINDOW {win['index']} {win['x']} {win['y']} {win['justification']} {win['fontSize']}")
        lines.append(f"SYMATTR InstName {name}")
        lines.append(f"SYMATTR Value {node.value}")

    lines.append("")

    logger.info("Built .asc: %d components, %d wires, %d flags",
                len(graph.components), len(wire_result.wires), len(wire_result.flags))

    return "\n".join(lines)
