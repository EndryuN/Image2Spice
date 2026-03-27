import pytest
from services.vision import _extract_json, _json_to_ir


def test_extract_json_from_code_fence():
    text = '```json\n{"sheet": {"width": 880, "height": 680}}\n```'
    result = _extract_json(text)
    assert result["sheet"]["width"] == 880


def test_extract_json_bare():
    text = '{"sheet": {"width": 880, "height": 680}}'
    result = _extract_json(text)
    assert result["sheet"]["width"] == 880


def test_extract_json_with_surrounding_text():
    text = 'Here is the analysis:\n{"sheet": {"width": 880, "height": 680}}\nDone.'
    result = _extract_json(text)
    assert result["sheet"]["width"] == 880


def test_extract_json_invalid():
    with pytest.raises(ValueError):
        _extract_json("no json here")


def test_json_to_ir_basic():
    data = {
        "sheet": {"width": 880, "height": 680},
        "components": [
            {
                "type": "res",
                "instanceName": "R1",
                "value": "1k",
                "position": {"x": 272, "y": 128},
                "rotation": "R90",
            }
        ],
        "wires": [{"from": {"x": 100, "y": 100}, "to": {"x": 200, "y": 100}}],
        "flags": [{"name": "0", "position": {"x": 150, "y": 150}}],
        "text": [{"content": ".tran 0.005", "position": {"x": 400, "y": 450}}],
    }
    ir = _json_to_ir(data)
    assert len(ir.components) == 1
    assert ir.components[0].instance_name == "R1"
    assert len(ir.wires) == 1
    assert len(ir.flags) == 1
    assert len(ir.texts) == 1


def test_json_to_ir_with_value2():
    data = {
        "sheet": {"width": 880, "height": 680},
        "components": [
            {
                "type": "voltage",
                "instanceName": "V3",
                "value": "PULSE(0 0.01 0 1u 1u 0.0005 0.001 100)",
                "position": {"x": 112, "y": 288},
                "rotation": "R0",
                "value2": "AC 0.01",
            }
        ],
        "wires": [],
        "flags": [],
        "text": [],
    }
    ir = _json_to_ir(data)
    assert ir.components[0].value2 == "AC 0.01"
