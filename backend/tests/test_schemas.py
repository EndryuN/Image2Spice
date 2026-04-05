import pytest
from pydantic import ValidationError
from services.schemas import (
    IdentifiedComponent,
    IdentifyResponse,
    DirectivesResponse,
    LayoutItem,
    LayoutResponse,
    NearbyRef,
    ConnectionEndpoint,
    WireConnection,
    WiresResponse,
    GroundRef,
    LabelRef,
)


def test_identified_component_valid():
    c = IdentifiedComponent(type="res", instanceName="R1", value="10k")
    assert c.type == "res"
    assert c.instanceName == "R1"
    assert c.value == "10k"
    assert c.value2 is None


def test_identified_component_with_value2():
    c = IdentifiedComponent(type="voltage", instanceName="V1", value="5", value2="AC 1")
    assert c.value2 == "AC 1"


def test_identified_component_missing_required():
    with pytest.raises(ValidationError):
        IdentifiedComponent(type="res", instanceName="R1")  # missing value


def test_identify_response_from_array():
    data = {"components": [{"type": "res", "instanceName": "R1", "value": "1k"}]}
    r = IdentifyResponse.model_validate(data)
    assert len(r.components) == 1


def test_directives_response_valid():
    r = DirectivesResponse(directives=[".tran 1m", ".param R=10k"])
    assert len(r.directives) == 2


def test_directives_response_empty():
    r = DirectivesResponse(directives=[])
    assert r.directives == []


def test_layout_item_valid():
    item = LayoutItem(
        instanceName="U1",
        region="center",
        nearby=[NearbyRef(name="R1", direction="above")]
    )
    assert item.region == "center"
    assert len(item.nearby) == 1


def test_layout_item_no_nearby():
    item = LayoutItem(instanceName="V1", region="top-left")
    assert item.nearby == []


def test_layout_response_valid():
    data = {"layout": [
        {"instanceName": "R1", "region": "top-left", "nearby": []},
        {"instanceName": "U1", "region": "center", "nearby": [{"name": "R1", "direction": "above"}]},
    ]}
    r = LayoutResponse.model_validate(data)
    assert len(r.layout) == 2


def test_wire_connection_from_alias():
    data = {"from": {"component": "R1", "pin": "B"}, "to": {"component": "C1", "pin": "A"}}
    wc = WireConnection.model_validate(data)
    assert wc.from_.component == "R1"
    assert wc.to.pin == "A"


def test_wires_response_valid():
    data = {
        "connections": [
            {"from": {"component": "R1", "pin": "B"}, "to": {"component": "C1", "pin": "A"}}
        ],
        "grounds": [{"component": "V1", "pin": "-"}],
        "labels": [{"component": "U1", "pin": "OUT", "label": "OUT"}],
    }
    r = WiresResponse.model_validate(data)
    assert len(r.connections) == 1
    assert len(r.grounds) == 1
    assert len(r.labels) == 1


def test_wires_response_empty():
    r = WiresResponse.model_validate({})
    assert r.connections == []
    assert r.grounds == []
    assert r.labels == []


def test_wires_response_missing_pin():
    with pytest.raises(ValidationError):
        WiresResponse.model_validate({
            "connections": [{"from": {"component": "R1"}, "to": {"component": "C1", "pin": "A"}}]
        })
