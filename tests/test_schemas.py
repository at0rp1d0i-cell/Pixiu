import json
import os
import re
import sys
import pytest
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pydantic import ValidationError

pytestmark = pytest.mark.unit

from src.schemas.hypothesis import (
    Hypothesis,
    StrategySpec,
    ExplorationSubspace,
    MutationOperator,
    RegimeCondition,
)
from src.schemas.thresholds import THRESHOLDS

# 这里我们先导入虽然还不存在的模块，TDD 模式下这里会报错直到我们实现它们
from src.schemas.market_context import MarketContextMemo, NorthboundFlow, MacroSignal, HistoricalInsight
from src.schemas.research_note import FactorResearchNote, ExplorationQuestion, SynthesisInsight
from src.schemas.exploration import ExplorationRequest, ExplorationResult
from src.schemas.backtest import BacktestReport, BacktestMetrics, ExecutionMeta, FactorSpecSnapshot, ArtifactRefs
from src.schemas.judgment import CriticVerdict, ThresholdCheck, RiskAuditReport, CorrelationFlag, PortfolioAllocation, FactorWeight, CIOReport
from src.schemas.factor_pool import FactorPoolRecord
LegacyFactorPoolRecord = FactorPoolRecord
from src.schemas.control_plane import RunRecord, RunSnapshot, ArtifactRecord, HumanDecisionRecord
from src.schemas.state import AgentState

def test_market_context_memo_creation():
    """测试 MarketContextMemo 实体的创建和验证"""
    flow = NorthboundFlow(
        net_buy_bn=15.5,
        top_sectors=["科技", "金融"],
        top_stocks=["600519.SH", "000858.SZ"],
        sentiment="bullish"
    )
    
    signal = MacroSignal(
        signal="CPI超预期下降",
        source="cpi",
        direction="positive",
        confidence=0.8
    )

    insight = HistoricalInsight(
        island="momentum",
        best_factor_formula="$close/Ref($close, 5)",
        best_sharpe=1.8,
        common_failure_modes=["高换手", "反转"],
        suggested_directions=["低波突破"]
    )
    
    memo = MarketContextMemo(
        date="2026-03-07",
        northbound=flow,
        macro_signals=[signal],
        hot_themes=["AI", "红利"],
        historical_insights=[insight],
        suggested_islands=["momentum"],
        market_regime="trending_up",
        raw_summary="市场整体向好..."
    )
    
    assert memo.date == "2026-03-07"
    assert memo.northbound.net_buy_bn == 15.5
    assert len(memo.macro_signals) == 1
    # 基类应该自动填充 created_at 和 version
    assert isinstance(memo.created_at, datetime)
    assert memo.version == "2.0"

def test_market_context_memo_forbid_extra():
    """测试 Config.extra = 'forbid' 是否生效"""
    with pytest.raises(ValidationError):
        MarketContextMemo(
            date="2026-03-07",
            northbound=None,
            macro_signals=[],
            hot_themes=[],
            historical_insights=[],
            suggested_islands=[],
            market_regime="volatile",
            raw_summary="",
            extra_field="this should fail"  # 不允许出现的额外字段
        )

def test_factor_research_note_defaults():
    """测试 FactorResearchNote 的默认值"""
    note = FactorResearchNote(
        note_id="momentum_20260307_001",
        island="momentum",
        iteration=1,
        hypothesis="测试假设",
        economic_intuition="测试直觉",
        proposed_formula="$close/$open",
        final_formula=None,
        exploration_questions=[],
        risk_factors=["未知风险"],
        market_context_date="2026-03-07"
    )
    
    assert note.universe == "csi300"
    assert note.holding_period == 1
    assert note.expected_ic_min == 0.02
    assert note.status == "draft"

def test_backtest_report_metrics():
    """测试 BacktestReport 及其嵌套 Metrics"""
    metrics = BacktestMetrics(
        sharpe=2.8,
        annualized_return=0.25,
        max_drawdown=0.1,
        ic_mean=0.035,
        ic_std=0.05,
        icir=0.7,
        turnover_rate=0.2,
        coverage=1.0,
    )
    
    report = BacktestReport(
        report_id="req-123",
        note_id="note-123",
        factor_id="factor-123",
        island="valuation",
        formula="$pe",
        metrics=metrics,
        passed=True,
        execution_time_seconds=120.5,
        qlib_output_raw="stdout...",
        error_message=None,
        execution_meta=ExecutionMeta(
            universe="csi300",
            benchmark="csi300",
            start_date="2021-01-01",
            end_date="2025-01-01",
            runtime_seconds=120.5,
            timestamp_utc=datetime.now(UTC),
        ),
        factor_spec=FactorSpecSnapshot(
            formula="$pe",
            hypothesis="估值回归",
            economic_rationale="低估值回归均值",
        ),
        artifacts=ArtifactRefs(),
    )
    
    assert report.passed is True
    assert report.metrics.sharpe == 2.8
    assert report.metrics.annualized_return == 0.25
    assert report.factor_spec is not None

