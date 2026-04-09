import json
import re
from pathlib import Path

from services.ollama_client import chat_with_vision

VISION_MODEL = "qwen3-vl:8b"
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _extract_json(text: str) -> dict | list:
    """Extract JSON from model response, handling markdown code fences."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())
    start = text.find("{")
    start_arr = text.find("[")
    if start_arr != -1 and (start == -1 or start_arr < start):
        end = text.rfind("]")
        if end != -1:
            return json.loads(text[start_arr : end + 1])
    if start != -1:
        end = text.rfind("}")
        if end != -1:
            return json.loads(text[start : end + 1])
    raise ValueError(f"Could not extract JSON from response: {text[:200]}")


async def identify_components(image_bytes: bytes) -> list[dict]:
    """Step 2: Identify components in the image."""
    system = _load_prompt("identify_system.txt")
    user = (
        "List every component in this schematic. For each, provide:\n"
        "- type (one of: res, cap, ind, voltage, current, opamp2, opamp, npn, pnp, nmos, pmos, diode, zener)\n"
        "- instanceName (the label, e.g. R1, U1, V3)\n"
        "- value (the displayed value)\n"
        "- value2 (only for voltage sources with a second value, otherwise omit)\n\n"
        'Output as JSON array:\n[{"type": "res", "instanceName": "R1", "value": "1k"}, ...]'
    )
    response = await chat_with_vision(VISION_MODEL, system, user, image_bytes)
    result = _extract_json(response)
    if isinstance(result, list):
        return result
    return result.get("components", [])


async def read_directives(image_bytes: bytes) -> list[str]:
    """Step 3: Read SPICE directives from the image."""
    system = _load_prompt("directives_system.txt")
    user = (
        "List every SPICE directive visible in this schematic.\n"
        'Output as a JSON array of strings:\n'
        '[".param RINP=1k PSV=15", ".tran 0.005"]'
    )
    response = await chat_with_vision(VISION_MODEL, system, user, image_bytes)
    result = _extract_json(response)
    if isinstance(result, list):
        return result
    return result.get("directives", [])


async def describe_layout(image_bytes: bytes, components: list[dict]) -> list[dict]:
    """Step 4: Describe spatial layout."""
    system = _load_prompt("layout_system.txt")
    comp_list = ", ".join(f"{c['instanceName']} ({c['type']})" for c in components)
    user = (
        f"These components were identified in the schematic:\n{comp_list}\n\n"
        "For each component, describe:\n"
        "- region: which area (top-left, top-center, top-right, center-left, center, center-right, bottom-left, bottom-center, bottom-right)\n"
        "- nearby: which other components are adjacent and in which direction\n\n"
        'Output as JSON array:\n'
        '[{"instanceName": "U1", "region": "center", "nearby": [{"name": "R5", "direction": "above"}]}, ...]'
    )
    response = await chat_with_vision(VISION_MODEL, system, user, image_bytes)
    result = _extract_json(response)
    if isinstance(result, list):
        return result
    return result.get("layout", [])


async def describe_wires(image_bytes: bytes, components: list[dict], pin_info: dict) -> dict:
    """Step 5: Describe wire connections."""
    system = _load_prompt("wires_system.txt")
    comp_lines = []
    for c in components:
        pins = pin_info.get(c["type"], [])
        pin_names = ", ".join(p["name"] for p in pins)
        comp_lines.append(f"- {c['instanceName']} ({c['type']}): pins [{pin_names}]")
    comp_text = "\n".join(comp_lines)
    user = (
        f"These components are in the schematic:\n{comp_text}\n\n"
        "Describe every wire connection:\n"
        "- Which component pin connects to which other component pin\n"
        "- Any ground connections (which pin connects to ground)\n"
        "- Any net labels (which pin has a label and what is it)\n\n"
        'Output as JSON:\n'
        '{"connections": [{"from": {"component": "R5", "pin": "2"}, "to": {"component": "U1", "pin": "In-"}}], '
        '"grounds": [{"component": "V3", "pin": "-"}], '
        '"labels": [{"component": "U1", "pin": "OUT", "label": "OUT"}]}'
    )
    response = await chat_with_vision(VISION_MODEL, system, user, image_bytes)
    result = _extract_json(response)
    if isinstance(result, dict):
        return result
    return {"connections": [], "grounds": [], "labels": []}
