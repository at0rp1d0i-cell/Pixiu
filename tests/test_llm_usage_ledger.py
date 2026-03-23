from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.core.experiment_logger import ExperimentLogger
from src.llm import usage_ledger
from src.schemas.state import AgentState

pytestmark = pytest.mark.unit


def _make_llm_result(
    *,
    llm_output: dict | None = None,
    usage_metadata: dict | None = None,
) -> LLMResult:
    message = AIMessage(content="ok")
    if usage_metadata is not None:
        message.usage_metadata = usage_metadata
    generation = ChatGeneration(message=message)
    return LLMResult(generations=[[generation]], llm_output=llm_output)


def test_extract_usage_prefers_llm_output_token_usage():
    result = _make_llm_result(
        llm_output={
            "model_name": "gpt-test",
            "token_usage": {
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "total_tokens": 150,
            },
        }
    )

    usage = usage_ledger.extract_usage_from_llm_result(result)

    assert usage["model_name"] == "gpt-test"
    assert usage["prompt_tokens"] == 120
    assert usage["completion_tokens"] == 30
    assert usage["total_tokens"] == 150


def test_extract_usage_falls_back_to_message_usage_metadata():
    result = _make_llm_result(
        llm_output=None,
        usage_metadata={
            "input_tokens": 90,
            "output_tokens": 10,
            "total_tokens": 100,
        },
    )

    usage = usage_ledger.extract_usage_from_llm_result(result)

    assert usage["prompt_tokens"] == 90
    assert usage["completion_tokens"] == 10
    assert usage["total_tokens"] == 100


def test_usage_callback_records_run_scoped_usage(monkeypatch):
    usage_ledger.reset_usage_ledger()
    monkeypatch.setenv("PIXIU_LLM_PROMPT_COST_PER_1K_USD", "0.01")
    monkeypatch.setenv("PIXIU_LLM_COMPLETION_COST_PER_1K_USD", "0.02")
    monkeypatch.setattr(usage_ledger, "_resolve_run_id", lambda run_id=None: "run-usage-test")

    callback = usage_ledger.get_usage_ledger_callback()
    result = _make_llm_result(
        llm_output={
            "model_name": "gpt-test",
            "token_usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "total_tokens": 1500,
            },
        }
    )

    callback.on_llm_end(
        response=result,
        run_id="ignored-by-ledger",
        parent_run_id=None,
        tags=None,
    )

    snapshot = usage_ledger.get_run_usage_snapshot(run_id="run-usage-test")
    assert snapshot["calls"] == 1
    assert snapshot["prompt_tokens"] == 1000
    assert snapshot["completion_tokens"] == 500
    assert snapshot["total_tokens"] == 1500
    assert snapshot["estimated_cost_usd"] == pytest.approx(0.02)
    assert snapshot["by_model"]["gpt-test"]["total_tokens"] == 1500

    usage_ledger.reset_usage_ledger()


def test_experiment_logger_emits_round_and_cumulative_llm_usage(tmp_path):
    logger = ExperimentLogger(run_id="exp_usage", runs_dir=tmp_path)
    state = AgentState(current_round=1)

    usage_snapshots = [
        {
            "run_id": "run-123",
            "calls": 2,
            "prompt_tokens": 200,
            "completion_tokens": 50,
            "total_tokens": 250,
            "estimated_cost_usd": 0.003,
            "by_model": {},
        },
        {
            "run_id": "run-123",
            "calls": 5,
            "prompt_tokens": 620,
            "completion_tokens": 180,
            "total_tokens": 800,
            "estimated_cost_usd": 0.009,
            "by_model": {},
        },
    ]

    with patch("src.core.experiment_logger.get_run_usage_snapshot", side_effect=usage_snapshots):
        with patch("src.factor_pool.pool.get_factor_pool") as mock_pool:
            mock_pool.return_value.get_passed_factors.return_value = []
            logger.snapshot(round_n=1, state=state)
            logger.snapshot(round_n=2, state=state)

    payload_1 = json.loads((tmp_path / "exp_usage" / "round_001.json").read_text(encoding="utf-8"))
    payload_2 = json.loads((tmp_path / "exp_usage" / "round_002.json").read_text(encoding="utf-8"))

    assert payload_1["llm_usage"]["round"]["total_tokens"] == 250
    assert payload_1["llm_usage"]["cumulative"]["total_tokens"] == 250
    assert payload_2["llm_usage"]["round"]["total_tokens"] == 550
    assert payload_2["llm_usage"]["cumulative"]["total_tokens"] == 800
    assert payload_2["llm_usage"]["run_id"] == "run-123"