def test_critic_verdict():
    """测试 Stage 5 Critic 的判定报告 Schema"""
    check = ThresholdCheck(
        metric="sharpe",
        value=1.5,
        threshold=2.67,
        passed=False
    )
    
    verdict = CriticVerdict(
        report_id="rep-123",
        factor_id="factor-123",
        note_id="note-123",
        overall_passed=False,
        decision="reject",
        score=0.25,
        checks=[check],
        passed_checks=[],
        failed_checks=["sharpe"],
        failure_mode="low_sharpe",
        failure_explanation="Sharpe 小于基线",
        suggested_fix="增加动量过滤",
        summary="Sharpe 未通过",
        reason_codes=["LOW_SHARPE"],
        register_to_pool=True,
        pool_tags=["failed:low_sharpe", "island:valuation"]
    )
    
    assert verdict.overall_passed is False
    assert verdict.decision == "reject"
    assert len(verdict.checks) == 1
    assert verdict.failure_mode == "low_sharpe"
    assert verdict.verdict_id


def test_factor_pool_record_schema():
    record = FactorPoolRecord(
        factor_id="factor-1",
        note_id="note-1",
        formula="$close",
        hypothesis="趋势延续",
        economic_rationale="资金流驱动。",
        backtest_report_id="report-1",
        verdict_id="verdict-1",
        decision="promote",
        score=0.91,
        sharpe=3.0,
        ic_mean=0.04,
        icir=0.6,
        turnover=0.18,
        max_drawdown=0.1,
        coverage=1.0,
        tags=["passed"],
    )

    assert record.factor_id == "factor-1"
    assert record.coverage == 1.0
    assert isinstance(record.created_at, datetime)


def test_legacy_factor_pool_record_import_points_to_canonical_schema():
    assert LegacyFactorPoolRecord is FactorPoolRecord

def test_agent_state_defaults():
    """测试 AgentState 初始化状态"""
    state = AgentState()
    assert state.current_round == 0
    assert state.current_island == "momentum"
    assert state.iteration == 0
    assert state.research_notes == []
    assert state.awaiting_human_approval is False


def test_control_plane_schemas():
    """测试控制平面基础 schema 可创建并具备关键字段。"""
    now = datetime.now(UTC)
    run = RunRecord(
        run_id="r1",
        mode="single",
        status="running",
        current_round=1,
        current_stage="coder",
        started_at=now,
    )
    snapshot = RunSnapshot(
        run_id="r1",
        approved_notes_count=1,
        backtest_reports_count=0,
        verdicts_count=0,
        awaiting_human_approval=False,
        updated_at=now,
    )
    artifact = ArtifactRecord(
        run_id="r1",
        kind="cio_report",
        ref_id="rep1",
        path="/tmp/report.md",
    )
    decision = HumanDecisionRecord(run_id="r1", action="approve")

    assert run.run_id == "r1"
    assert run.current_stage == "coder"
    assert isinstance(run.created_at, datetime)
    assert isinstance(run.started_at, datetime)
    assert run.finished_at is None
    assert snapshot.approved_notes_count == 1
    assert isinstance(snapshot.created_at, datetime)
    assert isinstance(snapshot.updated_at, datetime)
    assert artifact.kind == "cio_report"
    assert isinstance(artifact.created_at, datetime)
    assert decision.action == "approve"
    assert isinstance(decision.created_at, datetime)


def test_control_plane_forbid_extra_fields():
    """测试控制平面模型继承 forbid-extra 约束。"""
    with pytest.raises(ValidationError):
        RunRecord(
            run_id="r1",
            mode="single",
            status="running",
            started_at=datetime.now(UTC),
            extra_field="should-fail",
        )


# ─────────────────────────────────────────────────────────
# From test_hypothesis_schema.py
# ─────────────────────────────────────────────────────────

def test_hypothesis_minimal():
    """Hypothesis 最小必填字段"""
    h = Hypothesis(
        hypothesis_id="hyp_momentum_001",
        island="momentum",
        mechanism="价格动量延续效应",
        economic_rationale="市场参与者的追涨行为导致短期趋势延续",
    )
    assert h.hypothesis_id == "hyp_momentum_001"
    assert h.island == "momentum"
    assert h.mechanism == "价格动量延续效应"
    assert h.applicable_regimes == []
    assert h.invalid_regimes == []


