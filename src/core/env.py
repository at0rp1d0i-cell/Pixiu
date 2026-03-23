"""Shared environment helpers."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Optional

_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
SOURCE_PROCESS_ENV = "process_env"
SOURCE_USER_RUNTIME_ENV = "user_runtime_env"
SOURCE_REPO_ENV = "repo_env"
SOURCE_DEFAULT = "default"


@dataclass(frozen=True)
class ResolvedEnv:
    values: dict[str, str]
    sources: dict[str, str]
    runtime_env_path: Path
    repo_env_path: Path | None


def load_dotenv_if_available(dotenv_path: Optional[str | Path] = None) -> None:
    if dotenv_path is not None:
        try:
            from dotenv import load_dotenv

            load_dotenv(dotenv_path=dotenv_path)
        except ImportError:
            pass
        return

    try:
        resolve_and_apply_layered_env(
            process_env=os.environ,
            target_env=os.environ,
            repo_env_path=get_default_repo_env_path(),
        )
    except ImportError:
        pass


def get_default_runtime_env_path(*, home: str | Path | None = None) -> Path:
    base = Path(home).expanduser() if home is not None else Path.home()
    return base / ".config" / "pixiu" / "runtime.env"


def get_default_repo_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        from dotenv import dotenv_values

        payload = dotenv_values(path)
        return {str(k): str(v) for k, v in payload.items() if k and v is not None}
    except ImportError:
        result: dict[str, str] = {}
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            result[key] = value.strip().strip("'\"")
        return result


def resolve_layered_env(
    *,
    keys: Iterable[str] | None = None,
    process_env: Mapping[str, str] | None = None,
    runtime_env_path: str | Path | None = None,
    repo_env_path: str | Path | None = None,
    defaults: Mapping[str, str] | None = None,
    default_source: str = SOURCE_DEFAULT,
) -> ResolvedEnv:
    runtime_path = Path(runtime_env_path).expanduser() if runtime_env_path is not None else get_default_runtime_env_path()
    repo_path = Path(repo_env_path) if repo_env_path is not None else None

    process_map = os.environ if process_env is None else process_env
    runtime_values = _parse_env_file(runtime_path)
    repo_values = _parse_env_file(repo_path) if repo_path is not None else {}
    default_values = {str(k): str(v) for k, v in (defaults or {}).items()}

    if keys is None:
        ordered_keys = tuple(dict.fromkeys([*default_values.keys(), *repo_values.keys(), *runtime_values.keys(), *process_map.keys()]))
    else:
        ordered_keys = tuple(dict.fromkeys(keys))

    resolved_values: dict[str, str] = {}
    resolved_sources: dict[str, str] = {}
    for key in ordered_keys:
        if key in process_map:
            resolved_values[key] = process_map[key]
            resolved_sources[key] = SOURCE_PROCESS_ENV
            continue
        if key in runtime_values:
            resolved_values[key] = runtime_values[key]
            resolved_sources[key] = SOURCE_USER_RUNTIME_ENV
            continue
        if key in repo_values:
            resolved_values[key] = repo_values[key]
            resolved_sources[key] = SOURCE_REPO_ENV
            continue
        if key in default_values:
            resolved_values[key] = default_values[key]
            resolved_sources[key] = default_source

    return ResolvedEnv(
        values=resolved_values,
        sources=resolved_sources,
        runtime_env_path=runtime_path,
        repo_env_path=repo_path,
    )


def apply_resolved_env(
    resolved: ResolvedEnv,
    *,
    target_env: MutableMapping[str, str] | None = None,
) -> MutableMapping[str, str]:
    target = os.environ if target_env is None else target_env
    target.update(resolved.values)
    return target


def resolve_and_apply_layered_env(
    *,
    keys: Iterable[str] | None = None,
    process_env: Mapping[str, str] | None = None,
    target_env: MutableMapping[str, str] | None = None,
    runtime_env_path: str | Path | None = None,
    repo_env_path: str | Path | None = None,
    defaults: Mapping[str, str] | None = None,
    default_source: str = SOURCE_DEFAULT,
) -> ResolvedEnv:
    target = os.environ if target_env is None else target_env
    explicit = target if process_env is None else process_env
    resolved = resolve_layered_env(
        keys=keys,
        process_env=explicit,
        runtime_env_path=runtime_env_path,
        repo_env_path=repo_env_path,
        defaults=defaults,
        default_source=default_source,
    )
    apply_resolved_env(resolved, target_env=target)
    return resolved


def clear_localhost_proxy_env() -> list[str]:
    """Remove localhost proxy variables that break direct vendor API calls.

    This keeps explicit non-local proxies intact while stripping stale local
    proxy settings such as `127.0.0.1:17890`, which frequently appear in shell
    startup files and cause Tushare downloads to fail in unattended runs.
    """

    cleared: list[str] = []
    for key in _PROXY_VARS:
        value = os.environ.get(key)
        if value and ("127.0.0.1" in value or "localhost" in value):
            os.environ.pop(key, None)
            cleared.append(key)
    return cleared
