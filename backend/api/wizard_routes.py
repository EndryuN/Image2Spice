import json
import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import ValidationError

from services.vision import identify_components, read_directives, describe_layout, describe_wires
from services.layout import compute_layout
from services.wire_router import compute_wires
from services.schemas import normalize_pin

router = APIRouter(prefix="/api/wizard")
logger = logging.getLogger(__name__)

DICTIONARY_DIR = Path(__file__).parent.parent.parent / "dictionary"


def _load_dictionary() -> dict:
    return json.loads(
        (DICTIONARY_DIR / "components.json").read_text(encoding="utf-8")
    )


def _require_image(file: UploadFile) -> None:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")


@router.post("/identify")
async def wizard_identify(file: UploadFile = File(...)):
    _require_image(file)
    image_bytes = await file.read()
    try:
        components = await identify_components(image_bytes)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(400, detail={"error": "Component identification failed", "details": str(exc)})
    return {"components": components}


@router.post("/directives")
async def wizard_directives(file: UploadFile = File(...)):
    _require_image(file)
    image_bytes = await file.read()
    try:
        directives = await read_directives(image_bytes)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(400, detail={"error": "Directive reading failed", "details": str(exc)})
    return {"directives": directives}


@router.post("/layout")
async def wizard_layout(
    file: UploadFile = File(...),
    components_json: str = Form(""),
):
    _require_image(file)
    image_bytes = await file.read()
    components = json.loads(components_json) if components_json else []

    try:
        layout_desc = await describe_layout(image_bytes, components)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(400, detail={"error": "Layout description failed", "details": str(exc)})

    dictionary = _load_dictionary()
    comp_sizes = {}
    for comp_id, comp_data in dictionary["components"].items():
        bounds = comp_data.get("geometry", {}).get("bounds")
        comp_sizes[comp_id] = {
            "width": comp_data["symbol"]["width"],
            "height": comp_data["symbol"]["height"],
            "bounds": bounds,
        }

    positions = compute_layout(layout_desc, comp_sizes)
    return {"layout": layout_desc, "positions": positions}


@router.post("/wires")
async def wizard_wires(
    file: UploadFile = File(...),
    components_json: str = Form(""),
    positions_json: str = Form(""),
):
    _require_image(file)
    image_bytes = await file.read()
    components = json.loads(components_json) if components_json else []
    positions = json.loads(positions_json) if positions_json else {}

    dictionary = _load_dictionary()
    pin_defs = {}
    component_bounds = {}
    for comp_id, comp_data in dictionary["components"].items():
        pin_defs[comp_id] = comp_data.get("pins", [])
        bounds = comp_data.get("geometry", {}).get("bounds")
        if bounds:
            component_bounds[comp_id] = bounds

    try:
        wire_desc = await describe_wires(image_bytes, components, pin_defs)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(400, detail={"error": "Wire tracing failed", "details": str(exc)})

    # Normalize pin names in wire descriptions
    for conn in wire_desc.get("connections", []):
        for key in ("from", "to"):
            ep = conn.get(key)
            if ep:
                comp_name = ep["component"]
                comp_entry = next((c for c in components if c["instanceName"] == comp_name), None)
                if comp_entry:
                    ep["pin"] = normalize_pin(comp_entry["type"], ep["pin"])

    for gnd in wire_desc.get("grounds", []):
        comp_entry = next((c for c in components if c["instanceName"] == gnd["component"]), None)
        if comp_entry:
            gnd["pin"] = normalize_pin(comp_entry["type"], gnd["pin"])

    for lbl in wire_desc.get("labels", []):
        comp_entry = next((c for c in components if c["instanceName"] == lbl["component"]), None)
        if comp_entry:
            lbl["pin"] = normalize_pin(comp_entry["type"], lbl["pin"])

    comp_map = {}
    for comp in components:
        name = comp["instanceName"]
        if name in positions:
            comp_map[name] = {
                "x": positions[name]["x"],
                "y": positions[name]["y"],
                "type": comp["type"],
            }

    wire_result = compute_wires(comp_map, pin_defs, wire_desc, component_bounds)

    return {
        "wire_descriptions": wire_desc,
        "wires": [{"x1": w[0], "y1": w[1], "x2": w[2], "y2": w[3]} for w in wire_result.wires],
        "flags": wire_result.flags,
    }
