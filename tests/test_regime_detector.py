"""
Regime Detection 模块单元测试（Phase 2 子任务 2.5）

测试覆盖：
  - RegimeDetector.detect() — 基于预计算统计量的五种 regime 路径
  - RegimeDetector.detect_from_signals() — 基于原始价格序列的检测路径
  - 边界条件与降级行为
  - prefilter.RegimeFilter — invalid_regimes 过滤逻辑

标记：smoke（快速冒烟）和 unit（单元）
"""
import math
import pytest

from src.schemas.market_context import MarketRegime
from src.market.regime_detector import RegimeDetector, RegimeSignals


# ─────────────────────────────────────────────────────────
# 辅助工厂
# ─────────────────────────────────────────────────────────

def _make_detector() -> RegimeDetector:
    return RegimeDetector()


def _make_rising_closes(n: int = 60, start: float = 3000.0, slope: float = 10.0) -> list[float]:
    """生成单调上涨的价格序列，最终涨幅 = slope * n / start。"""
    return [start + i * slope for i in range(n)]


def _make_falling_closes(n: int = 60, start: float = 3600.0, slope: float = 10.0) -> list[float]:
    """生成单调下跌的价格序列。"""
    return [start - i * slope for i in range(n)]


def _make_flat_closes(n: int = 60, base: float = 3000.0, noise: float = 5.0) -> list[float]:
    """生成低波动横盘序列（微小正弦扰动）。"""
    import math
    return [base + noise * math.sin(i) for i in range(n)]


def _make_volatile_closes(n: int = 60, base: float = 3000.0, amplitude: float = 200.0) -> list[float]:
    """生成高波动价格序列（大幅震荡，日均波动率约 3.3%，超过 HIGH_VOL 阈值 2.5%）。"""
    import math
    return [base + amplitude * math.sin(i * 0.7) for i in range(n)]


# ─────────────────────────────────────────────────────────
# 1. detect(market_data: dict) — 预计算路径
# ─────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_detect_structural_break_by_volatility():
    """波动率超过 3% 应触发 STRUCTURAL_BREAK。"""
    d = _make_detector()
    result = d.detect({"volatility_30d": 3.5})
    assert result == MarketRegime.STRUCTURAL_BREAK


@pytest.mark.unit
def test_detect_structural_break_by_max_daily_return():
    """单日涨跌幅超过 5% 应触发 STRUCTURAL_BREAK（即使波动率不够高）。"""
    d = _make_detector()
    result = d.detect({"volatility_30d": 1.0, "max_daily_return": 6.0})
    assert result == MarketRegime.STRUCTURAL_BREAK


@pytest.mark.unit
def test_detect_structural_break_max_daily_negative():
    """max_daily_return 负值（大跌）也应触发 STRUCTURAL_BREAK。"""
    d = _make_detector()
    result = d.detect({"volatility_30d": 1.0, "max_daily_return": -7.5})
    assert result == MarketRegime.STRUCTURAL_BREAK


@pytest.mark.smoke
def test_detect_high_volatility():
    """波动率在 1.5%-3% 之间应触发 HIGH_VOLATILITY。"""
    d = _make_detector()
    result = d.detect({"volatility_30d": 2.0})
    assert result == MarketRegime.HIGH_VOLATILITY


@pytest.mark.smoke
def test_detect_bull_trend():
    """均线多头排列且 30 日涨幅 > 10% 应触发 BULL_TREND。"""
    d = _make_detector()
    result = d.detect({
        "volatility_30d": 0.8,
        "ma5": 4200.0,
        "ma20": 4100.0,
        "ma60": 3900.0,
        "market_return_30d": 15.0,
    })
    assert result == MarketRegime.BULL_TREND


