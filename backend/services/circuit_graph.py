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
