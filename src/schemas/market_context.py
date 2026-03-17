from typing import Optional, List
from enum import Enum
from pydantic import field_validator
from src.schemas import PixiuBase


class MarketRegime(str, Enum):
    BULL_TREND = "bull_trend"
    BEAR_TREND = "bear_trend"
    HIGH_VOLATILITY = "high_volatility"
    RANGE_BOUND = "range_bound"
    STRUCTURAL_BREAK = "structural_break"


class NorthboundFlow(PixiuBase):
    net_buy_bn: float           # 净买入（亿元）
    top_sectors: List[str]      # 资金流入最多的板块（最多5个）
    top_stocks: List[str]       # 资金流入最多的个股（最多10个）
    sentiment: str              # "bullish" | "neutral" | "bearish"

class MacroSignal(PixiuBase):
    signal: str                 # 信号描述
    source: str                 # 来源（"fed" | "cpi" | "pmi" | "news"）
    direction: str              # "positive" | "negative" | "neutral"
    confidence: float           # 0.0 - 1.0

class HistoricalInsight(PixiuBase):
    """LiteratureMiner 从 FactorPool 检索到的相关历史"""
    island: str
    best_factor_formula: str
    best_sharpe: float
    common_failure_modes: List[str]
    suggested_directions: List[str]

class MarketContextMemo(PixiuBase):
    date: str                                    # "2026-03-07"
    northbound: Optional[NorthboundFlow]
    macro_signals: List[MacroSignal]
    hot_themes: List[str]                        # 当日热点主题
    historical_insights: List[HistoricalInsight] # 每个 Island 一条
    suggested_islands: List[str]                 # 建议本轮重点探索的 Island
    market_regime: MarketRegime = MarketRegime.RANGE_BOUND  # enum, default conservative

    # 技术面指标（供 RegimeDetector 使用，LLM 在数据可用时填充）
    index_ma5: Optional[float] = None       # 上证指数 MA5
    index_ma20: Optional[float] = None      # 上证指数 MA20
    index_ma60: Optional[float] = None      # 上证指数 MA60
    volatility_30d: Optional[float] = None  # 近 30 日日均波动率（%）
    return_30d: Optional[float] = None      # 近 30 日累计涨跌幅（%）

    @field_validator("market_regime", mode="before")
    @classmethod
    def coerce_market_regime(cls, v):
        """Coerce unknown/legacy string values to RANGE_BOUND for backward compatibility."""
        if isinstance(v, MarketRegime):
            return v
        if isinstance(v, str):
            # Legacy value mapping (pre-enum naming convention)
            _LEGACY_MAP = {
                "trending_up": MarketRegime.BULL_TREND,
                "trending_down": MarketRegime.BEAR_TREND,
                "sideways": MarketRegime.RANGE_BOUND,
                "volatile": MarketRegime.HIGH_VOLATILITY,
                "unknown": MarketRegime.RANGE_BOUND,
            }
            if v in _LEGACY_MAP:
                return _LEGACY_MAP[v]
            # Try direct enum lookup
            try:
                return MarketRegime(v)
            except ValueError:
                return MarketRegime.RANGE_BOUND
        return v
    raw_summary: str                             # 给 Researcher 读的自然语言摘要（500字以内）
