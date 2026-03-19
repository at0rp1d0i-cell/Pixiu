"""Unit tests for shared OpenAI-compatible LLM config helpers."""
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


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


def test_get_researcher_llm_kwargs_loads_dotenv_first():
    from src.llm.openai_compat import get_researcher_llm_kwargs

    with patch('src.llm.openai_compat.load_dotenv_if_available') as mock_load:
        with patch.dict('os.environ', {}, clear=True):
            get_researcher_llm_kwargs(temperature=0.1)

    mock_load.assert_called_once()


def test_build_researcher_llm_passes_through_shared_kwargs():
    from src.llm.openai_compat import build_researcher_llm

    with patch('src.llm.openai_compat.ChatOpenAI') as MockLLM:
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
