"""Minimal deterministic risk auditor."""
from __future__ import annotations

from src.factor_pool.pool import FactorPool
from src.schemas.backtest import BacktestReport
from src.schemas.judgment import CorrelationFlag, RiskAuditReport
from src.schemas.thresholds import THRESHOLDS


class RiskAuditor:
    """Minimal deterministic risk audit used to keep the current orchestrator runnable."""

    def __init__(self, factor_pool: FactorPool | None = None):
        self.factor_pool = factor_pool

    async def audit(self, report: BacktestReport) -> RiskAuditReport:
        correlation_flags: list[CorrelationFlag] = []

        if self.factor_pool is not None:
            for existing in self.factor_pool.get_passed_factors(island=report.island, limit=20):
                if existing.get("formula") == report.formula and existing.get("formula") != "":
                    correlation_flags.append(
                        CorrelationFlag(
                            existing_factor_id=existing.get("factor_id", existing.get("id", "unknown")),
                            correlation=1.0,
                            flag_reason="too_similar",
                        )
                    )
                    break

        overfitting_score = 0.0
        if report.error_message:
            overfitting_score = 0.5
        elif report.metrics.turnover_rate > THRESHOLDS.max_turnover_rate:
            overfitting_score = min(
                1.0,
                report.metrics.turnover_rate / max(THRESHOLDS.max_turnover_rate, 1e-9) - 1.0,
            )

        overfitting_flag = overfitting_score > THRESHOLDS.max_overfitting_score
        recommendation = "manual_review" if overfitting_flag or correlation_flags else "clear"
        audit_notes = "存在潜在过拟合或高相似风险。" if recommendation == "manual_review" else "未发现显著风险。"

        return RiskAuditReport(
            factor_id=report.factor_id,
            overfitting_score=overfitting_score,
            overfitting_flag=overfitting_flag,
            correlation_flags=correlation_flags,
            recommendation=recommendation,
            audit_notes=audit_notes,
        )
