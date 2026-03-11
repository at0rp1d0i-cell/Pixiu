"""
Stage 5: Critic - 确定性判定逻辑
按照 v2_stage45_golden_path.md 规格实现
"""
import uuid
import logging
from typing import List, Tuple, Optional
from src.schemas.backtest import BacktestReport
from src.schemas.judgment import CriticVerdict
from src.schemas.thresholds import THRESHOLDS

logger = logging.getLogger(__name__)

# 原因码枚举
REASON_LOW_SHARPE = "LOW_SHARPE"
REASON_LOW_IC = "LOW_IC"
REASON_LOW_ICIR = "LOW_ICIR"
REASON_HIGH_TURNOVER = "HIGH_TURNOVER"
REASON_HIGH_DRAWDOWN = "HIGH_DRAWDOWN"
REASON_LOW_COVERAGE = "LOW_COVERAGE"
REASON_EXECUTION_FAILED = "EXECUTION_FAILED"
REASON_PARSE_INCOMPLETE = "PARSE_INCOMPLETE"
REASON_JUDGE_INCOMPLETE = "JUDGE_INCOMPLETE"

class Critic:
    """
    确定性判定器（v2 Golden Path）

    职责：
    1. 接收 BacktestReport
    2. 执行固定顺序的检查（完整性 → 硬阈值 → 评分）
    3. 返回确定性的 CriticVerdict

    不调用任何 LLM，不做自由文本推理。
    """

    def __init__(self, thresholds=None):
        self.thresholds = thresholds or THRESHOLDS

    def evaluate(self, report: BacktestReport) -> CriticVerdict:
        """
        确定性判定的唯一入口

        判定顺序（固定）：
        1. 完整性检查
        2. 硬阈值检查
        3. 加权评分
        """
        verdict_id = str(uuid.uuid4())

        # Step 1: 完整性检查
        completeness_ok, reason_codes = self._check_completeness(report)
        if not completeness_ok:
            return CriticVerdict(
                verdict_id=verdict_id,
                report_id=report.report_id,
                note_id=report.note_id,
                decision="retry",
                score=0.0,
                passed_checks=[],
                failed_checks=["completeness"],
                summary="报告不完整，需要重试",
                reason_codes=reason_codes,
            )

        # Step 2: 硬阈值检查
        passed_checks, failed_checks, reason_codes = self._check_thresholds(report)

        # Step 3: 加权评分
        score = self._calculate_score(report)

        # Step 4: 决策
        decision = self._make_decision(passed_checks, failed_checks, score)

        # Step 5: 生成摘要
        summary = self._generate_summary(decision, passed_checks, failed_checks, score)

        return CriticVerdict(
            verdict_id=verdict_id,
            report_id=report.report_id,
            note_id=report.note_id,
            decision=decision,
            score=score,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            summary=summary,
            reason_codes=reason_codes,
        )

    def _check_completeness(self, report: BacktestReport) -> Tuple[bool, List[str]]:
        """Step 1: 完整性检查"""
        reason_codes = []

        # 检查执行状态
        if report.status == "failed":
            if report.failure_stage == "compile":
                reason_codes.append(REASON_EXECUTION_FAILED)
            elif report.failure_stage == "run":
                reason_codes.append(REASON_EXECUTION_FAILED)
            elif report.failure_stage == "parse":
                reason_codes.append(REASON_PARSE_INCOMPLETE)
            elif report.failure_stage == "judge":
                reason_codes.append(REASON_JUDGE_INCOMPLETE)
            else:
                reason_codes.append(REASON_EXECUTION_FAILED)
            return False, reason_codes

        # 检查必要指标是否存在
        metrics = report.metrics
        if metrics.sharpe is None or metrics.ic_mean is None or metrics.icir is None:
            reason_codes.append(REASON_PARSE_INCOMPLETE)
            return False, reason_codes

        return True, []

    def _check_thresholds(self, report: BacktestReport) -> Tuple[List[str], List[str], List[str]]:
        """Step 2: 硬阈值检查"""
        passed_checks = []
        failed_checks = []
        reason_codes = []

        metrics = report.metrics

        # Sharpe 检查
        if metrics.sharpe is not None:
            if metrics.sharpe >= self.thresholds.min_sharpe:
                passed_checks.append("sharpe")
            else:
                failed_checks.append("sharpe")
                reason_codes.append(REASON_LOW_SHARPE)

        # IC 检查
        if metrics.ic_mean is not None:
            if metrics.ic_mean >= self.thresholds.min_ic_mean:
                passed_checks.append("ic_mean")
            else:
                failed_checks.append("ic_mean")
                reason_codes.append(REASON_LOW_IC)

        # ICIR 检查
        if metrics.icir is not None:
            if metrics.icir >= self.thresholds.min_icir:
                passed_checks.append("icir")
            else:
                failed_checks.append("icir")
                reason_codes.append(REASON_LOW_ICIR)

        # 换手率检查
        if metrics.turnover is not None:
            if metrics.turnover <= self.thresholds.max_turnover:
                passed_checks.append("turnover")
            else:
                failed_checks.append("turnover")
                reason_codes.append(REASON_HIGH_TURNOVER)

        # 最大回撤检查
        if metrics.max_drawdown is not None:
            if abs(metrics.max_drawdown) <= self.thresholds.max_drawdown:
                passed_checks.append("max_drawdown")
            else:
                failed_checks.append("max_drawdown")
                reason_codes.append(REASON_HIGH_DRAWDOWN)

        # 覆盖率检查（如果有）
        if metrics.coverage is not None:
            if metrics.coverage >= self.thresholds.min_coverage:
                passed_checks.append("coverage")
            else:
                failed_checks.append("coverage")
                reason_codes.append(REASON_LOW_COVERAGE)

        return passed_checks, failed_checks, reason_codes

    def _calculate_score(self, report: BacktestReport) -> float:
        """Step 3: 加权评分（确定性）"""
        metrics = report.metrics

        # 归一化各指标到 [0, 1]
        sharpe_score = min(1.0, max(0.0, (metrics.sharpe or 0) / 3.0))  # 假设 3.0 为优秀
        ic_score = min(1.0, max(0.0, (metrics.ic_mean or 0) / 0.05))    # 假设 0.05 为优秀
        icir_score = min(1.0, max(0.0, (metrics.icir or 0) / 1.0))      # 假设 1.0 为优秀

        # 换手率和回撤是负向指标
        turnover_score = 1.0 - min(1.0, (metrics.turnover or 0) / self.thresholds.max_turnover)
        drawdown_score = 1.0 - min(1.0, abs(metrics.max_drawdown or 0) / self.thresholds.max_drawdown)

        # 加权平均（权重可调整）
        weights = {
            "sharpe": 0.3,
            "ic": 0.25,
            "icir": 0.2,
            "turnover": 0.15,
            "drawdown": 0.1,
        }

        score = (
            weights["sharpe"] * sharpe_score +
            weights["ic"] * ic_score +
            weights["icir"] * icir_score +
            weights["turnover"] * turnover_score +
            weights["drawdown"] * drawdown_score
        )

        return round(score, 3)

    def _make_decision(
        self,
        passed_checks: List[str],
        failed_checks: List[str],
        score: float,
    ) -> str:
        """Step 4: 决策（确定性状态机）"""

        # 所有硬阈值通过 → promote
        if len(failed_checks) == 0:
            return "promote"

        # 有失败但分数还可以 → archive（留档）
        if score >= 0.5:
            return "archive"

        # 分数太低 → reject
        return "reject"

    def _generate_summary(
        self,
        decision: str,
        passed_checks: List[str],
        failed_checks: List[str],
        score: float,
    ) -> str:
        """Step 5: 生成摘要（确定性模板）"""

        if decision == "promote":
            return f"因子通过所有检查，综合得分 {score:.2f}，推荐进入候选池"
        elif decision == "archive":
            return f"因子部分指标未达标（{', '.join(failed_checks)}），但综合得分 {score:.2f}，留档备用"
        elif decision == "reject":
            return f"因子质量不达标（{', '.join(failed_checks)}），综合得分 {score:.2f}，不推荐使用"
        else:  # retry
            return "执行或解析异常，建议重试"
