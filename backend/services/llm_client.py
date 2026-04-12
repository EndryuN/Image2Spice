from __future__ import annotations

import asyncio
import base64
import logging

import httpx

logger = logging.getLogger(__name__)


class OpenRouterError(Exception):
    """Error from OpenRouter API with status code."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.raw_message = message
        super().__init__(f"OpenRouter error ({status_code}): {message}")

    @property
    def is_auth_error(self) -> bool:
        lower = self.raw_message.lower()
        return (self.status_code == 401
                or "api_key_invalid" in lower
                or "api key not valid" in lower
                or "invalid api key" in lower
                or "invalid_api_key" in lower)

OLLAMA_BASE_URL = "http://localhost:11434"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"
CLAUDE_BASE_URL = "https://api.anthropic.com/v1"

# Free vision models to try in order if the primary is rate-limited
OPENROUTER_FALLBACKS = [
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
    "meta-llama/llama-3.2-11b-vision-instruct:free",
]

_MAX_RETRIES = 5
_RETRY_DELAYS = [3, 6, 12, 20, 30]  # seconds


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
        return await _call_openrouter_with_retry(model, system_prompt, user_prompt, image_bytes, api_key)
    elif provider == "openai":
        if not api_key:
            raise ValueError("API key is required for OpenAI provider")
        return await _call_openai(model, system_prompt, user_prompt, image_bytes, api_key)
    elif provider == "claude":
        if not api_key:
            raise ValueError("API key is required for Claude provider")
        return await _call_claude(model, system_prompt, user_prompt, image_bytes, api_key)
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
    async with httpx.AsyncClient(timeout=1200.0) as client:
        resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]


async def _call_openrouter_with_retry(
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_bytes: bytes,
    api_key: str,
) -> str:
    """Try the requested model with retries, then fall back to other free models."""
    # Build model list: requested model first, then fallbacks (avoiding duplicates)
    models_to_try = [model] + [m for m in OPENROUTER_FALLBACKS if m != model]

    last_error = None
    for try_model in models_to_try:
        for attempt in range(_MAX_RETRIES):
            try:
                return await _call_openrouter(try_model, system_prompt, user_prompt, image_bytes, api_key)
            except OpenRouterError as exc:
                last_error = exc
                if exc.is_auth_error:
                    logger.error("API key invalid — not retrying other models")
                    raise ValueError(
                        "OpenRouter API key is invalid. Check your key in the LLM picker."
                    ) from exc
                elif exc.status_code == 429:
                    if attempt < _MAX_RETRIES - 1:
                        delay = _RETRY_DELAYS[attempt]
                        logger.warning("Rate limited on %s, retrying in %ds (attempt %d/%d)",
                                       try_model, delay, attempt + 1, _MAX_RETRIES)
                        await asyncio.sleep(delay)
                    else:
                        logger.warning("Rate limited on %s after %d retries, trying next model",
                                       try_model, _MAX_RETRIES)
                        break  # try next model
                elif exc.status_code in (400, 403, 404, 502, 503):
                    logger.warning("Provider error %d on %s, trying next model",
                                   exc.status_code, try_model)
                    break  # try next model immediately
                else:
                    raise  # other errors, don't retry

    raise ValueError(f"All models failed. Last error: {last_error}")


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
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
        "temperature": 0.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:5173",
        "X-Title": "image2spice",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
        )
        if resp.status_code != 200:
            logger.error("OpenRouter error %d on %s: %s", resp.status_code, model, resp.text[:500])
            raise OpenRouterError(resp.status_code, resp.text[:500])
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        logger.info("OpenRouter [%s] response (%d chars): %s...", model, len(content), content[:100])
        return content


async def _call_openai(
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
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
        "temperature": 0.0,
        "top_p": 0.95,
        "max_tokens": 16384,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
        )
        if resp.status_code != 200:
            logger.error("OpenAI error %d on %s: %s", resp.status_code, model, resp.text[:500])
            raise ValueError(f"OpenAI error ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        logger.info("OpenAI [%s] response (%d chars): %s...", model, len(content), content[:100])
        return content


async def _call_claude(
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_bytes: bytes,
    api_key: str,
) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": model,
        "max_tokens": 16384,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": user_prompt},
                ],
            },
        ],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            f"{CLAUDE_BASE_URL}/messages",
            json=payload,
            headers=headers,
        )
        if resp.status_code != 200:
            logger.error("Claude error %d on %s: %s", resp.status_code, model, resp.text[:500])
            raise ValueError(f"Claude error ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        content = data["content"][0]["text"]
        logger.info("Claude [%s] response (%d chars): %s...", model, len(content), content[:100])
        return content
