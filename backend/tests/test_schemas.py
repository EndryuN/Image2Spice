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


from services.schemas import normalize_pin


def test_normalize_pin_resistor_canonical():
    assert normalize_pin("res", "A") == "A"
    assert normalize_pin("res", "B") == "B"

def test_normalize_pin_resistor_numeric():
    assert normalize_pin("res", "1") == "A"
    assert normalize_pin("res", "2") == "B"

def test_normalize_pin_resistor_generic():
    assert normalize_pin("res", "pin1") == "A"
    assert normalize_pin("res", "pin2") == "B"

def test_normalize_pin_resistor_positional():
    assert normalize_pin("res", "top") == "A"
    assert normalize_pin("res", "bottom") == "B"

def test_normalize_pin_cap_numeric():
    assert normalize_pin("cap", "1") == "A"
    assert normalize_pin("cap", "2") == "B"

def test_normalize_pin_inductor_numeric():
    assert normalize_pin("ind", "1") == "A"
    assert normalize_pin("ind", "2") == "B"

def test_normalize_pin_voltage_canonical():
    assert normalize_pin("voltage", "+") == "+"
    assert normalize_pin("voltage", "-") == "-"

def test_normalize_pin_voltage_descriptive():
    assert normalize_pin("voltage", "positive") == "+"
    assert normalize_pin("voltage", "negative") == "-"

def test_normalize_pin_voltage_aliases():
    assert normalize_pin("voltage", "v+") == "+"
    assert normalize_pin("voltage", "v-") == "-"
    assert normalize_pin("voltage", "p") == "+"
    assert normalize_pin("voltage", "n") == "-"

def test_normalize_pin_voltage_numeric():
    assert normalize_pin("voltage", "1") == "+"
    assert normalize_pin("voltage", "2") == "-"

def test_normalize_pin_current_numeric():
    assert normalize_pin("current", "1") == "+"
    assert normalize_pin("current", "2") == "-"

def test_normalize_pin_diode_descriptive():
    assert normalize_pin("diode", "anode") == "+"
    assert normalize_pin("diode", "cathode") == "-"

def test_normalize_pin_zener_numeric():
    assert normalize_pin("zener", "1") == "+"
    assert normalize_pin("zener", "2") == "-"

def test_normalize_pin_npn_canonical():
    assert normalize_pin("npn", "C") == "C"
    assert normalize_pin("npn", "B") == "B"
    assert normalize_pin("npn", "E") == "E"

def test_normalize_pin_npn_descriptive():
    assert normalize_pin("npn", "collector") == "C"
    assert normalize_pin("npn", "base") == "B"
    assert normalize_pin("npn", "emitter") == "E"

def test_normalize_pin_npn_numeric():
    assert normalize_pin("npn", "1") == "C"
    assert normalize_pin("npn", "2") == "B"
    assert normalize_pin("npn", "3") == "E"

def test_normalize_pin_pnp_descriptive():
    assert normalize_pin("pnp", "collector") == "C"
    assert normalize_pin("pnp", "emitter") == "E"

def test_normalize_pin_nmos_canonical():
    assert normalize_pin("nmos", "D") == "D"
    assert normalize_pin("nmos", "G") == "G"
    assert normalize_pin("nmos", "S") == "S"

def test_normalize_pin_nmos_descriptive():
    assert normalize_pin("nmos", "drain") == "D"
    assert normalize_pin("nmos", "gate") == "G"
    assert normalize_pin("nmos", "source") == "S"

def test_normalize_pin_pmos_numeric():
    assert normalize_pin("pmos", "1") == "D"
    assert normalize_pin("pmos", "2") == "G"
    assert normalize_pin("pmos", "3") == "S"

def test_normalize_pin_opamp_canonical():
    assert normalize_pin("opamp", "invin") == "invin"
    assert normalize_pin("opamp", "noninvin") == "noninvin"
    assert normalize_pin("opamp", "out") == "out"

def test_normalize_pin_opamp_aliases():
    assert normalize_pin("opamp", "in-") == "invin"
    assert normalize_pin("opamp", "in+") == "noninvin"
    assert normalize_pin("opamp", "inverting") == "invin"
    assert normalize_pin("opamp", "non-inverting") == "noninvin"
    assert normalize_pin("opamp", "output") == "out"

def test_normalize_pin_opamp2_canonical():
    assert normalize_pin("opamp2", "In+") == "In+"
    assert normalize_pin("opamp2", "In-") == "In-"
    assert normalize_pin("opamp2", "V+") == "V+"
    assert normalize_pin("opamp2", "V-") == "V-"
    assert normalize_pin("opamp2", "OUT") == "OUT"

def test_normalize_pin_opamp2_aliases():
    assert normalize_pin("opamp2", "noninv") == "In+"
    assert normalize_pin("opamp2", "non-inverting") == "In+"
    assert normalize_pin("opamp2", "inv") == "In-"
    assert normalize_pin("opamp2", "inverting") == "In-"
    assert normalize_pin("opamp2", "vcc") == "V+"
    assert normalize_pin("opamp2", "vee") == "V-"
    assert normalize_pin("opamp2", "output") == "OUT"
    assert normalize_pin("opamp2", "out") == "OUT"

def test_normalize_pin_case_insensitive():
    assert normalize_pin("res", "a") == "A"
    assert normalize_pin("res", "PIN1") == "A"
    assert normalize_pin("voltage", "POSITIVE") == "+"
    assert normalize_pin("npn", "collector") == "C"

def test_normalize_pin_unknown_returns_raw():
    assert normalize_pin("res", "xyz") == "xyz"
    assert normalize_pin("unknown_type", "A") == "A"
