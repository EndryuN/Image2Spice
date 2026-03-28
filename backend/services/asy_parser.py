"""
Parser for LTspice .asy (symbol) files.

Reads component geometry (lines, circles, arcs, rectangles), pin definitions,
window positions, and symbol attributes from .asy text content.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Pin:
    name: str
    x: int
    y: int
    spice_order: int = 0


@dataclass
class Window:
    index: int
    x: int
    y: int
    justification: str
    font_size: int


@dataclass
class AsySymbol:
    # Geometry — stored as tuples of raw (un-normalised) integers
    lines: list[tuple[int, int, int, int]] = field(default_factory=list)
    circles: list[tuple[int, int, int, int]] = field(default_factory=list)
    arcs: list[tuple[int, int, int, int, int, int, int, int]] = field(default_factory=list)
    rectangles: list[tuple[int, int, int, int]] = field(default_factory=list)

    pins: list[Pin] = field(default_factory=list)
    windows: list[Window] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def prefix(self) -> str:
        return self.attrs.get("Prefix", "")

    @property
    def description(self) -> str:
        return self.attrs.get("Description", "")

    @property
    def value(self) -> str:
        return self.attrs.get("Value", "")

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """Return (min_x, min_y, max_x, max_y) over all geometry and pins."""
        xs: list[int] = []
        ys: list[int] = []

        for x1, y1, x2, y2 in self.lines:
            xs += [x1, x2]
            ys += [y1, y2]

        for x1, y1, x2, y2 in self.circles:
            xs += [x1, x2]
            ys += [y1, y2]

        for x1, y1, x2, y2 in self.rectangles:
            xs += [x1, x2]
            ys += [y1, y2]

        for arc in self.arcs:
            xs += [arc[0], arc[2]]
            ys += [arc[1], arc[3]]

        for p in self.pins:
            xs.append(p.x)
            ys.append(p.y)

        if not xs:
            return (0, 0, 0, 0)

        return (min(xs), min(ys), max(xs), max(ys))

    # ------------------------------------------------------------------
    # SVG conversion
    # ------------------------------------------------------------------

    def to_svg_path(self) -> str:
        """Return an SVG path string with origin normalised to (0,0)."""
        bx1, by1, _, _ = self.bounds
        parts: list[str] = []

        # Lines
        for x1, y1, x2, y2 in self.lines:
            nx1, ny1 = x1 - bx1, y1 - by1
            nx2, ny2 = x2 - bx1, y2 - by1
            parts.append(f"M{nx1},{ny1} L{nx2},{ny2}")

        # Circles — LTspice stores bounding box; convert to SVG arc
        for x1, y1, x2, y2 in self.circles:
            # Use integer arithmetic when coordinates divide evenly to keep
            # clean output (e.g. "32,32" not "32.0,32.0").
            def _n(v: float) -> int | float:
                return int(v) if v == int(v) else v

            cx = _n((x1 + x2) / 2 - bx1)
            cy = _n((y1 + y2) / 2 - by1)
            rx = _n(abs(x2 - x1) / 2)
            ry = _n(abs(y2 - y1) / 2)
            # Full circle as two half-arcs
            parts.append(
                f"M{cx - rx},{cy} "
                f"A{rx},{ry} 0 1,0 {cx + rx},{cy} "
                f"A{rx},{ry} 0 1,0 {cx - rx},{cy} Z"
            )

        # Rectangles
        for x1, y1, x2, y2 in self.rectangles:
            nx1, ny1 = x1 - bx1, y1 - by1
            nx2, ny2 = x2 - bx1, y2 - by1
            parts.append(
                f"M{nx1},{ny1} L{nx2},{ny1} L{nx2},{ny2} L{nx1},{ny2} Z"
            )

        # Arcs — approximate as a straight line between endpoints for now
        for arc in self.arcs:
            ax1, ay1, ax2, ay2, ax3, ay3, ax4, ay4 = arc
            # arc bounding box centre and radii
            cx = (ax1 + ax2) / 2 - bx1
            cy = (ay1 + ay2) / 2 - by1
            rx = abs(ax2 - ax1) / 2
            ry = abs(ay2 - ay1) / 2
            sx, sy = ax3 - bx1, ay3 - by1
            ex, ey = ax4 - bx1, ay4 - by1
            parts.append(
                f"M{sx},{sy} A{rx},{ry} 0 0,1 {ex},{ey}"
            )

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Dict serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        bx1, by1, bx2, by2 = self.bounds
        width = bx2 - bx1
        height = by2 - by1
        svg_path = self.to_svg_path()

        pins_list = [
            {
                "name": p.name,
                "x": p.x,
                "y": p.y,
                "spiceOrder": p.spice_order,
            }
            for p in self.pins
        ]

        return {
            "prefix": self.prefix,
            "description": self.description,
            "value": self.value,
            "pins": pins_list,
            "windows": [
                {
                    "index": w.index,
                    "x": w.x,
                    "y": w.y,
                    "justification": w.justification,
                    "fontSize": w.font_size,
                }
                for w in self.windows
            ],
            "geometry": {
                "lines": list(self.lines),
                "circles": list(self.circles),
                "arcs": list(self.arcs),
                "rectangles": list(self.rectangles),
                "bounds": list(self.bounds),
            },
            "symbol": {
                "svgPath": svg_path,
                "width": width,
                "height": height,
            },
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_asy_string(content: str) -> AsySymbol:
    """Parse the text content of a .asy file and return an AsySymbol."""
    sym = AsySymbol()

    # We need look-ahead for PIN → PINATTR pairs, so collect lines first.
    raw_lines = content.splitlines()
    i = 0
    pending_pin_xy: tuple[int, int] | None = None

    while i < len(raw_lines):
        line = raw_lines[i].strip()
        tokens = line.split()

        if not tokens:
            i += 1
            continue

        keyword = tokens[0].upper()

        if keyword == "LINE" and len(tokens) >= 6:
            # LINE Normal x1 y1 x2 y2
            x1, y1, x2, y2 = int(tokens[2]), int(tokens[3]), int(tokens[4]), int(tokens[5])
            sym.lines.append((x1, y1, x2, y2))

        elif keyword == "CIRCLE" and len(tokens) >= 6:
            x1, y1, x2, y2 = int(tokens[2]), int(tokens[3]), int(tokens[4]), int(tokens[5])
            sym.circles.append((x1, y1, x2, y2))

        elif keyword == "ARC" and len(tokens) >= 10:
            coords = tuple(int(t) for t in tokens[2:10])
            sym.arcs.append(coords)  # type: ignore[arg-type]

        elif keyword == "RECTANGLE" and len(tokens) >= 6:
            x1, y1, x2, y2 = int(tokens[2]), int(tokens[3]), int(tokens[4]), int(tokens[5])
            sym.rectangles.append((x1, y1, x2, y2))

        elif keyword == "WINDOW" and len(tokens) >= 6:
            idx = int(tokens[1])
            wx, wy = int(tokens[2]), int(tokens[3])
            just = tokens[4]
            fs = int(tokens[5])
            sym.windows.append(Window(index=idx, x=wx, y=wy, justification=just, font_size=fs))

        elif keyword == "SYMATTR" and len(tokens) >= 3:
            attr_key = tokens[1]
            attr_val = " ".join(tokens[2:])
            sym.attrs[attr_key] = attr_val

        elif keyword == "PIN" and len(tokens) >= 3:
            pending_pin_xy = (int(tokens[1]), int(tokens[2]))

        elif keyword == "PINATTR" and pending_pin_xy is not None:
            attr_name = tokens[1] if len(tokens) > 1 else ""
            attr_val = tokens[2] if len(tokens) > 2 else ""

            if attr_name == "PinName":
                # Look ahead for SpiceOrder on next PINATTR line(s)
                spice_order = 0
                j = i + 1
                while j < len(raw_lines):
                    next_tokens = raw_lines[j].strip().split()
                    if not next_tokens:
                        j += 1
                        continue
                    if next_tokens[0].upper() == "PINATTR" and len(next_tokens) >= 3 and next_tokens[1] == "SpiceOrder":
                        spice_order = int(next_tokens[2])
                        break
                    # If we hit a new PIN or non-PINATTR line, stop looking
                    if next_tokens[0].upper() not in ("PINATTR",):
                        break
                    j += 1

                px, py = pending_pin_xy
                sym.pins.append(Pin(name=attr_val, x=px, y=py, spice_order=spice_order))
                # Don't reset pending_pin_xy yet; SpiceOrder PINATTR may follow

            elif attr_name == "SpiceOrder":
                # Update the last pin's spice order in case look-ahead missed it
                if sym.pins:
                    sym.pins[-1].spice_order = int(attr_val)
                pending_pin_xy = None  # PIN block complete after SpiceOrder

        i += 1

    return sym


def parse_asy_file(path: str | Path) -> AsySymbol:
    """Read a .asy file from disk and parse it."""
    content = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse_asy_string(content)


# ---------------------------------------------------------------------------
# Component dictionary helpers
# ---------------------------------------------------------------------------

# Maps component IDs used in the schematic to LTspice .asy relative paths.
CORE_SYMBOLS: dict[str, str] = {
    "res": "res.asy",
    "cap": "cap.asy",
    "ind": "ind.asy",
    "voltage": "voltage.asy",
    "current": "current.asy",
    "diode": "diode.asy",
    "zener": "zener.asy",
    "npn": "npn.asy",
    "pnp": "pnp.asy",
    "nmos": "nmos.asy",
    "pmos": "pmos.asy",
    "opamp": "OpAmps/opamp.asy",
    "opamp2": "OpAmps/opamp2.asy",
}

CATEGORIES: dict[str, list[str]] = {
    "passive": ["res", "cap", "ind"],
    "source": ["voltage", "current"],
    "diode": ["diode", "zener"],
    "transistor": ["npn", "pnp", "nmos", "pmos"],
    "opamp": ["opamp", "opamp2"],
}

DISPLAY_NAMES: dict[str, str] = {
    "res": "Resistor",
    "cap": "Capacitor",
    "ind": "Inductor",
    "voltage": "Voltage Source",
    "current": "Current Source",
    "diode": "Diode",
    "zener": "Zener Diode",
    "npn": "NPN BJT",
    "pnp": "PNP BJT",
    "nmos": "N-Channel MOSFET",
    "pmos": "P-Channel MOSFET",
    "opamp": "Op-Amp",
    "opamp2": "Op-Amp (2-supply)",
}


def build_dictionary_from_asy(ltspice_sym_dir: str | Path) -> dict[str, Any]:
    """
    Parse all CORE_SYMBOLS from *ltspice_sym_dir* and return a dict mapping
    component IDs to their to_dict() representations.  Symbols whose .asy
    file cannot be found are silently skipped.
    """
    sym_dir = Path(ltspice_sym_dir)
    result: dict[str, Any] = {}

    for component_id, rel_path in CORE_SYMBOLS.items():
        full_path = sym_dir / rel_path
        if not full_path.exists():
            continue
        try:
            sym = parse_asy_file(full_path)
            d = sym.to_dict()
            d["id"] = component_id
            d["displayName"] = DISPLAY_NAMES.get(component_id, component_id)
            result[component_id] = d
        except Exception:
            pass  # skip malformed files

    return result
