import json
import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import ValidationError

from services.vision import identify_components, read_directives, describe_layout, describe_wires
from services.llm_client import OpenRouterError
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


def _parse_provider(provider_json: str) -> tuple[str, str | None, str | None]:
    """Parse provider_json form field into (provider, api_key, model)."""
    config = json.loads(provider_json) if provider_json else {}
    return (
        config.get("provider", "local"),
        config.get("apiKey"),
        config.get("model"),
    )


@router.post("/identify")
async def wizard_identify(
    file: UploadFile = File(...),
    provider_json: str = Form("{}"),
):
    _require_image(file)
    image_bytes = await file.read()
    provider, api_key, model = _parse_provider(provider_json)
    try:
        components = await identify_components(image_bytes, provider=provider, api_key=api_key, model=model)
    except (httpx.HTTPError, httpx.TransportError) as exc:
        raise HTTPException(400, detail={"error": "Cannot reach LLM provider. Check Ollama is running or switch to OpenRouter.", "details": str(exc)})
    except (ValidationError, ValueError, OpenRouterError) as exc:
        raise HTTPException(400, detail={"error": "Component identification failed", "details": str(exc)})
    return {"components": components}


@router.post("/directives")
async def wizard_directives(
    file: UploadFile = File(...),
    provider_json: str = Form("{}"),
):
    _require_image(file)
    image_bytes = await file.read()
    provider, api_key, model = _parse_provider(provider_json)
    try:
        directives = await read_directives(image_bytes, provider=provider, api_key=api_key, model=model)
    except (httpx.HTTPError, httpx.TransportError) as exc:
        raise HTTPException(400, detail={"error": "Cannot reach LLM provider. Check Ollama is running or switch to OpenRouter.", "details": str(exc)})
    except (ValidationError, ValueError, OpenRouterError) as exc:
        raise HTTPException(400, detail={"error": "Directive reading failed", "details": str(exc)})
    return {"directives": directives}


@router.post("/layout")
async def wizard_layout(
    file: UploadFile = File(...),
    components_json: str = Form(""),
    provider_json: str = Form("{}"),
    sheet_json: str = Form("{}"),
):
    _require_image(file)
    image_bytes = await file.read()
    components = json.loads(components_json) if components_json else []
    sheet = json.loads(sheet_json) if sheet_json else {}
    sheet_width = sheet.get("width", 880)
    sheet_height = sheet.get("height", 680)
    provider, api_key, model = _parse_provider(provider_json)

    try:
        layout_desc = await describe_layout(image_bytes, components, provider=provider, api_key=api_key, model=model)
    except (httpx.HTTPError, httpx.TransportError) as exc:
        raise HTTPException(400, detail={"error": "Cannot reach LLM provider. Check Ollama is running or switch to OpenRouter.", "details": str(exc)})
    except (ValidationError, ValueError, OpenRouterError) as exc:
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

    positions = compute_layout(layout_desc, comp_sizes, sheet_width=sheet_width, sheet_height=sheet_height)
    return {"layout": layout_desc, "positions": positions}


@router.post("/wires")
async def wizard_wires(
    file: UploadFile = File(...),
    components_json: str = Form(""),
    positions_json: str = Form(""),
    provider_json: str = Form("{}"),
):
    _require_image(file)
    image_bytes = await file.read()
    components = json.loads(components_json) if components_json else []
    positions = json.loads(positions_json) if positions_json else {}
    provider, api_key, model = _parse_provider(provider_json)

    dictionary = _load_dictionary()
    pin_defs = {}
    component_bounds = {}
    symbol_sizes = {}
    for comp_id, comp_data in dictionary["components"].items():
        pin_defs[comp_id] = comp_data.get("pins", [])
        bounds = comp_data.get("geometry", {}).get("bounds")
        if bounds:
            component_bounds[comp_id] = bounds
        symbol_sizes[comp_id] = (comp_data["symbol"]["width"], comp_data["symbol"]["height"])

    try:
        wire_desc = await describe_wires(image_bytes, components, pin_defs, provider=provider, api_key=api_key, model=model)
    except (httpx.HTTPError, httpx.TransportError) as exc:
        raise HTTPException(400, detail={"error": "Cannot reach LLM provider. Check Ollama is running or switch to OpenRouter.", "details": str(exc)})
    except (ValidationError, ValueError, OpenRouterError) as exc:
        logger.error("Wire tracing failed: %s", exc)
        raise HTTPException(400, detail={"error": "Wire tracing failed", "details": str(exc)})
    except Exception as exc:
        logger.error("Unexpected wire error: %s", exc, exc_info=True)
        raise HTTPException(400, detail={"error": "Wire tracing failed unexpectedly", "details": str(exc)})

    logger.info("Wire desc: %d connections, %d grounds, %d labels",
                len(wire_desc.get("connections", [])),
                len(wire_desc.get("grounds", [])),
                len(wire_desc.get("labels", [])))

    # Normalize pin names in wire descriptions
    try:
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
                    "rotation": positions[name].get("rotation", "R0"),
                }

        wire_result = compute_wires(comp_map, pin_defs, wire_desc, component_bounds, symbol_sizes)
    except Exception as exc:
        logger.error("Wire routing failed: %s", exc, exc_info=True)
        raise HTTPException(400, detail={"error": "Wire routing failed", "details": str(exc)})

    return {
        "wire_descriptions": wire_desc,
        "wires": [{"x1": w[0], "y1": w[1], "x2": w[2], "y2": w[3]} for w in wire_result.wires],
        "flags": wire_result.flags,
    }
