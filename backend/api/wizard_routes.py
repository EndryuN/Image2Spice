import json
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import BaseModel

from services.vision import identify_components, read_directives, describe_layout, describe_wires
from services.layout import compute_layout
from services.wire_router import compute_wires

router = APIRouter(prefix="/api/wizard")

DICTIONARY_DIR = Path(__file__).parent.parent.parent / "dictionary"


def _load_dictionary() -> dict:
    return json.loads(
        (DICTIONARY_DIR / "components.json").read_text(encoding="utf-8")
    )


@router.post("/identify")
async def wizard_identify(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    image_bytes = await file.read()
    components = await identify_components(image_bytes)
    return {"components": components}


@router.post("/directives")
async def wizard_directives(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    image_bytes = await file.read()
    directives = await read_directives(image_bytes)
    return {"directives": directives}


@router.post("/layout")
async def wizard_layout(
    file: UploadFile = File(...),
    components_json: str = Form(""),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    image_bytes = await file.read()
    components = json.loads(components_json) if components_json else []

    layout_desc = await describe_layout(image_bytes, components)

    dictionary = _load_dictionary()
    comp_sizes = {}
    for comp_id, comp_data in dictionary["components"].items():
        comp_sizes[comp_id] = {
            "width": comp_data["symbol"]["width"],
            "height": comp_data["symbol"]["height"],
        }

    positions = compute_layout(layout_desc, comp_sizes)
    return {"layout": layout_desc, "positions": positions}


@router.post("/wires")
async def wizard_wires(
    file: UploadFile = File(...),
    components_json: str = Form(""),
    positions_json: str = Form(""),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    image_bytes = await file.read()
    components = json.loads(components_json) if components_json else []
    positions = json.loads(positions_json) if positions_json else {}

    dictionary = _load_dictionary()
    pin_defs = {}
    for comp_id, comp_data in dictionary["components"].items():
        pin_defs[comp_id] = comp_data.get("pins", [])

    wire_desc = await describe_wires(image_bytes, components, pin_defs)

    comp_map = {}
    for comp in components:
        name = comp["instanceName"]
        if name in positions:
            comp_map[name] = {
                "x": positions[name]["x"],
                "y": positions[name]["y"],
                "type": comp["type"],
            }

    wire_result = compute_wires(comp_map, pin_defs, wire_desc)

    return {
        "wire_descriptions": wire_desc,
        "wires": [{"x1": w[0], "y1": w[1], "x2": w[2], "y2": w[3]} for w in wire_result.wires],
        "flags": wire_result.flags,
    }