@pytest.mark.smoke
def test_detect_bear_trend():
    """均线空头排列且 30 日跌幅 > 10% 应触发 BEAR_TREND。"""
    d = _make_detector()
    result = d.detect({
        "volatility_30d": 0.8,
        "ma5": 3500.0,
        "ma20": 3700.0,
        "ma60": 3900.0,
        "market_return_30d": -12.0,
    })
    assert result == MarketRegime.BEAR_TREND


@pytest.mark.smoke
def test_detect_range_bound_default():
    """低波动 + 均线混乱排列 + 小幅涨跌 → RANGE_BOUND（默认）。"""
    d = _make_detector()
    result = d.detect({
        "volatility_30d": 0.9,
        "ma5": 3800.0,
        "ma20": 3820.0,
        "ma60": 3810.0,
        "market_return_30d": 3.0,
    })
    assert result == MarketRegime.RANGE_BOUND


@pytest.mark.unit
def test_detect_range_bound_no_data():
    """无任何数据时应返回 RANGE_BOUND（保守默认）。"""
    d = _make_detector()
    result = d.detect({})
    assert result == MarketRegime.RANGE_BOUND


@pytest.mark.unit
def test_detect_bull_trend_requires_alignment():
    """均线排列正确但涨幅不足 → 不触发 BULL_TREND，应降级为 RANGE_BOUND。"""
    d = _make_detector()
    result = d.detect({
        "volatility_30d": 0.8,
        "ma5": 4200.0,
        "ma20": 4100.0,
        "ma60": 3900.0,
        "market_return_30d": 5.0,  # 不足 10%
    })
    assert result == MarketRegime.RANGE_BOUND


@pytest.mark.unit
def test_detect_bear_trend_requires_alignment():
    """均线空头排列但跌幅不足 → 不触发 BEAR_TREND，应降级为 RANGE_BOUND。"""
    d = _make_detector()
    result = d.detect({
        "volatility_30d": 0.8,
        "ma5": 3500.0,
        "ma20": 3700.0,
        "ma60": 3900.0,
        "market_return_30d": -5.0,  # 不足 -10%
    })
    assert result == MarketRegime.RANGE_BOUND


@pytest.mark.unit
def test_detect_volatility_exact_structural_break_boundary():
    """波动率恰好等于阈值 3.0 时不触发 STRUCTURAL_BREAK（> 不含等号）。"""
    d = _make_detector()
    result = d.detect({"volatility_30d": 3.0})
    # 3.0 不 > 3.0，应降级到 HIGH_VOLATILITY
    assert result == MarketRegime.HIGH_VOLATILITY


@pytest.mark.unit
def test_detect_volatility_exact_high_vol_boundary():
    """波动率恰好等于阈值 1.5 时不触发 HIGH_VOLATILITY（> 不含等号）。"""
    d = _make_detector()
    result = d.detect({"volatility_30d": 1.5})
    # 1.5 不 > 1.5，应降级到 RANGE_BOUND（无均线数据）
    assert result == MarketRegime.RANGE_BOUND


@pytest.mark.unit
def test_detect_partial_data_missing_ma():
    """只有波动率而无均线数据时，BULL/BEAR 规则跳过，应走波动率路径。"""
    d = _make_detector()
    # 有波动率但无均线 — 低波动时应返回 RANGE_BOUND
    result = d.detect({"volatility_30d": 0.5, "market_return_30d": 20.0})
    assert result == MarketRegime.RANGE_BOUND


# ─────────────────────────────────────────────────────────
# 2. detect_from_signals() — 原始价格序列路径
# ─────────────────────────────────────────────────────────

@pytest.mark.unit
def test_detect_from_signals_bull_trend():
    """稳步上涨的价格序列应检测为 BULL_TREND。"""
    d = _make_detector()
    # 涨幅 = 59 * 10 / 3000 ≈ 19.7%，大于 TREND_MIN_RETURN=8%
    closes = _make_rising_closes(n=60, start=3000.0, slope=10.0)
    signals = RegimeSignals(index_close=closes)
    result = d.detect_from_signals(signals)
    assert result == MarketRegime.BULL_TREND


