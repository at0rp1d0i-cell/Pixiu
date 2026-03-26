"""Unit tests for runtime LLM role/provider settings."""
from pathlib import Path

import pytest

from src.llm.runtime_settings import (
    ProviderDefaults,
    RoleSelection,
    load_llm_runtime_settings,
    resolve_role_provider_connection,
)

pytestmark = pytest.mark.unit


def test_load_llm_runtime_settings_from_json(tmp_path: Path):
    config = tmp_path / "llm_runtime.json"
    config.write_text(
        (
            "{"
            "\"default_provider\":\"deepseek\","
            "\"provider_defaults\":{"
            "\"deepseek\":{\"model\":\"deepseek-chat\"},"
            "\"openai\":{\"model\":\"gpt-5.4\"}"
            "},"
            "\"roles\":{\"researcher\":{\"provider\":\"openai\"}}"
            "}"
        ),
        encoding="utf-8",
    )

    settings = load_llm_runtime_settings(config)

    assert settings is not None
    assert settings.default_provider == "deepseek"
    assert settings.provider_defaults["deepseek"] == ProviderDefaults(model="deepseek-chat")
    assert settings.roles["researcher"] == RoleSelection(provider="openai", model=None)


def test_load_llm_runtime_settings_returns_none_for_invalid_schema(tmp_path: Path):
    config = tmp_path / "llm_runtime.json"
    config.write_text("{\"provider_defaults\":{},\"roles\":{}}", encoding="utf-8")

    assert load_llm_runtime_settings(config) is None


def test_resolve_role_provider_connection_uses_role_mapping(tmp_path: Path):
    config = tmp_path / "llm_runtime.json"
    config.write_text(
        (
            "{"
            "\"default_provider\":\"deepseek\","
            "\"provider_defaults\":{"
            "\"deepseek\":{\"model\":\"deepseek-chat\"},"
            "\"openai\":{\"model\":\"gpt-5.4\"}"
            "},"
            "\"roles\":{\"researcher\":{\"provider\":\"openai\"}}"
            "}"
        ),
        encoding="utf-8",
    )
    settings = load_llm_runtime_settings(config)
    assert settings is not None

    resolved = resolve_role_provider_connection(
        role="researcher",
        settings=settings,
        environ={
            "OPENAI_API_BASE": "https://api.example.com/v1",
            "OPENAI_API_KEY": "key",
            "DEEPSEEK_API_BASE": "https://api.deepseek.com",
            "DEEPSEEK_API_KEY": "deepseek-key",
        },
    )

    assert resolved is not None
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-5.4"
    assert resolved.base_url == "https://api.example.com/v1"
    assert resolved.api_key == "key"


def test_resolve_role_provider_connection_uses_global_default_selector(tmp_path: Path):
    config = tmp_path / "llm_runtime.json"
    config.write_text(
        (
            "{"
            "\"default_provider\":\"deepseek\","
            "\"provider_defaults\":{"
            "\"deepseek\":{\"model\":\"deepseek-chat\"},"
            "\"openai\":{\"model\":\"gpt-5.4\"}"
            "},"
            "\"roles\":{}"
            "}"
        ),
        encoding="utf-8",
    )
    settings = load_llm_runtime_settings(config)
    assert settings is not None

    resolved = resolve_role_provider_connection(
        role="researcher",
        settings=settings,
        environ={
            "PIXIU_LLM_DEFAULT_PROVIDER": "openai",
            "OPENAI_API_BASE": "https://api.example.com/v1",
            "OPENAI_API_KEY": "key",
            "DEEPSEEK_API_BASE": "https://api.deepseek.com",
            "DEEPSEEK_API_KEY": "deepseek-key",
        },
    )
    assert resolved is not None
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-5.4"


def test_resolve_role_provider_connection_returns_none_when_env_missing(tmp_path: Path):
    config = tmp_path / "llm_runtime.json"
    config.write_text(
        (
            "{"
            "\"default_provider\":\"openai\","
            "\"provider_defaults\":{\"openai\":{\"model\":\"gpt-5.4\"}},"
            "\"roles\":{}"
            "}"
        ),
        encoding="utf-8",
    )
    settings = load_llm_runtime_settings(config)
    assert settings is not None

    resolved = resolve_role_provider_connection(
        role="researcher",
        settings=settings,
        environ={"OPENAI_API_BASE": "https://api.example.com/v1"},
    )
    assert resolved is None


def test_resolve_role_provider_connection_anthropic_uses_default_base_url(tmp_path: Path):
    config = tmp_path / "llm_runtime.json"
    config.write_text(
        (
            "{"
            "\"default_provider\":\"anthropic\","
            "\"provider_defaults\":{\"anthropic\":{\"model\":\"anthropic/claude-3.5-sonnet\"}},"
            "\"roles\":{}"
            "}"
        ),
        encoding="utf-8",
    )
    settings = load_llm_runtime_settings(config)
    assert settings is not None

    resolved = resolve_role_provider_connection(
        role="researcher",
        settings=settings,
        environ={"ANTHROPIC_API_KEY": "key"},
    )
    assert resolved is not None
    assert resolved.provider == "anthropic"
    assert resolved.model == "anthropic/claude-3.5-sonnet"
    assert resolved.base_url == "https://api.anthropic.com"
    assert resolved.api_key == "key"
