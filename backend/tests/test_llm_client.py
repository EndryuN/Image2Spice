import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.llm_client import chat_with_vision


@pytest.mark.asyncio
async def test_local_provider_sends_ollama_format():
    mock_response = MagicMock()
    mock_response.json.return_value = {"message": {"content": "test response"}}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("services.llm_client.httpx.AsyncClient", return_value=mock_client):
        result = await chat_with_vision(
            model="qwen3-vl:8b",
            system_prompt="system",
            user_prompt="user",
            image_bytes=b"fake_image",
            provider="local",
        )

    assert result == "test response"
    call_args = mock_client.post.call_args
    assert "localhost:11434" in call_args[0][0]
    payload = call_args[1]["json"]
    assert payload["model"] == "qwen3-vl:8b"
    assert payload["messages"][1]["images"] is not None


@pytest.mark.asyncio
async def test_openrouter_provider_sends_openai_format():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "openrouter response"}}]
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("services.llm_client.httpx.AsyncClient", return_value=mock_client):
        result = await chat_with_vision(
            model="qwen/qwen3.6-plus:free",
            system_prompt="system",
            user_prompt="user",
            image_bytes=b"fake_image",
            provider="openrouter",
            api_key="test-key-123",
        )

    assert result == "openrouter response"
    call_args = mock_client.post.call_args
    assert "openrouter.ai" in call_args[0][0]
    headers = call_args[1]["headers"]
    assert headers["Authorization"] == "Bearer test-key-123"
    payload = call_args[1]["json"]
    user_content = payload["messages"][1]["content"]
    assert isinstance(user_content, list)
    assert user_content[1]["type"] == "image_url"


@pytest.mark.asyncio
async def test_openrouter_missing_api_key_raises():
    with pytest.raises(ValueError, match="API key"):
        await chat_with_vision(
            model="qwen/qwen3.6-plus:free",
            system_prompt="system",
            user_prompt="user",
            image_bytes=b"fake_image",
            provider="openrouter",
            api_key=None,
        )


@pytest.mark.asyncio
async def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown provider"):
        await chat_with_vision(
            model="model",
            system_prompt="system",
            user_prompt="user",
            image_bytes=b"fake_image",
            provider="azure",
        )