@pytest.mark.unit
def test_detect_from_signals_bear_trend():
    """稳步下跌的价格序列应检测为 BEAR_TREND。"""
    d = _make_detector()
    # 跌幅 = 59 * 10 / 3600 ≈ 16.4%，大于 TREND_MIN_RETURN=8%
    closes = _make_falling_closes(n=60, start=3600.0, slope=10.0)
    signals = RegimeSignals(index_close=closes)
    result = d.detect_from_signals(signals)
    assert result == MarketRegime.BEAR_TREND


@pytest.mark.unit
def test_detect_from_signals_range_bound():
    """低波动横盘序列应检测为 RANGE_BOUND。"""
    d = _make_detector()
    closes = _make_flat_closes(n=60, base=3000.0, noise=5.0)
    signals = RegimeSignals(index_close=closes)
    result = d.detect_from_signals(signals)
    assert result == MarketRegime.RANGE_BOUND


@pytest.mark.unit
def test_detect_from_signals_high_volatility():
    """高波动价格序列应检测为 HIGH_VOLATILITY 或 STRUCTURAL_BREAK。"""
    d = _make_detector()
    closes = _make_volatile_closes(n=60, base=3000.0, amplitude=200.0)
    signals = RegimeSignals(index_close=closes)
    result = d.detect_from_signals(signals)
    assert result in (MarketRegime.HIGH_VOLATILITY, MarketRegime.STRUCTURAL_BREAK)


@pytest.mark.unit
def test_detect_from_signals_structural_break():
    """近5日剧烈波动（远超前55日）应触发 STRUCTURAL_BREAK。"""
    d = _make_detector()
    # 前55日平稳，后5日剧烈震荡
    stable = _make_flat_closes(n=55, base=3000.0, noise=3.0)
    # 后5日：大幅震荡，日均波动远超前55日
    volatile_tail = [3000.0, 3200.0, 2800.0, 3300.0, 2700.0]
    closes = stable + volatile_tail
    signals = RegimeSignals(index_close=closes)
    result = d.detect_from_signals(signals)
    assert result == MarketRegime.STRUCTURAL_BREAK


@pytest.mark.unit
def test_detect_from_signals_insufficient_data():
    """数据不足（< 5 个）时应降级为 RANGE_BOUND。"""
    d = _make_detector()
    signals = RegimeSignals(index_close=[3000.0, 3010.0, 3020.0])
    result = d.detect_from_signals(signals)
    assert result == MarketRegime.RANGE_BOUND


# ─────────────────────────────────────────────────────────
# 3. RegimeFilter — prefilter Filter E
# ─────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_regime_filter_rejects_invalid_regime():
    """invalid_regimes 包含当前 regime 时应拒绝。"""
    from src.agents.prefilter import RegimeFilter
    from src.schemas.research_note import FactorResearchNote

    note = FactorResearchNote(
        note_id="test_regime_filter",
        island="momentum",
        iteration=1,
        hypothesis="动量假设",
        economic_intuition="趋势延续",
        proposed_formula="Mean($close, 5) / Mean($close, 20) - 1",
        risk_factors=["市场反转"],
        market_context_date="2026-03-17",
        invalid_regimes=["bull_trend", "high_volatility"],
    )

    rf = RegimeFilter()
    passed, reason = rf.check(note, current_regime="bull_trend")
    assert not passed
    assert "bull_trend" in reason


@pytest.mark.smoke
def test_regime_filter_passes_when_not_in_invalid():
    """invalid_regimes 不包含当前 regime 时应通过。"""
    from src.agents.prefilter import RegimeFilter
    from src.schemas.research_note import FactorResearchNote

    note = FactorResearchNote(
        note_id="test_regime_pass",
        island="momentum",
        iteration=1,
        hypothesis="动量假设",
        economic_intuition="趋势延续",
        proposed_formula="Mean($close, 5) / Mean($close, 20) - 1",
        risk_factors=["市场反转"],
        market_context_date="2026-03-17",
        invalid_regimes=["bear_trend"],
    )

    rf = RegimeFilter()
    passed, reason = rf.check(note, current_regime="bull_trend")
    assert passed


