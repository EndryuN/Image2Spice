from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


VALID_REGIONS = {
    "top-left", "top-center", "top-right",
    "center-left", "center", "center-right",
    "bottom-left", "bottom-center", "bottom-right",
}

VALID_DIRECTIONS = {
    "above", "below", "left", "right",
    "above-left", "above-right", "below-left", "below-right",
}


# ── Identify step ─────────────────────────────────────────────────────────────

DEFAULT_VALUES: dict[str, str] = {
    "res": "1k",
    "cap": "1u",
    "ind": "1m",
    "voltage": "5",
    "current": "1m",
    "opamp": "UniversalOpamp2",
    "opamp2": "UniversalOpamp2",
    "npn": "2N2222",
    "pnp": "2N2907",
    "nmos": "2N7002",
    "pmos": "BSS84",
    "diode": "1N4148",
    "zener": "1N4733A",
}


class IdentifiedComponent(BaseModel):
    type: str
    instanceName: str
    value: str
    value2: Optional[str] = None

    @field_validator("value", mode="before")
    @classmethod
    def value_must_not_be_empty(cls, v: str, info) -> str:
        if isinstance(v, str) and v.strip() == "":
            # Try to fill from defaults using the type field
            comp_type = info.data.get("type", "")
            default = DEFAULT_VALUES.get(comp_type, "1")
            return default
        return v


class IdentifyResponse(BaseModel):
    components: list[IdentifiedComponent]


# ── Directives step ───────────────────────────────────────────────────────────

class DirectivesResponse(BaseModel):
    directives: list[str]


# ── Layout step ───────────────────────────────────────────────────────────────

class NearbyRef(BaseModel):
    name: str
    direction: str


class LayoutItem(BaseModel):
    instanceName: str
    # Grid-based placement (new)
    row: int = 0
    col: int = 0
    orientation: str = "vertical"
    # Percentage-based placement (legacy)
    x: float = 50
    y: float = 50
    rotation: str = "R0"
    # Region-based placement (legacy)
    region: str = "center"
    nearby: list[NearbyRef] = Field(default_factory=list)


class LayoutResponse(BaseModel):
    layout: list[LayoutItem]


# ── Wires step ────────────────────────────────────────────────────────────────

class ConnectionEndpoint(BaseModel):
    component: str
    pin: str


class WireConnection(BaseModel):
    from_: ConnectionEndpoint = Field(alias="from")
    to: ConnectionEndpoint

    model_config = {"populate_by_name": True}


class GroundRef(BaseModel):
    component: str
    pin: str


class LabelRef(BaseModel):
    component: str
    pin: str
    label: str


class WiresResponse(BaseModel):
    connections: list[WireConnection] = Field(default_factory=list)
    grounds: list[GroundRef] = Field(default_factory=list)
    labels: list[LabelRef] = Field(default_factory=list)


# ── Pin normalization ─────────────────────────────────────────────────────────

_PASSIVE_ALIASES: dict[str, str] = {
    "1": "A", "2": "B",
    "pin1": "A", "pin2": "B",
    "pin 1": "A", "pin 2": "B",
    "top": "A", "bottom": "B",
    "left": "A", "right": "B",
    "p": "A", "n": "B",
    "a": "A", "b": "B",
    "positive": "A", "negative": "B",
    "pos": "A", "neg": "B",
    "+": "A", "-": "B",
    "input": "A", "output": "B",
    "in": "A", "out": "B",
    "first": "A", "second": "B",
}

_SOURCE_ALIASES: dict[str, str] = {
    "1": "+", "2": "-",
    "pin1": "+", "pin2": "-",
    "pin 1": "+", "pin 2": "-",
    "positive": "+", "negative": "-",
    "pos": "+", "neg": "-",
    "p": "+", "n": "-",
    "v+": "+", "v-": "-",
    "+": "+", "-": "-",
    "top": "+", "bottom": "-",
    "a": "+", "b": "-",
    "first": "+", "second": "-",
}

_DIODE_ALIASES: dict[str, str] = {
    "1": "+", "2": "-",
    "pin1": "+", "pin2": "-",
    "pin 1": "+", "pin 2": "-",
    "anode": "+", "cathode": "-",
    "a": "+", "k": "-",
    "p": "+", "n": "-",
    "+": "+", "-": "-",
    "positive": "+", "negative": "-",
    "pos": "+", "neg": "-",
    "top": "+", "bottom": "-",
    "first": "+", "second": "-",
}

_BJT_ALIASES: dict[str, str] = {
    "1": "C", "2": "B", "3": "E",
    "pin1": "C", "pin2": "B", "pin3": "E",
    "pin 1": "C", "pin 2": "B", "pin 3": "E",
    "collector": "C", "base": "B", "emitter": "E",
    "col": "C", "emit": "E",
    "c": "C", "b": "B", "e": "E",
    "top": "C", "middle": "B", "bottom": "E",
}

_MOSFET_ALIASES: dict[str, str] = {
    "1": "D", "2": "G", "3": "S",
    "pin1": "D", "pin2": "G", "pin3": "S",
    "pin 1": "D", "pin 2": "G", "pin 3": "S",
    "drain": "D", "gate": "G", "source": "S",
    "d": "D", "g": "G", "s": "S",
    "top": "D", "middle": "G", "bottom": "S",
}

_OPAMP_ALIASES: dict[str, str] = {
    "in-": "invin", "in+": "noninvin",
    "inverting": "invin", "non-inverting": "noninvin",
    "inv": "invin", "noninv": "noninvin",
    "output": "out",
    "1": "invin", "2": "noninvin", "3": "out",
    "pin1": "invin", "pin2": "noninvin", "pin3": "out",
    "invin": "invin", "noninvin": "noninvin", "out": "out",
}

_OPAMP2_ALIASES: dict[str, str] = {
    "in+": "In+", "in-": "In-",
    "noninv": "In+", "non-inverting": "In+", "noninverting": "In+",
    "inv": "In-", "inverting": "In-",
    "v+": "V+", "v-": "V-",
    "vcc": "V+", "vdd": "V+",
    "vee": "V-", "vss": "V-",
    "out": "OUT", "output": "OUT",
    "1": "In+", "2": "In-", "3": "V+", "4": "V-", "5": "OUT",
    "pin1": "In+", "pin2": "In-", "pin3": "V+", "pin4": "V-", "pin5": "OUT",
}

PIN_ALIASES: dict[str, dict[str, str]] = {
    "res": _PASSIVE_ALIASES,
    "cap": _PASSIVE_ALIASES,
    "ind": _PASSIVE_ALIASES,
    "voltage": _SOURCE_ALIASES,
    "current": _SOURCE_ALIASES,
    "diode": _DIODE_ALIASES,
    "zener": _DIODE_ALIASES,
    "npn": _BJT_ALIASES,
    "pnp": _BJT_ALIASES,
    "nmos": _MOSFET_ALIASES,
    "pmos": _MOSFET_ALIASES,
    "opamp": _OPAMP_ALIASES,
    "opamp2": _OPAMP2_ALIASES,
}


def normalize_pin(comp_type: str, raw_pin: str) -> str:
    """Map a VLM-returned pin name to the dictionary-canonical name.

    Lookup is case-insensitive.  Returns *raw_pin* unchanged when
    the component type is unknown or no alias matches.
    """
    aliases = PIN_ALIASES.get(comp_type)
    if aliases is None:
        return raw_pin
    return aliases.get(raw_pin.lower(), raw_pin)
