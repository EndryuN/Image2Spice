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
        "- value (REQUIRED, must never be empty — use the displayed value, or a sensible default if not visible)\n"
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
        "Place each component on a grid:\n"
        "- row: horizontal row number (1=top, 2=next, etc.)\n"
        "- col: column position within row (1=leftmost, 2=next, etc.)\n"
        "- orientation: 'vertical' (pins top/bottom, default) or 'horizontal' (pins left/right)\n\n"
        "Group components on the same horizontal level into the same row.\n"
        "Number columns left to right within each row.\n\n"
        'Output as JSON array:\n'
        '[{"instanceName": "Q1", "row": 1, "col": 1, "orientation": "vertical"}, ...]'
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
    comp_names = ", ".join(c["instanceName"] for c in components)
    user = (
        f"Components in this schematic: {comp_names}\n\n"
        "List EVERY wire connection between components. For each wire, say which component pin connects to which.\n\n"
        "Pin names:\n"
        "- 2-pin (R, C, L, diode): A (pin 1/top/left), B (pin 2/bottom/right)\n"
        "- Sources (V, I): + (positive), - (negative)\n"
        "- NPN/PNP: C (collector), B (base), E (emitter)\n"
        "- MOSFET: D (drain), G (gate), S (source)\n\n"
        "Also list:\n"
        "- Ground connections (triangles or '0' symbol)\n"
        "- Net labels (VCC, OUT, etc.)\n"
        "- wire_paths (optional): per-wire path shape "
        '("L_horizontal_first", "L_vertical_first", "direct_horizontal", "direct_vertical").\n'
        "- buses (optional): shared bus lines touching 3+ pins; give orientation, y_pct or x_pct, and connects list.\n\n"
        "If a path or bus is not visually obvious, leave the field as []. Include ALL connections. Don't skip any wires.\n\n"
        'Output JSON:\n'
        '{"connections": [{"from": {"component": "R1", "pin": "B"}, "to": {"component": "Q1", "pin": "C"}}], '
        '"grounds": [{"component": "R5", "pin": "B"}], '
        '"labels": [{"component": "R3", "pin": "A", "label": "VCC"}], '
        '"wire_paths": [{"from_pin": "R1.A", "to_pin": "Q1.C", "path": "L_horizontal_first"}], '
        '"buses": [{"orientation": "horizontal", "y_pct": 40, "connects": ["R1.B", "R2.B"]}]}'
    )
    vision_model = model or VISION_MODELS.get(provider, VISION_MODELS["local"])
    response = await chat_with_vision(vision_model, system, user, image_bytes, provider=provider, api_key=api_key)
    logger.info("Wire VLM raw response: %s", response[:1000])
    raw = _extract_json(response)
    logger.info("Wire parsed: %d connections, %d grounds, %d labels, %d wire_paths, %d buses",
                len(raw.get("connections", [])) if isinstance(raw, dict) else 0,
                len(raw.get("grounds", [])) if isinstance(raw, dict) else 0,
                len(raw.get("labels", [])) if isinstance(raw, dict) else 0,
                len(raw.get("wire_paths", [])) if isinstance(raw, dict) else 0,
                len(raw.get("buses", [])) if isinstance(raw, dict) else 0)
    if not isinstance(raw, dict):
        raw = {"connections": [], "grounds": [], "labels": [], "wire_paths": [], "buses": []}
    parsed = WiresResponse.model_validate(raw)
    return parsed.model_dump(by_alias=True)


async def analyze_schematic(
    image_bytes: bytes,
    provider: str = "local",
    api_key: str | None = None,
    model: str | None = None,
) -> dict:
    """Single-shot: extract components, connections, grounds, labels from schematic image."""
    system = _load_prompt("generate_asc_system.txt")
    user = (
        "Analyze this circuit schematic image carefully.\n\n"
        "First, count the total number of components you see.\n"
        "Then list ALL of them with exact values, positions, and orientations.\n"
        "Then trace every wire connection between component pins.\n"
        "Then list all ground symbols and net labels.\n\n"
        "Be thorough — every component and every wire matters.\n\n"
        "Output ONLY valid JSON."
    )
    vision_model = model or VISION_MODELS.get(provider, VISION_MODELS["local"])
    response = await chat_with_vision(vision_model, system, user, image_bytes, provider=provider, api_key=api_key)
    logger.info("Analyze VLM response (%d chars): %s...", len(response), response[:200])
    raw = _extract_json(response)
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object, got: {type(raw)}")
    return raw


