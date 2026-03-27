import json
import re
from pathlib import Path

from services.ollama_client import chat_with_vision
from services.asc_generator import SchematicIR

VISION_MODEL = "qwen3-vl:8b"
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _extract_json(text: str) -> dict:
    """Extract JSON from model response, handling markdown code fences."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start : end + 1])
    raise ValueError(f"Could not extract JSON from response: {text[:200]}")


def _json_to_ir(data: dict) -> SchematicIR:
    sheet = data.get("sheet", {"width": 880, "height": 680})
    ir = SchematicIR(sheet_width=sheet["width"], sheet_height=sheet["height"])

    for comp in data.get("components", []):
        ir.add_component(
            comp_type=comp["type"],
            instance_name=comp["instanceName"],
            value=comp["value"],
            x=int(comp["position"]["x"]),
            y=int(comp["position"]["y"]),
            rotation=comp.get("rotation", "R0"),
            value2=comp.get("value2"),
        )

    for wire in data.get("wires", []):
        ir.add_wire(
            x1=int(wire["from"]["x"]),
            y1=int(wire["from"]["y"]),
            x2=int(wire["to"]["x"]),
            y2=int(wire["to"]["y"]),
        )

    for flag in data.get("flags", []):
        ir.add_flag(
            name=flag["name"],
            x=int(flag["position"]["x"]),
            y=int(flag["position"]["y"]),
        )

    for text in data.get("text", []):
        ir.add_text(
            content=text["content"],
            x=int(text["position"]["x"]),
            y=int(text["position"]["y"]),
        )

    return ir


async def analyze_image(image_bytes: bytes) -> tuple[SchematicIR, dict]:
    """Analyze an LTspice screenshot, return (SchematicIR, raw_json_dict)."""
    system_prompt = _load_prompt("vision_system.txt")
    user_prompt = "Analyze this LTspice schematic screenshot. Output the JSON representation of all components, wires, flags, and directives."

    response = await chat_with_vision(VISION_MODEL, system_prompt, user_prompt, image_bytes)
    raw_data = _extract_json(response)
    ir = _json_to_ir(raw_data)
    return ir, raw_data
