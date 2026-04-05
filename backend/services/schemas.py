from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


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

class IdentifiedComponent(BaseModel):
    type: str
    instanceName: str
    value: str
    value2: Optional[str] = None


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