async def describe_wire_paths(
    image_bytes: bytes,
    components: list[dict],
    connections: list[dict],
    provider: str = "local",
    api_key: str | None = None,
    model: str | None = None,
) -> list[dict]:
    """Describe how each wire is routed in the image — straight, L-shaped, bus, etc."""
    comp_names = ", ".join(c.get("name", "") for c in components)
    conn_summary = "\n".join(
        f"  {c.get('from', '')} -> {c.get('to', '')}" for c in connections[:20]
    )

    system = (
        "You are analyzing wire routing in a circuit schematic image.\n\n"
        "For each wire path visible in the image, describe:\n"
        "- from_pin: which component pin it starts at (e.g. 'V1.+')\n"
        "- to_pin: which component pin it ends at (e.g. 'R1.A')\n"
        "- path: how the wire is routed. One of:\n"
        "  - 'direct_vertical': straight vertical wire (components share same X column)\n"
        "  - 'direct_horizontal': straight horizontal wire (components share same Y row)\n"
        "  - 'L_horizontal_first': L-shaped, goes horizontal then vertical\n"
        "  - 'L_vertical_first': L-shaped, goes vertical then horizontal\n"
        "  - 'bus_horizontal': part of a horizontal bus running across multiple components\n"
        "  - 'bus_vertical': part of a vertical bus\n"
        "- bus_y or bus_x: if bus routing, the approximate Y% (for horizontal) or X% (for vertical) "
        "where the bus runs (0=top/left, 100=bottom/right)\n\n"
        "Also identify buses: if multiple wires share the same horizontal or vertical line, "
        "group them as a bus.\n\n"
        "Output ONLY valid JSON."
    )

    user = (
        f"Components in this schematic: {comp_names}\n\n"
        f"Known connections:\n{conn_summary}\n\n"
        "Look at the image and describe HOW each wire is routed.\n"
        "Pay attention to:\n"
        "- Components in the same column connected by straight vertical wires\n"
        "- Horizontal bus lines running across the top or bottom\n"
        "- L-shaped wires that go horizontal then vertical (or vice versa)\n\n"
        "Also list any buses (horizontal or vertical lines shared by multiple connections):\n"
        '{"wire_paths": [...], "buses": [{"orientation": "horizontal", "y_pct": 10, '
        '"connects": ["V1.+", "R2.A", "V2.-"]}]}\n\n'
        "Output ONLY valid JSON."
    )

    vision_model = model or VISION_MODELS.get(provider, VISION_MODELS["local"])
    response = await chat_with_vision(vision_model, system, user, image_bytes, provider=provider, api_key=api_key)
    logger.info("Wire path VLM response (%d chars): %s...", len(response), response[:200])
    raw = _extract_json(response)
    if isinstance(raw, dict):
        return raw.get("wire_paths", []), raw.get("buses", [])
    return [], []


async def validate_and_fix(
    image_bytes: bytes,
    first_pass: dict,
    issues: dict,
    provider: str = "local",
    api_key: str | None = None,
    model: str | None = None,
) -> dict:
    """Second pass: send first-pass results + issues back to VLM for correction."""
    components = first_pass.get("components", [])
    connections = first_pass.get("connections", [])
    comp_names = [c.get("name", "") for c in components]

    unconnected = issues.get("unconnected_pins", [])
    unconnected_str = ", ".join(f"{c}.{p}" for c, p in unconnected)

    system = (
        "You are validating a circuit schematic analysis. The first pass may have "
        "missed connections or gotten polarities wrong.\n\n"
        "CRITICAL rules for voltage sources:\n"
        "- The LONGER line is the POSITIVE (+) terminal\n"
        "- The SHORTER line is the NEGATIVE (-) terminal\n"
        "- Look carefully at each voltage source to determine which end is + and -\n\n"
        "For every component, EVERY pin must be connected to something.\n"
        "A circuit must be closed — current must have a complete path.\n\n"
        "Output ONLY valid JSON with the complete corrected analysis."
    )

    user = (
        f"First pass found these components: {', '.join(comp_names)}\n\n"
        f"First pass connections:\n{json.dumps(connections, indent=2)}\n\n"
    )
    if unconnected:
        user += f"PROBLEM: These pins are NOT connected to anything: {unconnected_str}\n"
        user += "Every pin must be connected. Add the missing connections.\n\n"
    user += (
        "Look at the image again carefully and output the COMPLETE corrected analysis.\n"
        "Pay special attention to:\n"
        "1. Which terminal is + and which is - on each voltage source (longer line = +)\n"
        "2. Every pin must be connected — trace every wire\n"
        "3. The circuit must be closed (complete current paths)\n\n"
        "Output the full JSON with components, connections, grounds, and labels."
    )

    vision_model = model or VISION_MODELS.get(provider, VISION_MODELS["local"])
    response = await chat_with_vision(vision_model, system, user, image_bytes, provider=provider, api_key=api_key)
    logger.info("Validate VLM response (%d chars): %s...", len(response), response[:200])
    raw = _extract_json(response)
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object from validation pass, got: {type(raw)}")
    return raw
