"""Stage 5 failure constraint extractor."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, UTC
from typing import Optional

from src.schemas.failure_constraint import FailureConstraint, FailureMode
from src.schemas.judgment import CriticVerdict
from src.schemas.research_note import FactorResearchNote

# From ThresholdCheck.metric to FailureMode
_METRIC_TO_FAILURE_MODE: dict[str, FailureMode] = {
    "sharpe": FailureMode.LOW_SHARPE,
    "ic_mean": FailureMode.NO_IC,
    "icir": FailureMode.NO_IC,
    "turnover": FailureMode.HIGH_TURNOVER,
    "max_drawdown": FailureMode.HIGH_DRAWDOWN,
    "coverage": FailureMode.LOW_COVERAGE,
}

# These failure modes are always severity=hard
_HARD_FAILURE_MODES = {
    FailureMode.EXECUTION_ERROR,
    FailureMode.HIGH_TURNOVER,
    FailureMode.OVERFITTING,
}


class ConstraintExtractor:
    """从 CriticVerdict 提取 FailureConstraint。

    仅对 overall_passed=False 的 verdict 生效。
    """

    def extract(
        self,
        verdict: CriticVerdict,
        note: FactorResearchNote,
    ) -> Optional[FailureConstraint]:
        """提取失败约束，若 verdict 已通过则返回 None。"""
        if verdict.overall_passed:
            return None

        failure_mode = self._classify_failure_mode(verdict)
        formula = note.final_formula or note.proposed_formula
        formula_pattern = self._extract_pattern(formula)
        severity = self._determine_severity(failure_mode, verdict)
        constraint_rule = self._generate_rule(failure_mode, formula_pattern, verdict, note)

        return FailureConstraint(
            constraint_id=str(uuid.uuid4()),
            source_note_id=note.note_id,
            source_verdict_id=verdict.verdict_id,
            failure_mode=failure_mode,
            island=note.island,
            subspace=note.exploration_subspace.value if note.exploration_subspace else None,
            formula_pattern=formula_pattern,
            constraint_rule=constraint_rule,
            severity=severity,
            created_at=datetime.now(UTC).isoformat(),
            applicable_regimes=note.applicable_regimes if note.applicable_regimes else None,
        )

    def _classify_failure_mode(self, verdict: CriticVerdict) -> FailureMode:
        """根据 verdict.failure_mode 或 failed checks 映射到标准化 FailureMode。"""
        if verdict.failure_mode is not None:
            return verdict.failure_mode

        for check in verdict.checks:
            if not check.passed:
                return _METRIC_TO_FAILURE_MODE.get(check.metric, FailureMode.LOW_SHARPE)

        return FailureMode.LOW_SHARPE

    def _extract_pattern(self, formula: str) -> str:
        """将具体公式抽象为结构模式。

        规则：
        - 1-10  → N_SHORT（短窗口）
        - 11-60 → N_MID  （中窗口）
        - 61+   → N_LONG （长窗口）
        - 保留算子结构和字段名
        """
        if not formula:
            return ""

        def _classify(m: re.Match) -> str:
            n = int(m.group())
            if n <= 10:
                return "N_SHORT"
            elif n <= 60:
                return "N_MID"
            else:
                return "N_LONG"

        pattern = re.sub(r'\b\d+\b', _classify, formula)
        return pattern

    def _determine_severity(self, failure_mode: FailureMode, verdict: CriticVerdict) -> str:
        """判断约束严重程度：hard（prefilter 直接拒绝）或 warning（注入 prompt）。"""
        if failure_mode in _HARD_FAILURE_MODES:
            return "hard"
        failed_count = len([c for c in verdict.checks if not c.passed])
        if failed_count >= 3:
            return "hard"
        return "warning"

    def _generate_rule(
        self,
        failure_mode: FailureMode,
        formula_pattern: str,
        verdict: CriticVerdict,
        note: FactorResearchNote,
    ) -> str:
        """生成人类可读的约束规则描述。"""
        island = note.island
        explanation = verdict.failure_explanation or ""
        suggested_fix = verdict.suggested_fix or ""

        templates: dict[FailureMode, str] = {
            FailureMode.LOW_SHARPE: (
                f"avoid pattern '{formula_pattern}' in {island} island — "
                f"low Sharpe: {explanation}"
            ),
            FailureMode.HIGH_TURNOVER: (
                f"avoid pattern '{formula_pattern}' in {island} island — "
                f"high turnover: {explanation}. Fix: {suggested_fix}"
            ),
            FailureMode.NO_IC: (
                f"avoid pattern '{formula_pattern}' in {island} island — "
                f"near-zero IC: {explanation}"
            ),
            FailureMode.NEGATIVE_IC: (
                f"avoid pattern '{formula_pattern}' in {island} island — "
                f"negative IC signal: {explanation}"
            ),
            FailureMode.HIGH_DRAWDOWN: (
                f"avoid pattern '{formula_pattern}' in {island} island — "
                f"high drawdown: {explanation}"
            ),
            FailureMode.OVERFITTING: (
                f"avoid pattern '{formula_pattern}' in {island} island — "
                f"overfitting suspected: {explanation}"
            ),
            FailureMode.LOW_COVERAGE: (
                f"avoid pattern '{formula_pattern}' in {island} island — "
                f"low coverage: {explanation}"
            ),
            FailureMode.EXECUTION_ERROR: (
                f"avoid pattern '{formula_pattern}' — "
                f"execution error: {explanation}"
            ),
            FailureMode.DUPLICATE: (
                f"avoid pattern '{formula_pattern}' in {island} island — "
                f"duplicate of existing factor"
            ),
        }
        return templates.get(
            failure_mode,
            f"avoid pattern '{formula_pattern}' in {island} island — {explanation}",
        )
