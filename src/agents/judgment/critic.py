"""Deterministic Stage 5A critic."""
from __future__ import annotations

from typing import Optional

from src.schemas.backtest import BacktestReport
from src.schemas.judgment import CriticVerdict

from ._scoring import (
    _build_reason_codes,
    _build_threshold_checks,
    _decide,
    _diagnose_failure,
    _score_report,
)


class Critic:
    """Deterministic Stage 5A critic."""

    async def evaluate(self, report: BacktestReport, regime: Optional[str] = None) -> CriticVerdict:
        checks = _build_threshold_checks(report)
        failed_checks = [check for check in checks if not check.passed]
        overall_passed = not report.error_message and not failed_checks
        failure_mode, failure_explanation, suggested_fix = _diagnose_failure(report, failed_checks)
        score = _score_report(report)
        decision = _decide(report, overall_passed, score, failed_checks)
        passed_checks = [check.metric for check in checks if check.passed]
        failed_check_names = [check.metric for check in failed_checks]
        reason_codes = _build_reason_codes(report, failure_mode, failed_checks)

        tags = [f"island:{report.island}"]
        tags.append("passed" if overall_passed else f"failed:{failure_mode.value if failure_mode else 'unknown'}")
        tags.append(f"decision:{decision}")
        if report.oos_passed is True:
            tags.append("validation:oos_passed")
        elif report.oos_passed is False:
            tags.append("validation:oos_failed")
        elif report.oos_window is not None or report.metrics_scope == "discovery":
            tags.append("validation:pending_oos")

        if overall_passed and decision == "promote":
            summary = f"{report.factor_id} passed deterministic and OOS checks with score {score:.2f}."
        elif overall_passed and decision == "candidate":
            summary = f"{report.factor_id} passed deterministic checks and is pending OOS validation."
        elif overall_passed and decision == "archive" and report.oos_passed is False:
            summary = (
                f"{report.factor_id} passed discovery checks but failed out-of-sample validation"
                f" (oos_degradation={report.oos_degradation if report.oos_degradation is not None else 'n/a'})."
            )
        elif overall_passed:
            summary = f"{report.factor_id} passed deterministic checks with score {score:.2f}."
        else:
            summary = failure_explanation

        return CriticVerdict(
            report_id=report.report_id,
            factor_id=report.factor_id,
            note_id=report.note_id,
            overall_passed=overall_passed,
            decision=decision,
            score=score,
            checks=checks,
            passed_checks=passed_checks,
            failed_checks=failed_check_names,
            failure_mode=failure_mode,
            failure_explanation=failure_explanation,
            suggested_fix=suggested_fix,
            summary=summary,
            reason_codes=reason_codes,
            regime_at_judgment=regime,
            register_to_pool=True,
            pool_tags=tags,
        )
