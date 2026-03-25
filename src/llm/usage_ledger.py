"""Run-scoped LLM token/cost usage ledger.

v1 scope:
- Collect usage metadata from LangChain LLM callbacks.
- Keep cumulative counters per run.
- Expose snapshots for control-plane and experiment artifacts.
- Optional cost estimate via env-configured per-1k token rates.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import UTC, datetime
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult


_DEFAULT_RUN_ID = "default"
_LOCK = threading.Lock()
_RUN_LEDGER: dict[str, dict[str, Any]] = {}
_CALL_CONTEXTS: dict[str, dict[str, Any]] = {}


def _safe_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _safe_float(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, parsed)


def _resolve_run_id(run_id: str | None = None) -> str:
    if run_id:
        return run_id

    # Keep a soft dependency on orchestrator runtime.
    try:
        from src.core.orchestrator import runtime as orchestrator_runtime

        active_run_id = orchestrator_runtime.get_current_run_id()
        if active_run_id:
            return active_run_id
    except Exception:
        pass

    return os.getenv("PIXIU_RUN_ID", _DEFAULT_RUN_ID)


def _empty_snapshot(run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
        "by_model": {},
        "call_events": [],
    }


def _normalize_usage_payload(payload: Mapping[str, Any]) -> tuple[int, int, int]:
    prompt_tokens = _safe_int(
        payload.get("prompt_tokens", payload.get("input_tokens"))
    )
    completion_tokens = _safe_int(
        payload.get("completion_tokens", payload.get("output_tokens"))
    )
    total_tokens = _safe_int(payload.get("total_tokens"))
    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens
    return prompt_tokens, completion_tokens, total_tokens


def _first_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    return None


def _extract_usage_from_llm_output(llm_output: Any) -> tuple[int, int, int]:
    mapping = _first_mapping(llm_output)
    if mapping is None:
        return 0, 0, 0

    token_usage = _first_mapping(mapping.get("token_usage"))
    if token_usage is not None:
        return _normalize_usage_payload(token_usage)

    usage = _first_mapping(mapping.get("usage"))
    if usage is not None:
        return _normalize_usage_payload(usage)

    return 0, 0, 0


def _extract_usage_from_generations(generations: Any) -> tuple[int, int, int]:
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0

    if not isinstance(generations, list):
        return 0, 0, 0

    for generation_group in generations:
        if not isinstance(generation_group, list):
            continue
        for generation in generation_group:
            message = getattr(generation, "message", None)
            if message is None:
                continue

            usage_metadata = _first_mapping(getattr(message, "usage_metadata", None))
            response_metadata = _first_mapping(
                getattr(message, "response_metadata", None)
            )

            payload = usage_metadata
            if payload is None and response_metadata is not None:
                payload = _first_mapping(
                    response_metadata.get("token_usage", response_metadata.get("usage"))
                )
            if payload is None:
                continue

            p, c, t = _normalize_usage_payload(payload)
            prompt_tokens += p
            completion_tokens += c
            total_tokens += t

    return prompt_tokens, completion_tokens, total_tokens


def extract_usage_from_llm_result(result: LLMResult) -> dict[str, Any]:
    """Extract normalized usage counters from a LangChain LLMResult."""
    model_name = None
    llm_output = result.llm_output
    llm_output_mapping = _first_mapping(llm_output)
    if llm_output_mapping is not None:
        model_name = llm_output_mapping.get("model_name")

    prompt_tokens, completion_tokens, total_tokens = _extract_usage_from_llm_output(
        llm_output
    )
    if total_tokens == 0 and prompt_tokens == 0 and completion_tokens == 0:
        prompt_tokens, completion_tokens, total_tokens = _extract_usage_from_generations(
            result.generations
        )

    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens

    return {
        "model_name": str(model_name) if model_name else None,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _get_cost_rate(env_name: str) -> float | None:
    raw = os.getenv(env_name)
    if raw is None or raw == "":
        return None
    try:
        rate = float(raw)
    except ValueError:
        return None
    return rate if rate > 0 else None


def _estimate_cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    prompt_rate = _get_cost_rate("PIXIU_LLM_PROMPT_COST_PER_1K_USD")
    completion_rate = _get_cost_rate("PIXIU_LLM_COMPLETION_COST_PER_1K_USD")
    if prompt_rate is None and completion_rate is None:
        return 0.0

    return (
        (prompt_tokens / 1000.0) * (prompt_rate or 0.0)
        + (completion_tokens / 1000.0) * (completion_rate or 0.0)
    )


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _to_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _extract_tag_value(tags: list[str] | None, prefix: str) -> str | None:
    if not tags:
        return None
    for tag in tags:
        if not isinstance(tag, str):
            continue
        if tag.startswith(prefix):
            value = tag[len(prefix):].strip()
            if value:
                return value
    return None


def _now_iso_utc() -> str:
    return datetime.now(UTC).isoformat()


def _build_call_event(
    *,
    run_id: str,
    callback_run_id: str | None,
    model_name: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    success: bool,
    error: BaseException | None,
    latency_ms: float | None,
    tags: list[str] | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    metadata = metadata or {}
    stage = _to_optional_str(metadata.get("stage")) or _extract_tag_value(tags, "stage:")
    llm_profile = _to_optional_str(metadata.get("llm_profile")) or _extract_tag_value(tags, "profile:")
    provider = _to_optional_str(metadata.get("provider")) or "openai_compatible"
    agent_role = _to_optional_str(metadata.get("agent_role"))
    island = _to_optional_str(metadata.get("island"))
    subspace = _to_optional_str(metadata.get("subspace"))
    note_id = _to_optional_str(metadata.get("note_id"))

    return {
        "call_id": callback_run_id or f"call-{int(time.time() * 1000)}",
        "run_id": run_id,
        "stage": stage,
        "round": _to_optional_int(metadata.get("round")),
        "agent_role": agent_role,
        "llm_profile": llm_profile,
        "island": island,
        "subspace": subspace,
        "note_id": note_id,
        "provider": provider,
        "model": _to_optional_str(model_name) or _to_optional_str(metadata.get("model")),
        "prompt_tokens": _safe_int(prompt_tokens),
        "completion_tokens": _safe_int(completion_tokens),
        "total_tokens": _safe_int(total_tokens),
        "latency_ms": round(max(0.0, latency_ms), 3) if latency_ms is not None else None,
        "success": bool(success),
        "error_class": type(error).__name__ if error is not None else None,
        "error_message": str(error) if error is not None else None,
        "timestamp": _now_iso_utc(),
    }


def record_usage(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int | None = None,
    model_name: str | None = None,
    calls: int = 1,
    run_id: str | None = None,
    call_event: Mapping[str, Any] | None = None,
) -> None:
    resolved_run_id = _resolve_run_id(run_id)
    prompt_tokens = _safe_int(prompt_tokens)
    completion_tokens = _safe_int(completion_tokens)
    total_tokens = _safe_int(total_tokens)
    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens
    calls = _safe_int(calls)

    incremental_cost = _estimate_cost_usd(prompt_tokens, completion_tokens)

    with _LOCK:
        aggregate = _RUN_LEDGER.setdefault(resolved_run_id, _empty_snapshot(resolved_run_id))
        aggregate["calls"] += calls
        aggregate["prompt_tokens"] += prompt_tokens
        aggregate["completion_tokens"] += completion_tokens
        aggregate["total_tokens"] += total_tokens
        aggregate["estimated_cost_usd"] = round(
            _safe_float(aggregate["estimated_cost_usd"]) + incremental_cost,
            8,
        )
        if call_event is not None:
            aggregate.setdefault("call_events", []).append(dict(call_event))

        if model_name:
            by_model = aggregate["by_model"]
            model_usage = by_model.setdefault(
                model_name,
                {
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                },
            )
            model_usage["calls"] += calls
            model_usage["prompt_tokens"] += prompt_tokens
            model_usage["completion_tokens"] += completion_tokens
            model_usage["total_tokens"] += total_tokens
            model_usage["estimated_cost_usd"] = round(
                _safe_float(model_usage["estimated_cost_usd"]) + incremental_cost,
                8,
            )


def get_run_usage_snapshot(run_id: str | None = None) -> dict[str, Any]:
    resolved_run_id = _resolve_run_id(run_id)
    with _LOCK:
        aggregate = _RUN_LEDGER.get(resolved_run_id)
        if aggregate is None:
            return _empty_snapshot(resolved_run_id)
        return deepcopy(aggregate)


def reset_usage_ledger(run_id: str | None = None) -> None:
    with _LOCK:
        if run_id is None:
            _RUN_LEDGER.clear()
            _CALL_CONTEXTS.clear()
        else:
            resolved_run_id = _resolve_run_id(run_id)
            _RUN_LEDGER.pop(resolved_run_id, None)
            stale_contexts = [
                callback_run_id
                for callback_run_id, context in _CALL_CONTEXTS.items()
                if context.get("resolved_run_id") == resolved_run_id
            ]
            for callback_run_id in stale_contexts:
                _CALL_CONTEXTS.pop(callback_run_id, None)


@dataclass(slots=True)
class UsageLedgerCallback(BaseCallbackHandler):
    """LangChain callback handler that records usage metadata per run."""

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: Any,
        parent_run_id: Any = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        del prompts, parent_run_id, kwargs
        callback_run_id = _to_optional_str(run_id)
        if callback_run_id is None:
            return
        resolved_run_id = _resolve_run_id()
        with _LOCK:
            _CALL_CONTEXTS[callback_run_id] = {
                "resolved_run_id": resolved_run_id,
                "started_at": time.perf_counter(),
                "tags": list(tags or []),
                "metadata": dict(metadata or {}),
                "serialized": dict(serialized or {}),
            }

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: Any,
        parent_run_id: Any = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        del parent_run_id, kwargs
        callback_run_id = _to_optional_str(run_id)
        with _LOCK:
            context = _CALL_CONTEXTS.pop(callback_run_id, None) if callback_run_id else None

        context_tags = list(tags or [])
        context_metadata = {}
        latency_ms: float | None = None
        if context:
            context_tags = list(context.get("tags") or context_tags)
            context_metadata = dict(context.get("metadata") or {})
            started_at = context.get("started_at")
            if isinstance(started_at, (int, float)):
                latency_ms = (time.perf_counter() - float(started_at)) * 1000.0

        usage = extract_usage_from_llm_result(response)
        resolved_run_id = str(context.get("resolved_run_id")) if context else _resolve_run_id()
        call_event = _build_call_event(
            run_id=resolved_run_id,
            callback_run_id=callback_run_id,
            model_name=usage["model_name"],
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            success=True,
            error=None,
            latency_ms=latency_ms,
            tags=context_tags,
            metadata=context_metadata,
        )
        record_usage(
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            model_name=usage["model_name"],
            calls=1,
            run_id=resolved_run_id,
            call_event=call_event,
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: Any,
        parent_run_id: Any = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        del parent_run_id, kwargs
        callback_run_id = _to_optional_str(run_id)
        with _LOCK:
            context = _CALL_CONTEXTS.pop(callback_run_id, None) if callback_run_id else None

        context_tags = list(tags or [])
        context_metadata = {}
        latency_ms: float | None = None
        model_name: str | None = None
        if context:
            context_tags = list(context.get("tags") or context_tags)
            context_metadata = dict(context.get("metadata") or {})
            model_name = _to_optional_str(context_metadata.get("model"))
            started_at = context.get("started_at")
            if isinstance(started_at, (int, float)):
                latency_ms = (time.perf_counter() - float(started_at)) * 1000.0

        resolved_run_id = str(context.get("resolved_run_id")) if context else _resolve_run_id()
        call_event = _build_call_event(
            run_id=resolved_run_id,
            callback_run_id=callback_run_id,
            model_name=model_name,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            success=False,
            error=error,
            latency_ms=latency_ms,
            tags=context_tags,
            metadata=context_metadata,
        )
        record_usage(
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            model_name=model_name,
            calls=1,
            run_id=resolved_run_id,
            call_event=call_event,
        )


_LEDGER_CALLBACK = UsageLedgerCallback()


def get_usage_ledger_callback() -> UsageLedgerCallback:
    return _LEDGER_CALLBACK
