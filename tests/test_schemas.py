import pytest
from pydantic import ValidationError
from datetime import UTC, datetime

# 这里我们先导入虽然还不存在的模块，TDD 模式下这里会报错直到我们实现它们
from src.schemas.market_context import MarketContextMemo, NorthboundFlow, MacroSignal, HistoricalInsight
from src.schemas.research_note import FactorResearchNote, ExplorationQuestion, SynthesisInsight
from src.schemas.exploration import ExplorationRequest, ExplorationResult
from src.schemas.backtest import BacktestReport, BacktestMetrics, ExecutionMeta, FactorSpecSnapshot, ArtifactRefs
from src.schemas.judgment import CriticVerdict, ThresholdCheck, RiskAuditReport, CorrelationFlag, PortfolioAllocation, FactorWeight, CIOReport
from src.schemas.factor_pool import FactorPoolRecord
from src.schemas.factor_pool_record import FactorPoolRecord as LegacyFactorPoolRecord
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
