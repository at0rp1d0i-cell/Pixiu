"""LiteLLM-backed LangChain chat model compatibility layer."""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import litellm
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.tool import tool_call as make_tool_call
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    return None


def _read_attr_or_key(value: Any, key: str) -> Any:
    mapping = _as_mapping(value)
    if mapping is not None:
        return mapping.get(key)
    return getattr(value, key, None)


def _to_litellm_tool_call(tool: Mapping[str, Any]) -> dict[str, Any]:
    arguments = tool.get("args", {})
    if not isinstance(arguments, str):
        arguments = json.dumps(arguments, ensure_ascii=False)
    return {
        "id": tool.get("id"),
        "type": "function",
        "function": {
            "name": tool.get("name"),
            "arguments": arguments,
        },
    }


def _message_to_litellm(message: BaseMessage) -> dict[str, Any]:
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": message.content}
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": message.content}
    if isinstance(message, ToolMessage):
        return {
            "role": "tool",
            "content": message.content,
            "tool_call_id": message.tool_call_id,
        }

    payload: dict[str, Any] = {"role": "assistant", "content": message.content}
    tool_calls = getattr(message, "tool_calls", None)
    if isinstance(tool_calls, list) and tool_calls:
        payload["tool_calls"] = [_to_litellm_tool_call(call) for call in tool_calls]
    return payload


def _normalize_messages(messages: Sequence[BaseMessage]) -> list[dict[str, Any]]:
    return [_message_to_litellm(message) for message in messages]


def _usage_payload(response: Any) -> dict[str, int]:
    usage = _read_attr_or_key(response, "usage")
    prompt_tokens = int(_read_attr_or_key(usage, "prompt_tokens") or 0)
    completion_tokens = int(_read_attr_or_key(usage, "completion_tokens") or 0)
    total_tokens = int(_read_attr_or_key(usage, "total_tokens") or (prompt_tokens + completion_tokens))
    return {
        "input_tokens": prompt_tokens,
        "output_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _response_model_name(response: Any, fallback_model: str) -> str:
    model_name = _read_attr_or_key(response, "model")
    if isinstance(model_name, str) and model_name:
        return model_name
    return fallback_model


def _first_choice_message(response: Any) -> Any:
    choices = _read_attr_or_key(response, "choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        message = _read_attr_or_key(first_choice, "message")
        if message is not None:
            return message
    return None


def _parse_tool_arguments(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, Mapping):
        return dict(arguments)
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _extract_tool_calls(message: Any) -> list[dict[str, Any]]:
    raw_tool_calls = _read_attr_or_key(message, "tool_calls")
    if not isinstance(raw_tool_calls, list):
        return []

    normalized: list[dict[str, Any]] = []
    for raw_call in raw_tool_calls:
        function_payload = _read_attr_or_key(raw_call, "function")
        name = _read_attr_or_key(function_payload, "name")
        if not isinstance(name, str) or not name:
            continue
        arguments = _read_attr_or_key(function_payload, "arguments")
        normalized.append(
            make_tool_call(
                id=_read_attr_or_key(raw_call, "id"),
                name=name,
                args=_parse_tool_arguments(arguments),
            )
        )
    return normalized


def _message_content(message: Any) -> str | list[str | dict] | None:
    content = _read_attr_or_key(message, "content")
    if isinstance(content, (str, list)) or content is None:
        return content
    return str(content)


def _response_to_chat_result(response: Any, *, fallback_model: str) -> ChatResult:
    message = _first_choice_message(response)
    if message is None:
        ai_message = AIMessage(content="")
    else:
        usage = _usage_payload(response)
        model_name = _response_model_name(response, fallback_model)
        response_metadata = {
            "model_name": model_name,
            "token_usage": usage,
        }
        ai_message = AIMessage(
            content=_message_content(message),
            tool_calls=_extract_tool_calls(message),
            response_metadata=response_metadata,
            usage_metadata=usage,
        )
    return ChatResult(
        generations=[ChatGeneration(message=ai_message)],
        llm_output={
            "model_name": _response_model_name(response, fallback_model),
            "token_usage": _usage_payload(response),
        },
    )


class LiteLLMChatModel(BaseChatModel):
    """Minimal LangChain-compatible chat wrapper over LiteLLM."""

    model: str
    api_key: str
    base_url: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    request_timeout: int | float | None = None
    max_retries: int | None = None

    @property
    def _llm_type(self) -> str:
        return "litellm-chat"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "base_url": self.base_url,
        }

    def _completion_kwargs(self, stop: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": kwargs.pop("messages"),
            "api_key": self.api_key,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "timeout": self.request_timeout,
            "stop": stop,
        }
        if self.max_retries is not None:
            payload["num_retries"] = self.max_retries
        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value
        return payload

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del run_manager
        response = litellm.completion(
            **self._completion_kwargs(messages=_normalize_messages(messages), stop=stop, **kwargs)
        )
        return _response_to_chat_result(response, fallback_model=self.model)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del run_manager
        response = await litellm.acompletion(
            **self._completion_kwargs(messages=_normalize_messages(messages), stop=stop, **kwargs)
        )
        return _response_to_chat_result(response, fallback_model=self.model)

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any],
        *,
        tool_choice: dict | str | bool | None = None,
        parallel_tool_calls: bool | None = None,
        **kwargs: Any,
    ):
        formatted_tools = [convert_to_openai_tool(tool) for tool in tools]
        bound_kwargs: dict[str, Any] = {"tools": formatted_tools}
        tool_names = [
            tool["function"]["name"]
            for tool in formatted_tools
            if isinstance(tool, Mapping)
            and isinstance(tool.get("function"), Mapping)
            and isinstance(tool["function"].get("name"), str)
        ]
        if parallel_tool_calls is not None:
            bound_kwargs["parallel_tool_calls"] = parallel_tool_calls
        if tool_choice is not None:
            if tool_choice is True:
                bound_kwargs["tool_choice"] = "required"
            elif tool_choice == "any":
                bound_kwargs["tool_choice"] = "required"
            elif isinstance(tool_choice, str) and tool_choice in tool_names:
                bound_kwargs["tool_choice"] = {
                    "type": "function",
                    "function": {"name": tool_choice},
                }
            else:
                bound_kwargs["tool_choice"] = tool_choice
        bound_kwargs.update(kwargs)
        return self.bind(**bound_kwargs)
