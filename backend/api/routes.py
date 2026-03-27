import json
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from services.vision import analyze_image
from services.refinement import refine_to_asc
from services.asc_generator import SchematicIR, generate_asc
from services.validator import validate_asc

router = APIRouter(prefix="/api")

DICTIONARY_DIR = Path(__file__).parent.parent.parent / "dictionary"


@router.get("/dictionary")
async def get_dictionary():
    components = json.loads(
        (DICTIONARY_DIR / "components.json").read_text(encoding="utf-8")
    )
    directives = json.loads(
        (DICTIONARY_DIR / "directives.json").read_text(encoding="utf-8")
    )
    return {"components": components["components"], "directives": directives}


class GenerateResponse(BaseModel):
    ir: dict
    asc: str
    validation: dict


@router.post("/generate", response_model=GenerateResponse)
async def generate(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")

    image_bytes = await file.read()
    ir, raw_json = await analyze_image(image_bytes)
    asc_text = await refine_to_asc(ir)
    validation = validate_asc(asc_text)

    return GenerateResponse(
        ir=raw_json,
        asc=asc_text,
        validation={"valid": validation.valid, "errors": validation.errors},
    )


class RefineRequest(BaseModel):
    ir: dict


@router.post("/refine")
async def refine(request: RefineRequest):
    ir = _dict_to_ir(request.ir)
    asc_text = generate_asc(ir)
    validation = validate_asc(asc_text)
    return {
        "asc": asc_text,
        "validation": {"valid": validation.valid, "errors": validation.errors},
    }


class ValidateRequest(BaseModel):
    asc: str


@router.post("/validate")
async def validate(request: ValidateRequest):
    result = validate_asc(request.asc)
    return {"valid": result.valid, "errors": result.errors, "warnings": result.warnings}


def _dict_to_ir(data: dict) -> SchematicIR:
    sheet = data.get("sheet", {"width": 880, "height": 680})
    ir = SchematicIR(sheet_width=sheet["width"], sheet_height=sheet["height"])

    for comp in data.get("components", []):
        ir.add_component(
            comp_type=comp["type"],
            instance_name=comp["instanceName"],
            value=comp["value"],
            x=int(comp["position"]["x"]) if "position" in comp else int(comp["x"]),
            y=int(comp["position"]["y"]) if "position" in comp else int(comp["y"]),
            rotation=comp.get("rotation", "R0"),
            value2=comp.get("value2"),
        )

    for wire in data.get("wires", []):
        if "from" in wire:
            ir.add_wire(
                int(wire["from"]["x"]), int(wire["from"]["y"]),
                int(wire["to"]["x"]), int(wire["to"]["y"]),
            )
        else:
            ir.add_wire(int(wire["x1"]), int(wire["y1"]), int(wire["x2"]), int(wire["y2"]))

    for flag in data.get("flags", []):
        pos = flag.get("position", flag)
        name = flag["name"]
        ir.add_flag(name, int(pos["x"]), int(pos["y"]))

    for text in data.get("text", []):
        pos = text.get("position", text)
        ir.add_text(text["content"], int(pos["x"]), int(pos["y"]))

    return ir