def test_hypothesis_with_regimes():
    """Hypothesis 包含适用和失效 regime"""
    h = Hypothesis(
        hypothesis_id="hyp_vol_001",
        island="volatility",
        mechanism="波动率均值回归",
        economic_rationale="极端波动后市场趋于平静",
        applicable_regimes=["low_volatility", "stable_market"],
        invalid_regimes=["crisis", "high_volatility"],
    )
    assert "low_volatility" in h.applicable_regimes
    assert "crisis" in h.invalid_regimes


def test_hypothesis_with_inspirations():
    """Hypothesis 包含启发来源"""
    h = Hypothesis(
        hypothesis_id="hyp_nb_001",
        island="northbound",
        mechanism="北向资金流入预示上涨",
        economic_rationale="外资配置需求",
        inspirations=["AlphaAgent论文", "2024年北向资金研究"],
        failure_priors=["节假日前资金回流", "汇率波动期"],
    )
    assert len(h.inspirations) == 2
    assert len(h.failure_priors) == 2


def test_hypothesis_with_candidate_driver():
    """Hypothesis 包含潜在驱动因素"""
    h = Hypothesis(
        hypothesis_id="hyp_val_001",
        island="valuation",
        mechanism="低估值修复",
        economic_rationale="价值回归",
        candidate_driver="市场情绪改善",
    )
    assert h.candidate_driver == "市场情绪改善"


def test_strategy_spec_minimal():
    """StrategySpec 最小必填字段"""
    spec = StrategySpec(
        spec_id="spec_001",
        hypothesis_id="hyp_momentum_001",
        factor_expression="Ref($close, -5) / Ref($close, -20) - 1",
        universe="csi300",
        benchmark="SH000300",
        freq="day",
        required_fields=["$close"],
    )
    assert spec.spec_id == "spec_001"
    assert spec.hypothesis_id == "hyp_momentum_001"
    assert "$close" in spec.required_fields


def test_strategy_spec_with_holding_period():
    """StrategySpec 包含持仓周期"""
    spec = StrategySpec(
        spec_id="spec_002",
        hypothesis_id="hyp_vol_001",
        factor_expression="Std($close, 20)",
        universe="csi300",
        benchmark="SH000300",
        freq="day",
        holding_period=5,
        required_fields=["$close"],
    )
    assert spec.holding_period == 5


def test_strategy_spec_with_parameter_notes():
    """StrategySpec 包含参数说明"""
    spec = StrategySpec(
        spec_id="spec_003",
        hypothesis_id="hyp_momentum_001",
        factor_expression="Mean($close, N) / Mean($close, M) - 1",
        universe="csi300",
        benchmark="SH000300",
        freq="day",
        required_fields=["$close"],
        parameter_notes={
            "N": "短期窗口，建议5-10天",
            "M": "长期窗口，建议20-60天",
        },
    )
    assert "N" in spec.parameter_notes
    assert "M" in spec.parameter_notes


def test_strategy_spec_multiple_fields():
    """StrategySpec 需要多个数据字段"""
    spec = StrategySpec(
        spec_id="spec_004",
        hypothesis_id="hyp_volume_001",
        factor_expression="($volume / Mean($volume, 20) - 1) * ($close / Ref($close, -5) - 1)",
        universe="csi300",
        benchmark="SH000300",
        freq="day",
        required_fields=["$close", "$volume"],
    )
    assert len(spec.required_fields) == 2
    assert "$volume" in spec.required_fields


def test_exploration_subspace_enum():
    """ExplorationSubspace 枚举值"""
    assert ExplorationSubspace.FACTOR_ALGEBRA == "factor_algebra"
    assert ExplorationSubspace.SYMBOLIC_MUTATION == "symbolic_mutation"
    assert ExplorationSubspace.CROSS_MARKET == "cross_market"
    assert ExplorationSubspace.NARRATIVE_MINING == "narrative_mining"
    # REGIME_CONDITIONAL 已移除 — regime 现在是基础设施层


def test_mutation_operator_enum():
    """MutationOperator 枚举值"""
    assert MutationOperator.ADD_OPERATOR == "add_operator"
    assert MutationOperator.REMOVE_OPERATOR == "remove_operator"
    assert MutationOperator.SWAP_HORIZON == "swap_horizon"
    assert MutationOperator.CHANGE_NORMALIZATION == "change_normalization"
    assert MutationOperator.ALTER_INTERACTION == "alter_interaction"


