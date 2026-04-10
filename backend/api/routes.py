import json
import os
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.asc_generator import SchematicIR, generate_asc
from services.validator import validate_asc

router = APIRouter(prefix="/api")

DICTIONARY_DIR = Path(__file__).parent.parent.parent / "dictionary"

_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "claude": "CLAUDE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


@router.get("/env-keys")
async def env_keys():
    """Return which providers have API keys configured in .env."""
    available = {}
    for provider, env_var in _ENV_KEYS.items():
        key = os.environ.get(env_var, "")
        available[provider] = bool(key)
    return available


@router.get("/llm-status")
async def llm_status(provider: str = "local", api_key: str = ""):
    """Check if the LLM provider is reachable and authenticated."""
    # Fall back to .env if no key provided
    if not api_key and provider in _ENV_KEYS:
        api_key = os.environ.get(_ENV_KEYS[provider], "")
    if provider == "local":
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get("http://localhost:11434/api/tags")
                resp.raise_for_status()
                return {"online": True}
        except Exception:
            return {"online": False}
    elif provider == "openrouter":
        if not api_key:
            return {"online": False, "error": "No API key provided"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    params={"limit": "1"},
                )
                if resp.status_code == 200:
                    return {"online": True}
                return {"online": False, "error": f"API returned {resp.status_code}"}
        except Exception as exc:
            return {"online": False, "error": str(exc)}
    elif provider == "openai":
        if not api_key:
            return {"online": False, "error": "No API key provided"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if resp.status_code == 200:
                    return {"online": True}
                return {"online": False, "error": f"API returned {resp.status_code}"}
        except Exception as exc:
            return {"online": False, "error": str(exc)}
    elif provider == "claude":
        if not api_key:
            return {"online": False, "error": "No API key provided"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                if resp.status_code == 200:
                    return {"online": True}
                return {"online": False, "error": f"API returned {resp.status_code}"}
        except Exception as exc:
            return {"online": False, "error": str(exc)}
    return {"online": False}


@router.get("/dictionary")
async def get_dictionary():
    components = json.loads(
        (DICTIONARY_DIR / "components.json").read_text(encoding="utf-8")
    )
    directives = json.loads(
        (DICTIONARY_DIR / "directives.json").read_text(encoding="utf-8")
    )
    return {"components": components["components"], "directives": directives}


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
