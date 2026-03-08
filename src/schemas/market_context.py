from typing import Optional, List
from src.schemas import PixiuBase

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
    market_regime: str                           # "trending_up" | "trending_down" | "sideways" | "volatile"
    raw_summary: str                             # 给 Researcher 读的自然语言摘要（500字以内）