def test_regime_condition_minimal():
    """RegimeCondition 最小字段"""
    regime = RegimeCondition(
        regime_name="bull_market",
        description="牛市环境",
    )
    assert regime.regime_name == "bull_market"
    assert regime.description == "牛市环境"
    assert regime.detection_rule is None


def test_regime_condition_with_detection():
    """RegimeCondition 包含检测规则"""
    regime = RegimeCondition(
        regime_name="high_volatility",
        description="高波动环境",
        detection_rule="Std($close, 20) > threshold",
    )
    assert regime.detection_rule == "Std($close, 20) > threshold"


def test_hypothesis_to_strategy_spec_linkage():
    """测试 Hypothesis 到 StrategySpec 的关联"""
    hyp = Hypothesis(
        hypothesis_id="hyp_test_001",
        island="momentum",
        mechanism="短期动量",
        economic_rationale="追涨效应",
    )

    spec = StrategySpec(
        spec_id="spec_test_001",
        hypothesis_id=hyp.hypothesis_id,
        factor_expression="Ref($close, -5) / Ref($close, -10) - 1",
        universe="csi300",
        benchmark="SH000300",
        freq="day",
        required_fields=["$close"],
    )

    assert spec.hypothesis_id == hyp.hypothesis_id


def test_one_hypothesis_multiple_specs():
    """一个 Hypothesis 可以对应多个 StrategySpec（不同参数化）"""
    hyp_id = "hyp_momentum_param_test"

    hyp = Hypothesis(
        hypothesis_id=hyp_id,
        island="momentum",
        mechanism="动量效应",
        economic_rationale="趋势延续",
    )

    spec1 = StrategySpec(
        spec_id="spec_short",
        hypothesis_id=hyp_id,
        factor_expression="Ref($close, -5) / Ref($close, -10) - 1",
        universe="csi300",
        benchmark="SH000300",
        freq="day",
        required_fields=["$close"],
        parameter_notes={"window": "短期5-10天"},
    )

    spec2 = StrategySpec(
        spec_id="spec_long",
        hypothesis_id=hyp_id,
        factor_expression="Ref($close, -20) / Ref($close, -60) - 1",
        universe="csi300",
        benchmark="SH000300",
        freq="day",
        required_fields=["$close"],
        parameter_notes={"window": "长期20-60天"},
    )

    assert spec1.hypothesis_id == spec2.hypothesis_id == hyp_id
    assert spec1.spec_id != spec2.spec_id


# ─────────────────────────────────────────────────────────
# From test_structured_output.py
# ─────────────────────────────────────────────────────────


@dataclass
class FactorHypothesisLegacy:
    name: str
    formula: str
    hypothesis: str
    rationale: str
    expected_direction: str = "unknown"
    market_observation: str = ""


@dataclass
class BacktestMetricsLegacy:
    sharpe: float = 0.0
    annualized_return: float = 0.0
    max_drawdown: float = 0.0
    ic: float = 0.0
    icir: float = 0.0
    turnover: float = 0.0
    win_rate: float = 0.0
    parse_success: bool = False
    raw_log_tail: str = ""


def _parse_metrics_legacy(log: str) -> BacktestMetricsLegacy:
    if not log:
        return BacktestMetricsLegacy(parse_success=False)

    for line in log.splitlines():
        if not line.startswith("BACKTEST_METRICS_JSON:"):
            continue
        try:
            payload = json.loads(line.replace("BACKTEST_METRICS_JSON:", "", 1).strip())
            return BacktestMetricsLegacy(
                sharpe=payload.get("sharpe", 0.0),
                annualized_return=payload.get("annualized_return", 0.0),
                max_drawdown=payload.get("max_drawdown", 0.0),
                ic=payload.get("ic", payload.get("ic_mean", 0.0)),
                icir=payload.get("icir", 0.0),
                turnover=payload.get("turnover", payload.get("turnover_rate", 0.0)),
                win_rate=payload.get("win_rate", 0.0),
                parse_success=True,
                raw_log_tail=log[-500:],
            )
        except json.JSONDecodeError:
            break

    patterns = {
        "sharpe": r"(?:夏普比率|Sharpe)\s*[：:]\s*(-?\d+(?:\.\d+)?)",
        "ic": r"(?:IC均值|IC)\s*[：:]\s*(-?\d+(?:\.\d+)?)",
        "icir": r"(?:ICIR)\s*[：:]\s*(-?\d+(?:\.\d+)?)",
        "turnover": r"(?:换手率|Turnover)\s*[：:]\s*(-?\d+(?:\.\d+)?)%?",
    }
    values: dict[str, float] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, log, flags=re.IGNORECASE)
        if match:
            values[key] = float(match.group(1))

    if "sharpe" not in values:
        return BacktestMetricsLegacy(parse_success=False, raw_log_tail=log[-500:])

    return BacktestMetricsLegacy(
        sharpe=values.get("sharpe", 0.0),
        ic=values.get("ic", 0.0),
        icir=values.get("icir", 0.0),
        turnover=values.get("turnover", 0.0),
        parse_success=True,
        raw_log_tail=log[-500:],
    )


