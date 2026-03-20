"""Parity tests for FactorPool write paths."""
from __future__ import annotations

import json

import pytest

from src.factor_pool.pool import FactorPool, _InMemoryClient
from src.schemas.backtest import BacktestMetrics, BacktestReport, FactorSpecSnapshot
from src.schemas.factor_pool import FactorPoolRecord
from src.schemas.judgment import CriticVerdict, RiskAuditReport
from src.schemas.research_note import FactorResearchNote
from src.schemas.hypothesis import ExplorationSubspace

pytestmark = pytest.mark.unit


def _make_pool() -> FactorPool:
    pool = FactorPool.__new__(FactorPool)
    pool._storage_mode = "in_memory"
    pool._client = _InMemoryClient()
    pool._collection = pool._client.get_or_create_collection("factor_experiments")
    return pool


def _make_note() -> FactorResearchNote:
    return FactorResearchNote(
        note_id="note-001",
        island="momentum",
        iteration=1,
        hypothesis="价格惯性会延续",
        economic_intuition="资金流入会强化短期趋势。",
        proposed_formula="Mean($close, 5) / Ref($close, 5)",
        final_formula="Mean($close, 5) / Ref($close, 5)",
        exploration_questions=[],
        risk_factors=["风格切换"],
        market_context_date="2026-03-20",
        exploration_subspace=ExplorationSubspace.FACTOR_ALGEBRA,
    )


def _make_report() -> BacktestReport:
    return BacktestReport(
        report_id="report-001",
        note_id="note-001",
        factor_id="factor-001",
        island="momentum",
        formula="Mean($close, 5) / Ref($close, 5)",
        factor_spec=FactorSpecSnapshot(
            formula="Mean($close, 5) / Ref($close, 5)",
            hypothesis="价格惯性会延续",
            economic_rationale="资金流入会强化短期趋势。",
        ),
        metrics=BacktestMetrics(
            sharpe=3.1,
            annualized_return=0.22,
            max_drawdown=0.11,
            ic_mean=0.05,
            ic_std=0.03,
            icir=0.68,
            turnover_rate=0.21,
            coverage=0.9,
        ),
        passed=True,
        execution_succeeded=True,
        execution_time_seconds=1.0,
        qlib_output_raw="{}",
    )


def _make_verdict() -> CriticVerdict:
    return CriticVerdict(
        report_id="report-001",
        factor_id="factor-001",
        note_id="note-001",
        overall_passed=True,
        decision="promote",
        score=0.93,
        checks=[],
        register_to_pool=True,
        pool_tags=["passed", "decision:promote"],
        reason_codes=[],
    )


def _make_risk() -> RiskAuditReport:
    return RiskAuditReport(
        factor_id="factor-001",
        overfitting_score=0.12,
        overfitting_flag=False,
        correlation_flags=[],
        recommendation="clear",
        audit_notes="ok",
    )


def _make_record() -> FactorPoolRecord:
    return FactorPoolRecord(
        factor_id="factor-002",
        note_id="note-002",
        formula="Mean($close, 5) / Ref($close, 5)",
        hypothesis="价格惯性会延续",
        economic_rationale="资金流入会强化短期趋势。",
        backtest_report_id="report-002",
        verdict_id="verdict-002",
        decision="promote",
        score=0.94,
        execution_succeeded=True,
        sharpe=3.2,
        ic_mean=0.06,
        icir=0.7,
        turnover=0.18,
        max_drawdown=0.1,
        coverage=0.92,
        tags=["passed", "decision:promote"],
        subspace_origin=ExplorationSubspace.FACTOR_ALGEBRA.value,
    )


def _core_metadata(metadata: dict) -> dict:
    return {
        "note_id": metadata.get("note_id"),
        "formula": metadata.get("formula"),
        "hypothesis": metadata.get("hypothesis"),
        "economic_rationale": metadata.get("economic_rationale"),
        "backtest_report_id": metadata.get("backtest_report_id"),
        "verdict_id": metadata.get("verdict_id"),
        "decision": metadata.get("decision"),
        "score": metadata.get("score"),
        "sharpe": metadata.get("sharpe"),
        "ic_mean": metadata.get("ic_mean"),
        "icir": metadata.get("icir"),
        "turnover": metadata.get("turnover"),
        "max_drawdown": metadata.get("max_drawdown"),
        "coverage": metadata.get("coverage"),
        "passed": metadata.get("passed"),
        "beats_baseline": metadata.get("beats_baseline"),
        "subspace_origin": metadata.get("subspace_origin"),
        "tags": json.loads(metadata["tags"]) if metadata.get("tags") else [],
    }


def test_register_factor_v1_and_v2_share_core_write_semantics():
    note = _make_note()
    report = _make_report()
    verdict = _make_verdict()
    risk = _make_risk()

    pool_v1 = _make_pool()
    pool_v1.register_factor(report=report, verdict=verdict, risk_report=risk, note=note)
    meta_v1 = pool_v1._collection.get(ids=["factor-001"], include=["metadatas"])[
        "metadatas"
    ][0]
    assert meta_v1["verdict_id"] == verdict.verdict_id
    assert meta_v1["execution_succeeded"] is True

    pool_v2 = _make_pool()
    record = _make_record()
    pool_v2.register_factor_v2(record)
    meta_v2 = pool_v2._collection.get(ids=["factor-002"], include=["metadatas"])[
        "metadatas"
    ][0]

    assert pool_v1._collection.get(ids=["factor-001"], include=["ids"])["ids"] == ["factor-001"]
    assert pool_v2._collection.get(ids=["factor-002"], include=["ids"])["ids"] == ["factor-002"]

    assert _core_metadata(meta_v1) == {
        "note_id": "note-001",
        "formula": "Mean($close, 5) / Ref($close, 5)",
        "hypothesis": "价格惯性会延续",
        "economic_rationale": "资金流入会强化短期趋势。",
        "backtest_report_id": "report-001",
        "verdict_id": verdict.verdict_id,
        "decision": "promote",
        "score": 0.93,
        "sharpe": 3.1,
        "ic_mean": 0.05,
        "icir": 0.68,
        "turnover": 0.21,
        "max_drawdown": 0.11,
        "coverage": 0.9,
        "passed": True,
        "beats_baseline": True,
        "subspace_origin": ExplorationSubspace.FACTOR_ALGEBRA.value,
        "tags": ["passed", "decision:promote"],
    }
    assert _core_metadata(meta_v2) == {
        "note_id": "note-002",
        "formula": "Mean($close, 5) / Ref($close, 5)",
        "hypothesis": "价格惯性会延续",
        "economic_rationale": "资金流入会强化短期趋势。",
        "backtest_report_id": "report-002",
        "verdict_id": "verdict-002",
        "decision": "promote",
        "score": 0.94,
        "sharpe": 3.2,
        "ic_mean": 0.06,
        "icir": 0.7,
        "turnover": 0.18,
        "max_drawdown": 0.1,
        "coverage": 0.92,
        "passed": True,
        "beats_baseline": True,
        "subspace_origin": ExplorationSubspace.FACTOR_ALGEBRA.value,
        "tags": ["passed", "decision:promote"],
    }

    assert pool_v1._collection.get(ids=["factor-001"], include=["documents"])[
        "documents"
    ][0] == "Mean($close, 5) / Ref($close, 5)"
    assert pool_v2._collection.get(ids=["factor-002"], include=["documents"])[
        "documents"
    ][0].startswith("公式: Mean($close, 5) / Ref($close, 5)")
