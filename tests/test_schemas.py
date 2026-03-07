import pytest
from pydantic import ValidationError
from datetime import datetime

# 这里我们先导入虽然还不存在的模块，TDD 模式下这里会报错直到我们实现它们
from src.schemas.market_context import MarketContextMemo, NorthboundFlow, MacroSignal, HistoricalInsight
from src.schemas.research_note import FactorResearchNote, ExplorationQuestion, SynthesisInsight
from src.schemas.exploration import ExplorationRequest, ExplorationResult
from src.schemas.backtest import BacktestReport, BacktestMetrics
from src.schemas.judgment import CriticVerdict, ThresholdCheck, RiskAuditReport, CorrelationFlag, PortfolioAllocation, FactorWeight, CIOReport
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
        turnover_rate=0.2
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
        error_message=None
    )
    
    assert report.passed is True
    assert report.metrics.sharpe == 2.8

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
        overall_passed=False,
        checks=[check],
        failure_mode="low_sharpe",
        failure_explanation="Sharpe 小于基线",
        suggested_fix="增加动量过滤",
        register_to_pool=True,
        pool_tags=["failed:low_sharpe", "island:valuation"]
    )
    
    assert verdict.overall_passed is False
    assert len(verdict.checks) == 1
    assert verdict.failure_mode == "low_sharpe"

def test_agent_state_defaults():
    """测试 AgentState 初始化状态"""
    state = AgentState()
    assert state.current_round == 0
    assert state.current_island == "momentum"
    assert state.iteration == 0
    assert state.research_notes == []
    assert state.awaiting_human_approval is False
