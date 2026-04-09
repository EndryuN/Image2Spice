import json
import logging
import re
from pathlib import Path

from services.llm_client import chat_with_vision
from services.schemas import (
    IdentifyResponse,
    DirectivesResponse,
    LayoutResponse,
    WiresResponse,
)

logger = logging.getLogger(__name__)

VISION_MODELS = {
    "local": "qwen3-vl:8b",
    "openrouter": "google/gemma-4-31b-it:free",
    "openai": "gpt-4o",
    "claude": "claude-sonnet-4-20250514",
}
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _extract_json(text: str) -> dict | list:
    """Extract JSON from model response, handling markdown code fences and think tags."""
    # Strip <think>...</think> blocks (qwen3 models include reasoning)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

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


async def identify_components(
    image_bytes: bytes,
    provider: str = "local",
    api_key: str | None = None,
    model: str | None = None,
) -> list[dict]:
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
    vision_model = model or VISION_MODELS.get(provider, VISION_MODELS["local"])
    response = await chat_with_vision(vision_model, system, user, image_bytes, provider=provider, api_key=api_key)
    raw = _extract_json(response)
    items = raw if isinstance(raw, list) else raw.get("components", [])
    parsed = IdentifyResponse.model_validate({"components": items})
    return [c.model_dump() for c in parsed.components]


async def read_directives(
    image_bytes: bytes,
    provider: str = "local",
    api_key: str | None = None,
    model: str | None = None,
) -> list[str]:
    """Step 3: Read SPICE directives from the image."""
    system = _load_prompt("directives_system.txt")
    user = (
        "List every SPICE directive visible in this schematic.\n"
        'Output as a JSON array of strings:\n'
        '[".param RINP=1k PSV=15", ".tran 0.005"]'
    )
    vision_model = model or VISION_MODELS.get(provider, VISION_MODELS["local"])
    response = await chat_with_vision(vision_model, system, user, image_bytes, provider=provider, api_key=api_key)
    raw = _extract_json(response)
    items = raw if isinstance(raw, list) else raw.get("directives", [])
    parsed = DirectivesResponse.model_validate({"directives": items})
    return parsed.directives


async def describe_layout(
    image_bytes: bytes,
    components: list[dict],
    provider: str = "local",
    api_key: str | None = None,
    model: str | None = None,
) -> list[dict]:
    """Step 4: Describe spatial layout."""
    system = _load_prompt("layout_system.txt")
    comp_list = ", ".join(f"{c['instanceName']} ({c['type']})" for c in components)
    user = (
        f"These components were identified in the schematic:\n{comp_list}\n\n"
        "For each component, estimate its position as a percentage of the image dimensions:\n"
        "- x: 0 = left edge, 100 = right edge\n"
        "- y: 0 = top edge, 100 = bottom edge\n\n"
        "Be precise — look at each component's center position in the image.\n\n"
        'Output as JSON array:\n'
        '[{"instanceName": "U1", "x": 50, "y": 45}, ...]'
    )
    vision_model = model or VISION_MODELS.get(provider, VISION_MODELS["local"])
    response = await chat_with_vision(vision_model, system, user, image_bytes, provider=provider, api_key=api_key)
    raw = _extract_json(response)
    items = raw if isinstance(raw, list) else raw.get("layout", [])
    parsed = LayoutResponse.model_validate({"layout": items})
    return [item.model_dump() for item in parsed.layout]


async def describe_wires(
    image_bytes: bytes,
    components: list[dict],
    pin_info: dict,
    provider: str = "local",
    api_key: str | None = None,
    model: str | None = None,
) -> dict:
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
        "Trace EVERY wire in the schematic carefully. For each wire:\n"
        "1. Follow it from one component pin to another component pin\n"
        "2. Use the EXACT pin names listed above for each component\n"
        "3. Note ground symbols (downward triangles) as ground connections\n"
        "4. Note any net labels (like VCC, OUT) at wire endpoints\n\n"
        "Be thorough — include ALL connections visible in the image.\n\n"
        'Output as JSON:\n'
        '{"connections": [{"from": {"component": "R1", "pin": "B"}, "to": {"component": "Q1", "pin": "B"}}], '
        '"grounds": [{"component": "V1", "pin": "-"}], '
        '"labels": [{"component": "R3", "pin": "A", "label": "VCC"}]}'
    )
    vision_model = model or VISION_MODELS.get(provider, VISION_MODELS["local"])
    response = await chat_with_vision(vision_model, system, user, image_bytes, provider=provider, api_key=api_key)
    raw = _extract_json(response)
    if not isinstance(raw, dict):
        raw = {"connections": [], "grounds": [], "labels": []}
    parsed = WiresResponse.model_validate(raw)
    return parsed.model_dump(by_alias=True)
