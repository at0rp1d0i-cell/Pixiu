"""Unit tests for shared OpenAI-compatible LLM config helpers."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

pytestmark = pytest.mark.unit


def test_get_llm_profile_settings_returns_recommended_stage_defaults():
    from src.llm.settings import get_llm_profile_settings

    settings = get_llm_profile_settings("researcher")

    assert settings.temperature == 0.65
    assert settings.max_tokens == 2200
    assert settings.top_p == 0.95
    assert settings.max_retries == 2


def test_get_researcher_llm_kwargs_falls_back_to_openai_env():
    from src.llm.openai_compat import get_researcher_llm_kwargs

    with patch('src.llm.openai_compat.load_dotenv_if_available'):
        with patch.dict(
            'os.environ',
            {
                'RESEARCHER_MODEL': 'deepseek-chat',
                'OPENAI_API_BASE': 'https://api.example.com/v1',
                'OPENAI_API_KEY': 'fallback-key',
            },
            clear=True,
        ):
            kwargs = get_researcher_llm_kwargs(temperature=0.2, max_tokens=123)

    assert kwargs['model'] == 'deepseek-chat'
    assert kwargs['base_url'] == 'https://api.example.com/v1'
    assert kwargs['api_key'] == 'fallback-key'
    assert kwargs['temperature'] == 0.2
    assert kwargs['max_tokens'] == 123


def test_get_researcher_llm_kwargs_applies_profile_defaults():
    from src.llm.openai_compat import get_researcher_llm_kwargs

    with patch('src.llm.openai_compat.load_dotenv_if_available'):
        with patch.dict(
            'os.environ',
            {
                'OPENAI_API_BASE': 'https://api.example-openai.com/v1',
                'OPENAI_API_KEY': 'test-key',
            },
            clear=True,
        ):
            kwargs = get_researcher_llm_kwargs(profile='alignment_checker')

    assert kwargs['temperature'] == 0.0
    assert kwargs['max_tokens'] == 120
    assert kwargs['top_p'] == 1.0
    assert kwargs['request_timeout'] == 30
    assert kwargs['max_retries'] == 1
    assert kwargs["metadata"]["llm_profile"] == "alignment_checker"
    assert kwargs["metadata"]["agent_role"] == "alignment_checker"
    assert kwargs["metadata"]["provider"] == "openai"
    assert kwargs["model"] == "gpt-5.4"
    assert kwargs["base_url"] == "https://api.example-openai.com/v1"
    assert kwargs["api_key"] == "test-key"


def test_get_researcher_llm_kwargs_global_default_provider_does_not_override_explicit_role_binding():
    from src.llm.openai_compat import get_researcher_llm_kwargs
    from src.llm.runtime_settings import (
        LLMRuntimeSettings,
        ProviderDefaults,
        RoleSelection,
        resolve_role_provider_connection as real_resolve_role_provider_connection,
    )

    settings = LLMRuntimeSettings(
        default_provider="deepseek",
        provider_defaults={
            "deepseek": ProviderDefaults(model="deepseek-chat"),
            "openai": ProviderDefaults(model="gpt-5.4"),
        },
        roles={
            "researcher": RoleSelection(provider="deepseek"),
        },
    )

    with patch('src.llm.openai_compat.load_dotenv_if_available'):
        with patch(
            'src.llm.openai_compat.resolve_role_provider_connection',
            side_effect=lambda role: real_resolve_role_provider_connection(role=role, settings=settings),
        ):
            with patch.dict(
                'os.environ',
                {
                    'PIXIU_LLM_DEFAULT_PROVIDER': 'openai',
                    'OPENAI_API_BASE': 'https://api.example-openai.com/v1',
                    'OPENAI_API_KEY': 'openai-key',
                    'DEEPSEEK_API_BASE': 'https://api.deepseek.com',
                    'DEEPSEEK_API_KEY': 'deepseek-key',
                },
                clear=True,
            ):
                kwargs = get_researcher_llm_kwargs(profile='researcher')

    assert kwargs['model'] == 'deepseek-chat'
    assert kwargs['base_url'] == 'https://api.deepseek.com'
    assert kwargs['api_key'] == 'deepseek-key'
    assert kwargs["metadata"]["provider"] == "deepseek"


def test_get_researcher_llm_kwargs_global_default_provider_switches_unbound_role():
    from src.llm.openai_compat import get_researcher_llm_kwargs

    with patch('src.llm.openai_compat.load_dotenv_if_available'):
        with patch.dict(
            'os.environ',
            {
                'PIXIU_LLM_DEFAULT_PROVIDER': 'openai',
                'OPENAI_API_BASE': 'https://api.example-openai.com/v1',
                'OPENAI_API_KEY': 'openai-key',
                'DEEPSEEK_API_BASE': 'https://api.deepseek.com',
                'DEEPSEEK_API_KEY': 'deepseek-key',
            },
            clear=True,
        ):
            kwargs = get_researcher_llm_kwargs(profile='researcher')

    assert kwargs['model'] == 'gpt-5.4'
    assert kwargs['base_url'] == 'https://api.example-openai.com/v1'
    assert kwargs['api_key'] == 'openai-key'
    assert kwargs["metadata"]["provider"] == "openai"


def test_get_researcher_llm_kwargs_uses_role_provider_mapping_when_available():
    from src.llm.openai_compat import get_researcher_llm_kwargs
    from src.llm.runtime_settings import ResolvedRuntimeProvider

    with patch('src.llm.openai_compat.load_dotenv_if_available'):
        with patch(
            'src.llm.openai_compat.resolve_role_provider_connection',
            return_value=ResolvedRuntimeProvider(
                provider='openai',
                model='gpt-5.4',
                base_url='https://api.example-openai.com/v1',
                api_key='openai-key',
            ),
        ):
            with patch.dict(
                'os.environ',
                {
                    'RESEARCHER_MODEL': 'deepseek-chat',
                    'RESEARCHER_BASE_URL': 'https://api.deepseek.com',
                    'RESEARCHER_API_KEY': 'deepseek-key',
                },
                clear=True,
            ):
                kwargs = get_researcher_llm_kwargs(profile='researcher')

    assert kwargs['model'] == 'gpt-5.4'
    assert kwargs['base_url'] == 'https://api.example-openai.com/v1'
    assert kwargs['api_key'] == 'openai-key'
    assert kwargs["metadata"]["provider"] == "openai"


def test_get_researcher_llm_kwargs_keeps_legacy_fallback_when_runtime_settings_missing():
    from src.llm.openai_compat import get_researcher_llm_kwargs

    with patch('src.llm.openai_compat.load_dotenv_if_available'):
        with patch(
            'src.llm.openai_compat.resolve_role_provider_connection',
            return_value=None,
        ):
            with patch.dict(
                'os.environ',
                {
                    'RESEARCHER_MODEL': 'deepseek-chat',
                    'RESEARCHER_BASE_URL': 'https://api.deepseek.com',
                    'RESEARCHER_API_KEY': 'test-key',
                },
                clear=True,
            ):
                kwargs = get_researcher_llm_kwargs(profile='researcher')

    assert kwargs['model'] == 'deepseek-chat'
    assert kwargs['base_url'] == 'https://api.deepseek.com'
    assert kwargs['api_key'] == 'test-key'
    assert kwargs["metadata"]["provider"] == "openai_compatible"


def test_get_researcher_llm_kwargs_loads_dotenv_first():
    from src.llm.openai_compat import get_researcher_llm_kwargs

    with patch('src.llm.openai_compat.load_dotenv_if_available') as mock_load:
        with patch.dict('os.environ', {}, clear=True):
            get_researcher_llm_kwargs(temperature=0.1)

    mock_load.assert_called_once()


def test_build_researcher_llm_passes_through_shared_kwargs():
    from src.llm.openai_compat import build_researcher_llm

    with patch('src.llm.openai_compat.LiteLLMChatModel') as MockLLM:
        instance = MagicMock()
        MockLLM.return_value = instance

        with patch('src.llm.openai_compat.load_dotenv_if_available'):
            with patch.dict(
                'os.environ',
                {
                    'RESEARCHER_MODEL': 'deepseek-chat',
                    'RESEARCHER_BASE_URL': 'https://api.deepseek.com',
                    'RESEARCHER_API_KEY': 'test-key',
                },
                clear=True,
            ):
                result = build_researcher_llm(temperature=0.5)

    _, kwargs = MockLLM.call_args
    assert kwargs['model'] == 'deepseek-chat'
    assert kwargs['base_url'] == 'https://api.deepseek.com'
    assert kwargs['api_key'] == 'test-key'
    assert kwargs['temperature'] == 0.5
    assert result is instance


def test_build_researcher_llm_anthropic_profile_uses_litellm_model():
    from src.llm.openai_compat import build_researcher_llm

    with patch('src.llm.openai_compat.LiteLLMChatModel') as MockLLM:
        instance = MagicMock()
        MockLLM.return_value = instance

        with patch('src.llm.openai_compat.load_dotenv_if_available'):
            with patch.dict(
                'os.environ',
                {
                    'PIXIU_LLM_DEFAULT_PROVIDER': 'anthropic',
                    'ANTHROPIC_API_BASE': 'https://api.anthropic.example',
                    'ANTHROPIC_API_KEY': 'anthropic-key',
                },
                clear=True,
            ):
                result = build_researcher_llm(profile='exploration_agent')

    _, kwargs = MockLLM.call_args
    assert kwargs['model'] == 'anthropic/claude-3.5-sonnet'
    assert kwargs['base_url'] == 'https://api.anthropic.example'
    assert kwargs['api_key'] == 'anthropic-key'
    assert kwargs["metadata"]["provider"] == "anthropic"
    assert result is instance


def test_build_researcher_llm_anthropic_profile_uses_default_base_url_when_env_missing():
    from src.llm.openai_compat import build_researcher_llm
    from src.llm.runtime_settings import (
        LLMRuntimeSettings,
        ProviderDefaults,
        RoleSelection,
        resolve_role_provider_connection as real_resolve_role_provider_connection,
    )

    settings = LLMRuntimeSettings(
        default_provider="openai",
        provider_defaults={
            "openai": ProviderDefaults(model="gpt-5.4"),
            "anthropic": ProviderDefaults(model="anthropic/claude-3.5-sonnet"),
        },
        roles={
            "exploration_agent": RoleSelection(provider="anthropic"),
        },
    )

    with patch('src.llm.openai_compat.LiteLLMChatModel') as MockLLM:
        instance = MagicMock()
        MockLLM.return_value = instance

        with patch('src.llm.openai_compat.load_dotenv_if_available'):
            with patch(
                'src.llm.openai_compat.resolve_role_provider_connection',
                side_effect=lambda role: real_resolve_role_provider_connection(role=role, settings=settings),
            ):
                with patch.dict(
                    'os.environ',
                    {
                        'ANTHROPIC_API_KEY': 'anthropic-key',
                    },
                    clear=True,
                ):
                    result = build_researcher_llm(profile='exploration_agent')

    _, kwargs = MockLLM.call_args
    assert kwargs['model'] == 'anthropic/claude-3.5-sonnet'
    assert kwargs['base_url'] == 'https://api.anthropic.com'
    assert kwargs['api_key'] == 'anthropic-key'
    assert result is instance


def test_get_researcher_llm_kwargs_injects_usage_ledger_callback_by_default():
    from src.llm.openai_compat import get_researcher_llm_kwargs
    from src.llm.usage_ledger import UsageLedgerCallback

    with patch('src.llm.openai_compat.load_dotenv_if_available'):
        with patch.dict(
            'os.environ',
            {
                'RESEARCHER_MODEL': 'deepseek-chat',
                'RESEARCHER_BASE_URL': 'https://api.deepseek.com',
                'RESEARCHER_API_KEY': 'test-key',
            },
            clear=True,
        ):
            kwargs = get_researcher_llm_kwargs(temperature=0.2)

    assert any(isinstance(cb, UsageLedgerCallback) for cb in kwargs["callbacks"])


def test_get_researcher_llm_kwargs_preserves_existing_callbacks():
    from src.llm.openai_compat import get_researcher_llm_kwargs
    from src.llm.usage_ledger import UsageLedgerCallback

    custom_callback = object()
    with patch('src.llm.openai_compat.load_dotenv_if_available'):
        with patch.dict(
            'os.environ',
            {
                'RESEARCHER_MODEL': 'deepseek-chat',
                'RESEARCHER_BASE_URL': 'https://api.deepseek.com',
                'RESEARCHER_API_KEY': 'test-key',
            },
            clear=True,
        ):
            kwargs = get_researcher_llm_kwargs(
                temperature=0.2,
                callbacks=[custom_callback],
            )

    assert custom_callback in kwargs["callbacks"]
    assert sum(
        1 for cb in kwargs["callbacks"] if isinstance(cb, UsageLedgerCallback)
    ) == 1


def test_litellm_chat_model_ainvoke_routes_anthropic_provider_through_litellm():
    from src.llm.litellm_chat import LiteLLMChatModel

    captured: dict[str, object] = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return {
            "model": kwargs["model"],
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "ok",
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
            },
        }

    model = LiteLLMChatModel(
        model="anthropic/claude-3.5-sonnet",
        base_url="https://api.anthropic.example",
        api_key="anthropic-key",
        temperature=0.0,
    )

    with patch("src.llm.litellm_chat.litellm.acompletion", side_effect=fake_acompletion):
        message = asyncio.run(model.ainvoke([HumanMessage(content="ping")]))

    assert message.content == "ok"
    assert captured["model"] == "anthropic/claude-3.5-sonnet"
    assert captured["base_url"] == "https://api.anthropic.example"
    assert captured["api_key"] == "anthropic-key"
    assert captured["messages"][0]["role"] == "user"


def test_litellm_chat_model_bind_tools_passes_openai_tool_schema():
    from src.llm.litellm_chat import LiteLLMChatModel

    captured: dict[str, object] = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return {
            "model": kwargs["model"],
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "get_margin_data",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 3,
                "total_tokens": 8,
            },
        }

    model = LiteLLMChatModel(
        model="gpt-5.4",
        base_url="https://api.example-openai.com/v1",
        api_key="openai-key",
        temperature=0.0,
    )
    tool_schema = {
        "name": "get_margin_data",
        "description": "Fetch margin data",
        "parameters": {"type": "object", "properties": {}},
    }

    bound = model.bind_tools([tool_schema], tool_choice="get_margin_data")

    with patch("src.llm.litellm_chat.litellm.acompletion", side_effect=fake_acompletion):
        message = asyncio.run(bound.ainvoke([HumanMessage(content="call tool")]))

    assert captured["tool_choice"] == {
        "type": "function",
        "function": {"name": "get_margin_data"},
    }
    assert captured["tools"][0]["function"]["name"] == "get_margin_data"
    assert message.tool_calls[0]["name"] == "get_margin_data"


def test_build_researcher_llm_market_analyst_bind_tools_routes_through_litellm():
    from src.llm.openai_compat import build_researcher_llm

    captured: dict[str, object] = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return {
            "model": kwargs["model"],
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "get_margin_data",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 7,
                "completion_tokens": 4,
                "total_tokens": 11,
            },
        }

    with patch('src.llm.openai_compat.load_dotenv_if_available'):
        with patch.dict(
            'os.environ',
            {
                'OPENAI_API_BASE': 'https://api.example-openai.com/v1',
                'OPENAI_API_KEY': 'openai-key',
            },
            clear=True,
        ):
            model = build_researcher_llm(profile='market_analyst')

    bound = model.bind_tools(
        [
            {
                "name": "get_margin_data",
                "description": "Fetch margin data",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
        tool_choice="get_margin_data",
    )

    with patch("src.llm.litellm_chat.litellm.acompletion", side_effect=fake_acompletion):
        message = asyncio.run(bound.ainvoke([HumanMessage(content="call tool")]))

    assert captured["model"] == "gpt-5.4"
    assert captured["base_url"] == "https://api.example-openai.com/v1"
    assert captured["api_key"] == "openai-key"
    assert captured["tool_choice"] == {
        "type": "function",
        "function": {"name": "get_margin_data"},
    }
    assert captured["tools"][0]["function"]["name"] == "get_margin_data"
    assert message.tool_calls[0]["name"] == "get_margin_data"
