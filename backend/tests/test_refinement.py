from services.refinement import _ir_to_json_prompt, _clean_asc_response
from services.asc_generator import SchematicIR


def test_ir_to_json_prompt_structure():
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    ir.add_component("res", "R1", "1k", 100, 100, "R0")
    ir.add_wire(100, 100, 200, 100)
    ir.add_flag("0", 150, 150)
    ir.add_text(".tran 1", 300, 300)

    result = _ir_to_json_prompt(ir)
    import json
    data = json.loads(result)
    assert data["sheet"]["width"] == 880
    assert len(data["components"]) == 1
    assert data["components"][0]["instanceName"] == "R1"
    assert len(data["wires"]) == 1
    assert len(data["flags"]) == 1
    assert len(data["text"]) == 1


def test_ir_to_json_prompt_value2():
    ir = SchematicIR(sheet_width=880, sheet_height=680)
    ir.add_component("voltage", "V1", "5", 100, 100, "R0", value2="AC 1")
    result = _ir_to_json_prompt(ir)
    import json
    data = json.loads(result)
    assert data["components"][0]["value2"] == "AC 1"


def test_clean_asc_response_plain():
    text = "Version 4\nSHEET 1 880 680\n"
    assert _clean_asc_response(text) == "Version 4\nSHEET 1 880 680\n"


def test_clean_asc_response_with_fences():
    text = "```\nVersion 4\nSHEET 1 880 680\n```"
    assert _clean_asc_response(text) == "Version 4\nSHEET 1 880 680\n"


def test_clean_asc_response_with_language_fence():
    text = "```asc\nVersion 4\nSHEET 1 880 680\n```"
    assert _clean_asc_response(text) == "Version 4\nSHEET 1 880 680\n"
