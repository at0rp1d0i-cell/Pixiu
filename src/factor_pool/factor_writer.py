from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Optional

from src.schemas.backtest import BacktestReport
from src.schemas.factor_pool import FactorPoolRecord
from src.schemas.judgment import CriticVerdict, RiskAuditReport
from src.schemas.research_note import FactorResearchNote

logger = logging.getLogger(__name__)


def build_factor_record(
    report: BacktestReport,
    verdict: CriticVerdict,
    risk_report: RiskAuditReport,
    hypothesis: str = "",
    note: Optional[FactorResearchNote] = None,
) -> FactorPoolRecord:
    factor_spec = report.factor_spec
    turnover = report.metrics.turnover_rate
    coverage = report.metrics.coverage
    execution_succeeded = (
        report.execution_succeeded
        if report.execution_succeeded is not None
        else report.status == "success" and report.error_message is None
    )
    subspace_origin = (
        note.exploration_subspace.value if note and note.exploration_subspace else None
    )
    return FactorPoolRecord(
        factor_id=report.factor_id,
        note_id=report.note_id,
        formula=factor_spec.formula if factor_spec else report.formula,
        hypothesis=factor_spec.hypothesis if factor_spec else hypothesis,
        economic_rationale=factor_spec.economic_rationale if factor_spec else "",
        backtest_report_id=report.report_id,
        verdict_id=verdict.verdict_id,
        decision=verdict.decision or "",
        score=verdict.score,
        execution_succeeded=execution_succeeded,
        sharpe=report.metrics.sharpe,
        ic_mean=report.metrics.ic_mean,
        icir=report.metrics.icir,
        turnover=turnover,
        max_drawdown=report.metrics.max_drawdown,
        coverage=coverage,
        created_at=datetime.now(UTC),
        tags=verdict.pool_tags,
        subspace_origin=subspace_origin,
    )


def write_factor(
    collection,
    report: BacktestReport,
    verdict: CriticVerdict,
    risk_report: RiskAuditReport,
    hypothesis: str = "",
    note: Optional[FactorResearchNote] = None,
) -> FactorPoolRecord:
    record = build_factor_record(report, verdict, risk_report, hypothesis=hypothesis, note=note)
    collection.upsert(
        ids=[report.factor_id],
        documents=[record.formula],
        metadatas=[{
            "island": report.island,
            "note_id": record.note_id,
            "formula": record.formula,
            "hypothesis": record.hypothesis,
            "economic_rationale": record.economic_rationale,
            "backtest_report_id": record.backtest_report_id,
            "verdict_id": record.verdict_id,
            "overall_passed": verdict.overall_passed,
            "passed": record.decision == "promote",
            "candidate": record.decision == "candidate",
            "decision": record.decision,
            "score": record.score,
            "sharpe": record.sharpe,
            "ic_mean": record.ic_mean,
            "icir": record.icir,
            "turnover": record.turnover,
            "max_drawdown": record.max_drawdown,
            "coverage": record.coverage if record.coverage is not None else 0.0,
            "failure_mode": verdict.failure_mode or "",
            "reason_codes": json.dumps(verdict.reason_codes),
            "overfitting_score": risk_report.overfitting_score,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "tags": json.dumps(record.tags),
            "subspace_origin": record.subspace_origin or "",
            "execution_succeeded": record.execution_succeeded,
            "beats_baseline": verdict.overall_passed,
            "parse_success": record.execution_succeeded,
            "ic": report.metrics.ic_mean,
        }],
    )
    logger.info(
        "[FactorPool] register_factor: %s → decision=%s, overall_passed=%s, exec_succeeded=%s, Sharpe=%.2f",
        report.factor_id, record.decision, verdict.overall_passed, record.execution_succeeded, report.metrics.sharpe,
    )
    return record


def write_factor_v2(collection, record: FactorPoolRecord) -> None:
    document = (
        f"公式: {record.formula}\n"
        f"假设: {record.hypothesis}\n"
        f"逻辑: {record.economic_rationale}"
    )
    metadata = {
        "factor_id": record.factor_id,
        "note_id": record.note_id,
        "formula": record.formula,
        "hypothesis": record.hypothesis,
        "economic_rationale": record.economic_rationale,
        "backtest_report_id": record.backtest_report_id,
        "verdict_id": record.verdict_id,
        "decision": record.decision,
        "score": record.score,
        "sharpe": record.sharpe or 0.0,
        "ic_mean": record.ic_mean or 0.0,
        "icir": record.icir or 0.0,
        "turnover": record.turnover or 0.0,
        "max_drawdown": record.max_drawdown or 0.0,
        "coverage": record.coverage or 0.0,
        "created_at": record.created_at.isoformat(),
        "tags": json.dumps(record.tags),
        "subspace_origin": record.subspace_origin or "",
        "execution_succeeded": record.execution_succeeded,
        "parse_success": record.execution_succeeded,
        "passed": record.decision == "promote",
        "candidate": record.decision == "candidate",
        "beats_baseline": record.decision == "promote",
    }
    collection.upsert(
        ids=[record.factor_id],
        documents=[document],
        metadatas=[metadata],
    )
    logger.info(
        "[FactorPool] register_factor_v2: %s → decision=%s, score=%.3f",
        record.factor_id, record.decision, record.score,
    )


def archive_research_note(collection, note: FactorResearchNote) -> None:
    collection.upsert(
        ids=[note.note_id],
        documents=[note.hypothesis],
        metadatas=[{
            "island": note.island,
            "proposed_formula": note.proposed_formula,
            "final_formula": note.final_formula or "",
            "status": note.status,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "had_exploration": len(note.exploration_questions) > 0,
        }],
    )
    logger.info("[FactorPool] archive_research_note: %s", note.note_id)
