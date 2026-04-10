"""Circuit graph: components, nets, tiers — the core data model for layout and routing."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_DEFAULT_SYMBOL_SIZE = (64, 80)


@dataclass
class ComponentNode:
    name: str
    type: str
    value: str
    pins: list[dict]
    symbol_size: tuple[int, int]
    resolved_rotation: str = "R0"
    tier: int = -1
    position: tuple[int, int] | None = None


@dataclass
class Net:
    name: str
    pins: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Tier:
    index: int
    components: list[str] = field(default_factory=list)
    y_position: int = 0


class CircuitGraph:
    def __init__(self, dictionary: dict):
        self._dictionary = dictionary
        self.components: dict[str, ComponentNode] = {}
        self.nets: dict[str, Net] = {}
        self.tiers: list[Tier] = []
        self.flow_direction: str = "vertical"
        self._parent: dict[tuple[str, str], tuple[str, str]] = {}

    def add_components(self, components: list[dict]) -> None:
        for comp in components:
            name = comp.get("name", "")
            ctype = comp.get("type", "res")
            value = comp.get("value", "1")
            comp_def = self._dictionary.get("components", {}).get(ctype, {})
            pins = comp_def.get("pins", [])
            sym = comp_def.get("symbol", {})
            size = (sym.get("width", _DEFAULT_SYMBOL_SIZE[0]),
                    sym.get("height", _DEFAULT_SYMBOL_SIZE[1]))
            self.components[name] = ComponentNode(
                name=name, type=ctype, value=value,
                pins=pins, symbol_size=size,
            )

    def _uf_find(self, pin: tuple[str, str]) -> tuple[str, str]:
        while self._parent.get(pin, pin) != pin:
            self._parent[pin] = self._parent.get(self._parent[pin], self._parent[pin])
            pin = self._parent[pin]
        return pin

    def _uf_union(self, a: tuple[str, str], b: tuple[str, str]) -> None:
        ra, rb = self._uf_find(a), self._uf_find(b)
        if ra != rb:
            self._parent[ra] = rb

    def build_nets(self, connections: list[dict], grounds: list[dict], labels: list[dict]) -> None:
        self._parent.clear()
        self.nets.clear()

        for conn in connections:
            f = conn.get("from", {})
            t = conn.get("to", {})
            pin_a = (f.get("component", ""), f.get("pin", ""))
            pin_b = (t.get("component", ""), t.get("pin", ""))
            if pin_a[0] and pin_b[0]:
                self._uf_union(pin_a, pin_b)

        all_pins: set[tuple[str, str]] = set()
        for conn in connections:
            f = conn.get("from", {})
            t = conn.get("to", {})
            pa = (f.get("component", ""), f.get("pin", ""))
            pb = (t.get("component", ""), t.get("pin", ""))
            if pa[0]: all_pins.add(pa)
            if pb[0]: all_pins.add(pb)
        for gnd in grounds:
            pin = (gnd.get("component", ""), gnd.get("pin", ""))
            if pin[0]: all_pins.add(pin)
        for lbl in labels:
            pin = (lbl.get("component", ""), lbl.get("pin", ""))
            if pin[0]: all_pins.add(pin)

        groups: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for pin in all_pins:
            root = self._uf_find(pin)
            groups.setdefault(root, []).append(pin)

        ground_pins: set[tuple[str, str]] = set()
        for gnd in grounds:
            pin = (gnd.get("component", ""), gnd.get("pin", ""))
            if pin[0]: ground_pins.add(self._uf_find(pin))

        label_names: dict[tuple[str, str], str] = {}
        for lbl in labels:
            pin = (lbl.get("component", ""), lbl.get("pin", ""))
            if pin[0] and lbl.get("label"):
                label_names[self._uf_find(pin)] = lbl["label"]

        auto_idx = 0
        for root, pins in groups.items():
            if root in ground_pins:
                name = "0"
            elif root in label_names:
                name = label_names[root]
            else:
                name = f"net_{auto_idx}"
                auto_idx += 1
            self.nets[name] = Net(name=name, pins=sorted(pins))
