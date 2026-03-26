from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.llm.litellm_chat import LiteLLMChatModel

pytestmark = pytest.mark.unit


def test_litellm_chat_model_sync_roundtrip_records_usage():
    model = LiteLLMChatModel(
        model="gpt-5.4",
        api_key="test-key",
        base_url="https://api.example.com/v1",
        temperature=0.1,
    )

    response = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }
    with patch("src.llm.litellm_chat.litellm.completion", return_value=response) as mock_completion:
        result = model.invoke([HumanMessage(content="hello")])

    assert isinstance(result, AIMessage)
    assert result.content == "ok"
    _, kwargs = mock_completion.call_args
    assert kwargs["model"] == "gpt-5.4"
    assert kwargs["api_key"] == "test-key"
    assert kwargs["base_url"] == "https://api.example.com/v1"


@pytest.mark.asyncio
async def test_litellm_chat_model_async_roundtrip_with_tools():
    model = LiteLLMChatModel(
        model="anthropic/claude-3.5-sonnet",
        api_key="anthropic-key",
        base_url="https://api.anthropic.com",
        temperature=0.1,
    )
    response = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "get_moneyflow_hsgt",
                                "arguments": {"limit": 5},
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 12},
    }

    with patch(
        "src.llm.litellm_chat.litellm.acompletion",
        new=AsyncMock(return_value=response),
    ) as mock_acompletion:
        runnable = model.bind_tools(
            [{"type": "function", "function": {"name": "get_moneyflow_hsgt", "parameters": {"type": "object"}}}],
            tool_choice="get_moneyflow_hsgt",
        )
        result = await runnable.ainvoke([HumanMessage(content="call the tool")])

    assert result.tool_calls
    assert result.tool_calls[0]["name"] == "get_moneyflow_hsgt"
    _, kwargs = mock_acompletion.call_args
    assert kwargs["model"] == "anthropic/claude-3.5-sonnet"
    assert kwargs["tool_choice"]["function"]["name"] == "get_moneyflow_hsgt"
    assert kwargs["tools"][0]["function"]["name"] == "get_moneyflow_hsgt"


@pytest.mark.asyncio
async def test_litellm_chat_model_converts_message_roles():
    model = LiteLLMChatModel(
        model="deepseek/deepseek-chat",
        api_key="deepseek-key",
        base_url="https://api.deepseek.com",
        temperature=0.2,
    )
    response = {
        "choices": [{"message": {"content": "done"}}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
    }

    with patch(
        "src.llm.litellm_chat.litellm.acompletion",
        new=AsyncMock(return_value=response),
    ) as mock_acompletion:
        await model.ainvoke(
            [
                SystemMessage(content="system"),
                HumanMessage(content="user"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "tool_a",
                            "args": {"x": 1},
                            "id": "call_a",
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(content="result", tool_call_id="call_a"),
            ]
        )

    _, kwargs = mock_acompletion.call_args
    messages = kwargs["messages"]
    assert [message["role"] for message in messages] == ["system", "user", "assistant", "tool"]
    assert messages[2]["tool_calls"][0]["function"]["name"] == "tool_a"
    assert messages[3]["tool_call_id"] == "call_a"
