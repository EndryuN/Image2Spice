import json
from pathlib import Path

from services.ollama_client import chat_text
from services.asc_generator import SchematicIR, generate_asc

REFINE_MODEL = "qwen3:14b"
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _ir_to_json_prompt(ir: SchematicIR) -> str:
    """Convert SchematicIR to a JSON string for the refinement prompt."""
    data = {
        "sheet": {"width": ir.sheet_width, "height": ir.sheet_height},
        "components": [],
        "wires": [],
        "flags": [],
        "text": [],
    }
    for c in ir.components:
        comp = {
            "type": c.type,
            "instanceName": c.instance_name,
            "value": c.value,
            "x": c.x,
            "y": c.y,
            "rotation": c.rotation,
        }
        if c.value2:
            comp["value2"] = c.value2
        data["components"].append(comp)

    for w in ir.wires:
        data["wires"].append({"x1": w.x1, "y1": w.y1, "x2": w.x2, "y2": w.y2})

    for f in ir.flags:
        data["flags"].append({"name": f.name, "x": f.x, "y": f.y})

    for t in ir.texts:
        data["text"].append({"content": t.content, "x": t.x, "y": t.y})

    return json.dumps(data, indent=2)


def _clean_asc_response(text: str) -> str:
    """Strip markdown fences or extra text from model response."""
    lines = text.strip().split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines) + "\n"


async def refine_to_asc(ir: SchematicIR) -> str:
    """Use text model to refine JSON IR into .asc, with deterministic fallback."""
    deterministic_asc = generate_asc(ir)

    system_prompt = _load_prompt("refine_system.txt")
    user_prompt = (
        f"Convert this circuit JSON into a valid .asc file:\n\n"
        f"{_ir_to_json_prompt(ir)}\n\n"
        f"Here is a deterministic draft for reference. Improve it if needed "
        f"(fix coordinates, add missing WINDOW lines, etc.), or return it as-is "
        f"if it looks correct:\n\n{deterministic_asc}"
    )

    try:
        response = await chat_text(REFINE_MODEL, system_prompt, user_prompt)
        refined = _clean_asc_response(response)
        if refined.startswith("Version 4"):
            return refined
        return deterministic_asc
    except Exception:
        return deterministic_asc