@pytest.mark.unit
def test_regime_filter_passes_when_no_regime():
    """current_regime 为 None 时直接放行（无上下文）。"""
    from src.agents.prefilter import RegimeFilter
    from src.schemas.research_note import FactorResearchNote

    note = FactorResearchNote(
        note_id="test_no_regime",
        island="momentum",
        iteration=1,
        hypothesis="动量假设",
        economic_intuition="趋势延续",
        proposed_formula="Mean($close, 5) / Mean($close, 20) - 1",
        risk_factors=["市场反转"],
        market_context_date="2026-03-17",
        invalid_regimes=["bull_trend"],
    )

    rf = RegimeFilter()
    passed, reason = rf.check(note, current_regime=None)
    assert passed


@pytest.mark.unit
def test_regime_filter_passes_empty_invalid_regimes():
    """invalid_regimes 为空时应通过（因子未声明 regime 约束）。"""
    from src.agents.prefilter import RegimeFilter
    from src.schemas.research_note import FactorResearchNote

    note = FactorResearchNote(
        note_id="test_empty_invalid",
        island="momentum",
        iteration=1,
        hypothesis="动量假设",
        economic_intuition="趋势延续",
        proposed_formula="Mean($close, 5) / Mean($close, 20) - 1",
        risk_factors=["市场反转"],
        market_context_date="2026-03-17",
        invalid_regimes=[],
    )

    rf = RegimeFilter()
    passed, reason = rf.check(note, current_regime="bull_trend")
    assert passed


# ─────────────────────────────────────────────────────────
# 4. PreFilter 集成：filter_batch 带 current_regime 参数
# ─────────────────────────────────────────────────────────

@pytest.mark.unit
def test_prefilter_filter_batch_regime_param():
    """filter_batch 接受 current_regime 参数，invalid_regimes 匹配时过滤掉该 note。"""
    import asyncio
    from unittest.mock import MagicMock, AsyncMock, patch
    from src.agents.prefilter import PreFilter
    from src.schemas.research_note import FactorResearchNote

    mock_pool = MagicMock()
    mock_pool.get_island_factors.return_value = []
    mock_pool.query_constraints.return_value = []

    # 两条 note：一条 invalid_regimes=["bull_trend"]，一条无约束
    note_rejected = FactorResearchNote(
        note_id="rejected_note",
        island="momentum",
        iteration=1,
        hypothesis="动量假设",
        economic_intuition="趋势延续",
        proposed_formula="Mean($close, 5) / Mean($close, 20) - 1",
        risk_factors=["反转"],
        market_context_date="2026-03-17",
        invalid_regimes=["bull_trend"],
    )
    note_passed = FactorResearchNote(
        note_id="passed_note",
        island="momentum",
        iteration=1,
        hypothesis="动量假设2",
        economic_intuition="趋势延续2",
        proposed_formula="Corr($volume, $close, 20)",
        risk_factors=["流动性"],
        market_context_date="2026-03-17",
        invalid_regimes=[],
    )

    mock_response = MagicMock()
    mock_response.content = '{"aligned": true, "reason": "一致"}'

    with patch("src.agents.prefilter.ChatOpenAI") as MockLLM:
        mock_chat = MockLLM.return_value
        mock_chat.ainvoke = AsyncMock(return_value=mock_response)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test", "RESEARCHER_API_KEY": "test"}):
            pf = PreFilter(factor_pool=mock_pool)
            approved, filtered = asyncio.run(
                pf.filter_batch([note_rejected, note_passed], current_regime="bull_trend")
            )

    approved_ids = {n.note_id for n in approved}
    assert "rejected_note" not in approved_ids
    assert "passed_note" in approved_ids
