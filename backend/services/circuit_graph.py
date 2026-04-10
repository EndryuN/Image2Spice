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
        self._net_tiers: dict[str, int] = {}
        self._pin_net: dict[tuple[str, str], str] = {}

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

    def assign_tiers(self) -> None:
        if not self.components or not self.nets:
            return

        # Build pin -> net name mapping
        self._pin_net.clear()
        for net_name, net in self.nets.items():
            for pin in net.pins:
                self._pin_net[pin] = net_name
        pin_net = self._pin_net

        # Create virtual singleton nets for component pins not in any net
        virtual_idx = 0
        for name, node in self.components.items():
            for pin_def in node.pins:
                pin_key = (name, pin_def["name"])
                if pin_key not in pin_net:
                    vnet_name = f"_virtual_{virtual_idx}"
                    virtual_idx += 1
                    pin_net[pin_key] = vnet_name

        # For each component, find which nets its first and last pin belong to
        comp_pin_nets: dict[str, tuple[str | None, str | None]] = {}
        for name, node in self.components.items():
            if len(node.pins) >= 2:
                net_a = pin_net.get((name, node.pins[0]["name"]))
                net_b = pin_net.get((name, node.pins[-1]["name"]))
                comp_pin_nets[name] = (net_a, net_b)
            elif len(node.pins) == 1:
                comp_pin_nets[name] = (pin_net.get((name, node.pins[0]["name"])), None)
            else:
                comp_pin_nets[name] = (None, None)

        # Build net-level graph (nets connected by components)
        net_graph: dict[str, set[str]] = {}
        for name, (net_a, net_b) in comp_pin_nets.items():
            if net_a and net_b and net_a != net_b:
                net_graph.setdefault(net_a, set()).add(net_b)
                net_graph.setdefault(net_b, set()).add(net_a)

        # BFS from first net to assign net tiers
        self._net_tiers.clear()
        net_tiers = self._net_tiers
        if net_graph:
            # Prefer starting from a net connected to a voltage source
            start_net = next(iter(net_graph))
            for name, node in self.components.items():
                if node.type in ("voltage", "current"):
                    net_a, _ = comp_pin_nets.get(name, (None, None))
                    if net_a and net_a in net_graph:
                        start_net = net_a
                        break
            queue = [start_net]
            net_tiers[start_net] = 0
            while queue:
                current = queue.pop(0)
                for neighbor in net_graph.get(current, set()):
                    if neighbor not in net_tiers:
                        net_tiers[neighbor] = net_tiers[current] + 1
                        queue.append(neighbor)

        # Assign component tiers from their net tiers
        # All components use min — parallel components sharing the same two
        # nets end up on the same tier (correct for ground-truth circuit 04).
        # Series components naturally get different tiers because their nets
        # have different BFS distances.
        for name, node in self.components.items():
            net_a, net_b = comp_pin_nets.get(name, (None, None))
            tier_a = net_tiers.get(net_a, 0) if net_a else 0
            tier_b = net_tiers.get(net_b, 0) if net_b else 0
            node.tier = min(tier_a, tier_b)

        # Build tier list
        tier_map: dict[int, list[str]] = {}
        for name, node in self.components.items():
            tier_map.setdefault(node.tier, []).append(name)
        self.tiers = [Tier(index=idx, components=comps) for idx, comps in sorted(tier_map.items())]

    def resolve_orientations(self) -> None:
        for name, node in self.components.items():
            if len(node.pins) < 2:
                node.resolved_rotation = "R0"
                continue

            pin_a = (name, node.pins[0]["name"])
            pin_b = (name, node.pins[-1]["name"])

            net_a = self._pin_net.get(pin_a)
            net_b = self._pin_net.get(pin_b)

            tier_a = self._net_tiers.get(net_a, 0) if net_a else 0
            tier_b = self._net_tiers.get(net_b, 0) if net_b else 0

            if net_a == net_b:
                # Both pins on the same net — orient horizontally
                node.resolved_rotation = "R90"
            elif tier_a == tier_b:
                # Different nets at the same tier — default to vertical
                node.resolved_rotation = "R0"
            elif tier_a < tier_b:
                node.resolved_rotation = "R0"
            else:
                node.resolved_rotation = "R180"

    def validate(self) -> dict:
        """Check circuit for issues: unconnected pins, missing connections.

        Returns dict with:
          unconnected_pins: list of (comp_name, pin_name) not on any net
          component_count: int
          net_count: int
          all_connected: bool (every component has all pins in some net)
        """
        unconnected: list[tuple[str, str]] = []
        for name, node in self.components.items():
            for pin_def in node.pins:
                key = (name, pin_def["name"])
                if key not in self._pin_net or self._pin_net[key].startswith("_virtual_"):
                    unconnected.append(key)

        return {
            "unconnected_pins": unconnected,
            "component_count": len(self.components),
            "net_count": len(self.nets),
            "all_connected": len(unconnected) == 0,
        }