def _evaluate_legacy(metrics: BacktestMetricsLegacy, has_error: bool) -> tuple[str, str]:
    if has_error:
        return "loop", "执行异常，需要重试"
    if not metrics.parse_success:
        return "loop", "指标解析失败，需要重试"
    if metrics.sharpe < THRESHOLDS.min_sharpe:
        return "loop", "Sharpe 未通过"
    if metrics.ic < THRESHOLDS.min_ic_mean:
        return "loop", "IC 未通过"
    if metrics.icir < THRESHOLDS.min_icir:
        return "loop", "ICIR 未通过"
    if metrics.turnover > 50.0:
        return "loop", "换手率过高"
    return "end", "通过所有关键阈值检查"


class TestFactorHypothesisLegacy:
    def test_valid_construction(self):
        h = FactorHypothesisLegacy(
            name="northbound_mom_5d",
            formula="Mean($volume, 5) / Ref(Mean($volume, 5), 5)",
            hypothesis="北向资金5日动量因子",
            rationale="外资趋势性行为在A股有预测力",
        )
        assert h.name == "northbound_mom_5d"
        assert h.expected_direction == "unknown"

    def test_missing_required_field(self):
        with pytest.raises(Exception):
            FactorHypothesisLegacy(name="test")  # 缺少 formula、hypothesis、rationale


class TestMetricsParsing:
    def test_parse_json_format(self):
        log = """
训练完成。
BACKTEST_METRICS_JSON: {"sharpe": 3.12, "ic": 0.045, "icir": 0.58, "turnover": 22.3, "annualized_return": 18.5, "max_drawdown": -12.1, "win_rate": 54.2}
策略运行完毕。
"""
        metrics = _parse_metrics_legacy(log)
        assert metrics.parse_success is True
        assert metrics.sharpe == pytest.approx(3.12)
        assert metrics.ic == pytest.approx(0.045)
        assert metrics.icir == pytest.approx(0.58)

    def test_parse_regex_fallback(self):
        log = "夏普比率：2.91\nIC均值：0.038\nICIR：0.52\n换手率：18.5%"
        metrics = _parse_metrics_legacy(log)
        assert metrics.parse_success is True
        assert metrics.sharpe == pytest.approx(2.91)

    def test_parse_empty_log(self):
        metrics = _parse_metrics_legacy("")
        assert metrics.parse_success is False
        assert metrics.sharpe == 0.0

    def test_parse_no_sharpe(self):
        metrics = _parse_metrics_legacy("策略运行完毕，无有效输出。")
        assert metrics.parse_success is False


class TestEvaluation:
    def test_all_pass(self):
        m = BacktestMetricsLegacy(sharpe=3.1, ic=0.05, icir=0.6, turnover=20.0, parse_success=True)
        route, reason = _evaluate_legacy(m, False)
        assert route == "end"
        assert "通过" in reason

    def test_sharpe_too_low(self):
        m = BacktestMetricsLegacy(sharpe=0.2, ic=0.05, icir=0.6, turnover=20.0, parse_success=True)
        route, _ = _evaluate_legacy(m, False)
        assert route == "loop"

    def test_high_turnover(self):
        m = BacktestMetricsLegacy(sharpe=3.5, ic=0.05, icir=0.6, turnover=80.0, parse_success=True)
        route, reason = _evaluate_legacy(m, False)
        assert route == "loop"
        assert "换手率" in reason

    def test_low_ic(self):
        m = BacktestMetricsLegacy(sharpe=3.5, ic=0.001, icir=0.6, turnover=20.0, parse_success=True)
        route, reason = _evaluate_legacy(m, False)
        assert route == "loop"
        assert "IC" in reason

    def test_error_always_loops(self):
        m = BacktestMetricsLegacy(sharpe=99.0, parse_success=True)
        route, _ = _evaluate_legacy(m, has_error=True)
        assert route == "loop"

    def test_parse_failure_loops(self):
        m = BacktestMetricsLegacy(parse_success=False)
        route, _ = _evaluate_legacy(m, False)
        assert route == "loop"
