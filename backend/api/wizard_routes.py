import json
import logging
import os
from pathlib import Path

import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import ValidationError

from services.vision import identify_components, read_directives, describe_layout, describe_wires, analyze_schematic, validate_and_fix, describe_wire_paths
from services.schematic_builder import build_asc, build_graph_from_analysis, _normalize_analysis
from services.llm_client import OpenRouterError
from services.layout import compute_layout
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


_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "claude": "CLAUDE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _parse_provider(provider_json: str) -> tuple[str, str | None, str | None]:
    """Parse provider_json form field into (provider, api_key, model).
    Falls back to environment variables if no API key provided."""
    config = json.loads(provider_json) if provider_json else {}
    provider = config.get("provider", "local")
    api_key = config.get("apiKey")
    # Fall back to .env if no key from frontend
    if not api_key and provider in _ENV_KEYS:
        api_key = os.environ.get(_ENV_KEYS[provider])
    return (provider, api_key, config.get("model"))


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

        # Build a CircuitGraph and route via the VLM-aware path router.
        # Pattern mirrors /api/redraw in this file (see around line 302).
        from services.circuit_graph import CircuitGraph
        from services.wire_router import route_with_paths

        graph = CircuitGraph(dictionary)
        graph.add_components([
            {"name": c["instanceName"], "type": c["type"], "value": c.get("value", "1")}
            for c in components
        ])
        for c in components:
            name = c["instanceName"]
            if name in graph.components and name in positions:
                node = graph.components[name]
                node.position = (positions[name]["x"], positions[name]["y"])
                node.resolved_rotation = positions[name].get("rotation", "R0")

        wire_result = route_with_paths(
            graph,
            wire_paths=wire_desc.get("wire_paths", []),
            buses=wire_desc.get("buses", []),
            connections=wire_desc.get("connections", []),
            grounds=wire_desc.get("grounds", []),
            labels=wire_desc.get("labels", []),
        )
    except Exception as exc:
        logger.error("Wire routing failed: %s", exc, exc_info=True)
        raise HTTPException(400, detail={"error": "Wire routing failed", "details": str(exc)})

    return {
        "wire_descriptions": wire_desc,
        "wires": [{"x1": w[0], "y1": w[1], "x2": w[2], "y2": w[3]} for w in wire_result.wires],
        "flags": wire_result.flags,
    }


@router.post("/generate-asc")
async def wizard_generate_asc(
    file: UploadFile = File(...),
    provider_json: str = Form("{}"),
    sheet_json: str = Form("{}"),
):
    """Multi-pass: VLM analyzes image → validate → fix if needed → build .asc."""
    _require_image(file)
    image_bytes = await file.read()
    provider, api_key, model = _parse_provider(provider_json)
    sheet = json.loads(sheet_json) if sheet_json else {}
    sheet_width = sheet.get("width", 880)
    sheet_height = sheet.get("height", 680)

    # Pass 1: Initial analysis
    try:
        analysis = await analyze_schematic(
            image_bytes,
            provider=provider,
            api_key=api_key,
            model=model,
        )
    except (httpx.HTTPError, httpx.TransportError) as exc:
        raise HTTPException(400, detail={"error": "Cannot reach LLM provider.", "details": str(exc)})
    except (ValueError, OpenRouterError) as exc:
        logger.error("Analysis failed: %s", exc)
        raise HTTPException(400, detail={"error": "Schematic analysis failed", "details": str(exc)})

    dictionary = _load_dictionary()

    # Validate pass 1
    try:
        graph = build_graph_from_analysis(analysis, dictionary)
        issues = graph.validate()
        logger.info("Pass 1 validation: %d components, %d nets, all_connected=%s, unconnected=%s",
                     issues["component_count"], issues["net_count"],
                     issues["all_connected"], issues["unconnected_pins"])
    except Exception as exc:
        logger.error("Validation failed: %s", exc, exc_info=True)
        issues = {"all_connected": True}  # Skip pass 2 if validation itself fails

    # Pass 2: If issues found, ask VLM to fix
    if not issues.get("all_connected", True):
        logger.info("Pass 2: Requesting VLM correction for %d unconnected pins",
                     len(issues.get("unconnected_pins", [])))
        try:
            corrected = await validate_and_fix(
                image_bytes, analysis, issues,
                provider=provider, api_key=api_key, model=model,
            )
            # Use corrected analysis if it has components
            if corrected.get("components"):
                analysis = corrected
                logger.info("Pass 2: Got corrected analysis with %d components, %d connections",
                            len(corrected.get("components", [])),
                            len(corrected.get("connections", [])))
        except Exception as exc:
            logger.warning("Pass 2 correction failed, using pass 1: %s", exc)

    # Extract normalized connections
    _, norm_conns, norm_grounds, norm_labels = _normalize_analysis(analysis)

    # Build final .asc
    try:
        asc_text = build_asc(analysis, dictionary, sheet_width, sheet_height)
    except Exception as exc:
        logger.error("ASC build failed: %s", exc, exc_info=True)
        raise HTTPException(400, detail={"error": "ASC generation failed", "details": str(exc)})

    return {
        "asc": asc_text,
        "connections": norm_conns,
        "grounds": norm_grounds,
        "labels": norm_labels,
    }


@router.post("/redraw-wires")
async def wizard_redraw_wires(
    schematic_json: str = Form("{}"),
):
    """Re-route wires for current component positions without calling the VLM.

    Accepts a schematic JSON with components (with positions) and the original
    connection data. Rebuilds the circuit graph from the provided positions,
    re-runs wire routing, and returns updated wires + flags.
    """
    data = json.loads(schematic_json) if schematic_json else {}
    components = data.get("components", [])
    connections = data.get("connections", [])
    grounds = data.get("grounds", [])
    labels = data.get("labels", [])

    dictionary = _load_dictionary()

    from services.circuit_graph import CircuitGraph
    from services.wire_router import route_nets

    graph = CircuitGraph(dictionary)
    graph.add_components([
        {"name": c["instanceName"], "type": c["type"], "value": c.get("value", "1")}
        for c in components
    ])

    # Normalize connections
    norm_conns: list[dict] = []
    for conn in connections:
        f = conn.get("from", {})
        t = conn.get("to", {})
        if isinstance(f, dict) and isinstance(t, dict):
            norm_conns.append(conn)

    norm_grounds: list[dict] = []
    for gnd in grounds:
        if isinstance(gnd, dict):
            norm_grounds.append(gnd)

    norm_labels: list[dict] = []
    for lbl in labels:
        if isinstance(lbl, dict):
            norm_labels.append(lbl)

    graph.build_nets(norm_conns, norm_grounds, norm_labels)

    # Set positions from the provided component data (user may have dragged them)
    for c in components:
        name = c["instanceName"]
        if name in graph.components:
            node = graph.components[name]
            node.position = (c["position"]["x"], c["position"]["y"])
            node.resolved_rotation = c.get("rotation", "R0")

    # Route wires using net-aware bus routing with direct column wires
    wire_result = route_nets(graph)

    return {
        "wires": [{"x1": w[0], "y1": w[1], "x2": w[2], "y2": w[3]} for w in wire_result.wires],
        "flags": wire_result.flags,
    }
