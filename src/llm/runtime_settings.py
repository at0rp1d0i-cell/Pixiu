"""Runtime LLM provider/model selection settings."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SETTINGS_PATH = _PROJECT_ROOT / "config" / "llm_runtime.json"


@dataclass(frozen=True)
class ProviderEnvSpec:
    base_url_env: str
    api_key_env: str


@dataclass(frozen=True)
class ProviderDefaults:
    model: str


@dataclass(frozen=True)
class RoleSelection:
    provider: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class LLMRuntimeSettings:
    default_provider: str
    provider_defaults: dict[str, ProviderDefaults]
    roles: dict[str, RoleSelection]


@dataclass(frozen=True)
class ResolvedRuntimeProvider:
    provider: str
    model: str
    base_url: str
    api_key: str


PROVIDER_ENV_SPECS: dict[str, ProviderEnvSpec] = {
    "deepseek": ProviderEnvSpec(
        base_url_env="DEEPSEEK_API_BASE",
        api_key_env="DEEPSEEK_API_KEY",
    ),
    "openai": ProviderEnvSpec(
        base_url_env="OPENAI_API_BASE",
        api_key_env="OPENAI_API_KEY",
    ),
}


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _parse_role_selection(raw: Any) -> RoleSelection | None:
    if isinstance(raw, str):
        return RoleSelection(provider=raw)
    if not isinstance(raw, dict):
        return None
    provider = raw.get("provider")
    model = raw.get("model")
    provider_str = _as_str(provider) if provider is not None else None
    model_str = _as_str(model) if model is not None else None
    if provider is not None and provider_str is None:
        return None
    if model is not None and model_str is None:
        return None
    return RoleSelection(provider=provider_str, model=model_str)


def load_llm_runtime_settings(settings_path: Path | None = None) -> LLMRuntimeSettings | None:
    """Load runtime LLM role selection from JSON config.

    Returns None when config is missing or malformed.
    """
    path = settings_path or _DEFAULT_SETTINGS_PATH
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    default_provider = _as_str(payload.get("default_provider"))
    raw_provider_defaults = payload.get("provider_defaults")
    raw_roles = payload.get("roles")
    if not default_provider or not isinstance(raw_provider_defaults, dict) or not isinstance(raw_roles, dict):
        return None

    provider_defaults: dict[str, ProviderDefaults] = {}
    for provider, defaults in raw_provider_defaults.items():
        if not isinstance(provider, str) or not isinstance(defaults, dict):
            return None
        model = _as_str(defaults.get("model"))
        if model is None:
            return None
        provider_defaults[provider] = ProviderDefaults(model=model)

    if default_provider not in provider_defaults:
        return None
    if default_provider not in PROVIDER_ENV_SPECS:
        return None

    roles: dict[str, RoleSelection] = {}
    for role, raw_selection in raw_roles.items():
        if not isinstance(role, str):
            return None
        selection = _parse_role_selection(raw_selection)
        if selection is None:
            return None
        provider = selection.provider or default_provider
        if provider not in provider_defaults or provider not in PROVIDER_ENV_SPECS:
            return None
        roles[role] = selection

    return LLMRuntimeSettings(
        default_provider=default_provider,
        provider_defaults=provider_defaults,
        roles=roles,
    )


def resolve_role_provider_connection(
    *,
    role: str,
    environ: dict[str, str] | None = None,
    settings: LLMRuntimeSettings | None = None,
) -> ResolvedRuntimeProvider | None:
    """Resolve provider endpoint/secret from settings + env for a role.

    Returns None when settings do not apply or required env vars are missing.
    """
    runtime_settings = settings or load_llm_runtime_settings()
    if runtime_settings is None:
        return None
    env = os.environ if environ is None else environ

    global_provider_override = _as_str(env.get("PIXIU_LLM_DEFAULT_PROVIDER"))
    selected_default_provider = global_provider_override or runtime_settings.default_provider
    if selected_default_provider not in runtime_settings.provider_defaults:
        return None
    if selected_default_provider not in PROVIDER_ENV_SPECS:
        return None

    selection = runtime_settings.roles.get(role, RoleSelection())
    provider = selection.provider or selected_default_provider
    provider_defaults = runtime_settings.provider_defaults.get(provider)
    provider_env = PROVIDER_ENV_SPECS.get(provider)
    if provider_defaults is None or provider_env is None:
        return None
    model = selection.model or provider_defaults.model

    base_url = _as_str(env.get(provider_env.base_url_env))
    api_key = _as_str(env.get(provider_env.api_key_env))
    if not (model and base_url and api_key):
        return None

    return ResolvedRuntimeProvider(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
    )

