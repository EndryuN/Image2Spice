import pytest
from services.vision import _extract_json


def test_extract_json_from_code_fence():
    text = '```json\n{"sheet": {"width": 880}}\n```'
    result = _extract_json(text)
    assert result["sheet"]["width"] == 880


def test_extract_json_bare_object():
    text = '{"sheet": {"width": 880}}'
    result = _extract_json(text)
    assert result["sheet"]["width"] == 880


def test_extract_json_bare_array():
    text = '[{"type": "res", "instanceName": "R1"}]'
    result = _extract_json(text)
    assert isinstance(result, list)
    assert result[0]["type"] == "res"


def test_extract_json_array_with_surrounding_text():
    text = 'Here are the components:\n[{"type": "res"}]\nDone.'
    result = _extract_json(text)
    assert isinstance(result, list)
    assert result[0]["type"] == "res"


def test_extract_json_with_surrounding_text():
    text = 'Analysis:\n{"sheet": {"width": 880}}\nDone.'
    result = _extract_json(text)
    assert result["sheet"]["width"] == 880


def test_extract_json_invalid():
    with pytest.raises(ValueError):
        _extract_json("no json here")
