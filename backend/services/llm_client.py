from __future__ import annotations

import base64
import logging

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


async def chat_with_vision(
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_bytes: bytes,
    provider: str = "local",
    api_key: str | None = None,
) -> str:
    if provider == "local":
        return await _call_ollama(model, system_prompt, user_prompt, image_bytes)
    elif provider == "openrouter":
        if not api_key:
            raise ValueError("API key is required for OpenRouter provider")
        return await _call_openrouter(model, system_prompt, user_prompt, image_bytes, api_key)
    else:
        raise ValueError(f"Unknown provider: {provider}")


async def _call_ollama(
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_bytes: bytes,
) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": user_prompt,
                "images": [image_b64],
            },
        ],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    async with httpx.AsyncClient(timeout=600.0) as client:
        resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]


async def _call_openrouter(
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_bytes: bytes,
    api_key: str,
) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                        },
                    },
                ],
            },
        ],
        "temperature": 0.1,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:5173",
        "X-Title": "image2asc",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
        )
        if resp.status_code != 200:
            logger.error("OpenRouter error %d: %s", resp.status_code, resp.text[:500])
            raise ValueError(f"OpenRouter error ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        logger.info("OpenRouter response (%d chars): %s...", len(content), content[:100])
        return content
