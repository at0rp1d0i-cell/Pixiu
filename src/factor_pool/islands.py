"""
Pixiu: Island 定义
每个 Island 代表一个因子研究方向（家族）。
Island 概念来自 FunSearch 进化算法，用于防止搜索陷入局部最优。
"""

# Island 名称 → 描述（用于 Researcher 的 System Prompt 上下文注入）
ISLANDS: dict[str, dict] = {
    "momentum": {
        "name": "动量族",
        "description": "基于价格/成交量的动量与反转因子。如近N日收益率、量价相关性、强弱指标。",
        "seed_keywords": ["momentum", "return", "roc", "rsi", "macd"],
    },
    "northbound": {
        "name": "北向资金族",
        "description": "基于沪深港通北向资金流向的因子。北向资金代表外资机构行为，具有趋势性。",
        "seed_keywords": ["northbound", "hsgt", "foreign", "fund_flow"],
    },
    "valuation": {
        "name": "估值族",
        "description": "基于估值指标的因子。如PE分位、PB分位、行业估值相对强弱。",
        "seed_keywords": ["pe", "pb", "valuation", "ratio", "percentile"],
    },
    "volatility": {
        "name": "波动率族",
        "description": "基于价格波动特征的因子。如历史波动率、ATR、波动率偏度。",
        "seed_keywords": ["volatility", "std", "atr", "vix", "vol"],
    },
    "volume": {
        "name": "量价族",
        "description": "量价关系类因子。大单净流入、量价背离、成交量异动。",
        "seed_keywords": ["volume", "turnover", "amount", "big_order"],
    },
    "sentiment": {
        "name": "情绪族",
        "description": "基于市场情绪的因子。研报评级、分析师预期修正、新闻情绪分。",
        "seed_keywords": ["sentiment", "analyst", "rating", "news"],
    },
}

# 默认启动时激活的 Island（按优先级排列）
DEFAULT_ACTIVE_ISLANDS = ["momentum", "northbound", "valuation", "volatility"]
