"""
Pixiu v2 — Regime Detection 独立模块（Stage 2.5 实现规格）

将 market_regime 从 LLM 自由填写，变成规则引擎的确定性输出。

设计文档：docs/design/stage-2-hypothesis-expansion.md §11

两种入口：
  - detect(market_data: dict) — 简化接口，接受预计算统计量
  - detect_from_signals(signals: RegimeSignals) — 从原始价格序列检测

优先级（高 → 低）：
  STRUCTURAL_BREAK > HIGH_VOLATILITY > BULL_TREND > BEAR_TREND > RANGE_BOUND
"""
import statistics
from typing import List, Optional

from src.schemas import PixiuBase
from src.schemas.market_context import MarketRegime


class RegimeSignals(PixiuBase):
    """用于 regime 检测的市场原始信号（价格序列）。

    适用于拥有完整价格序列时的检测路径。
    """

    index_close: List[float]    # 最近 N 日收盘价（沪深300 或全A）
    volume: List[float] = []    # 最近 N 日成交量（可选）
    date_range: int = 60        # 使用的历史窗口（交易日）


class RegimeDetector:
    """基于规则的 Regime 检测器。

    两种使用方式：

    1. 从预计算统计量（适用于 LLM 已提取数据的场景）：
       detector = RegimeDetector()
       regime = detector.detect({
           "volatility_30d": 1.2,      # 日均波动率（%）
           "ma5": 4100.0,
           "ma20": 4050.0,
           "ma60": 3980.0,
           "market_return_30d": 12.5,  # 30日累积涨跌幅（%）
       })

    2. 从原始价格序列：
       signals = RegimeSignals(index_close=[...60个收盘价...])
       regime = detector.detect_from_signals(signals)

    规则优先级（按序评估，先满足先返回）：
      1. STRUCTURAL_BREAK：30日波动率 > 3%（日均）或单日涨跌 > 5%
      2. HIGH_VOLATILITY：30日波动率 > 1.5%（日均）
      3. BULL_TREND：MA5 > MA20 > MA60 且 market_return_30d > 10%
      4. BEAR_TREND：MA5 < MA20 < MA60 且 market_return_30d < -10%
      5. RANGE_BOUND：默认（其他所有情况）
    """

    # ── 阈值常量（可通过子类覆盖或环境变量扩展） ──────────────────────────

    # detect(market_data: dict) 路径阈值（日均波动率 %）
    STRUCTURAL_BREAK_VOL_THRESHOLD: float = 3.0    # 日均波动率 > 3% → 结构性突破
    HIGH_VOL_THRESHOLD: float = 1.5                # 日均波动率 > 1.5% → 高波动
    STRUCTURAL_BREAK_DAILY_RETURN: float = 5.0     # 单日涨跌幅 > 5% → 结构性突破
    BULL_RETURN_THRESHOLD: float = 10.0            # 30日涨跌幅 > 10% → 牛市趋势
    BEAR_RETURN_THRESHOLD: float = -10.0           # 30日涨跌幅 < -10% → 熊市趋势

    # detect_from_signals 路径阈值（原始日收益率，无量纲）
    _SIGNALS_HIGH_VOL: float = 0.025               # 年化≈25%，日≈1.58%
    _SIGNALS_TREND_MIN_RETURN: float = 0.08        # 60日涨跌幅 > 8% → 趋势
    _SIGNALS_STRUCTURAL_BREAK_RATIO: float = 2.5   # 近5日/前55日波动比 > 2.5 → 突破

    # ── 公开接口 ──────────────────────────────────────────────────────────

    def detect(self, market_data: dict) -> MarketRegime:
        """基于预计算统计量检测当前 regime（确定性规则）。

        Args:
            market_data: 包含以下可选字段的字典：
                - volatility_30d (float)：30日日均波动率（%），如 1.2 表示 1.2%
                - ma5, ma20, ma60 (float)：5/20/60日移动均线价格
                - market_return_30d (float)：30日累积涨跌幅（%），如 12.5 表示 +12.5%
                - max_daily_return (float, 可选)：近期最大单日涨跌幅绝对值（%）

        Returns:
            MarketRegime 枚举值

        Notes:
            - 任何字段缺失时，对应规则跳过（降级到后续规则）
            - 所有规则均跳过时，返回 RANGE_BOUND（保守默认）
        """
        vol = market_data.get("volatility_30d")
        ma5 = market_data.get("ma5")
        ma20 = market_data.get("ma20")
        ma60 = market_data.get("ma60")
        ret30 = market_data.get("market_return_30d")
        max_daily = market_data.get("max_daily_return")

        # 规则 1：STRUCTURAL_BREAK
        # 触发条件：波动率极高 OR 单日涨跌幅超过阈值
        if vol is not None and vol > self.STRUCTURAL_BREAK_VOL_THRESHOLD:
            return MarketRegime.STRUCTURAL_BREAK
        if max_daily is not None and abs(max_daily) > self.STRUCTURAL_BREAK_DAILY_RETURN:
            return MarketRegime.STRUCTURAL_BREAK

        # 规则 2：HIGH_VOLATILITY
        if vol is not None and vol > self.HIGH_VOL_THRESHOLD:
            return MarketRegime.HIGH_VOLATILITY

        # 规则 3：BULL_TREND（均线多头排列 + 正收益）
        if (
            ma5 is not None
            and ma20 is not None
            and ma60 is not None
            and ret30 is not None
        ):
            if ma5 > ma20 > ma60 and ret30 > self.BULL_RETURN_THRESHOLD:
                return MarketRegime.BULL_TREND

            # 规则 4：BEAR_TREND（均线空头排列 + 负收益）
            if ma5 < ma20 < ma60 and ret30 < self.BEAR_RETURN_THRESHOLD:
                return MarketRegime.BEAR_TREND

        # 规则 5：RANGE_BOUND（默认）
        return MarketRegime.RANGE_BOUND

    def detect_from_signals(self, signals: RegimeSignals) -> MarketRegime:
        """从原始价格序列检测 regime。

        依据 docs/design/stage-2-hypothesis-expansion.md §11.3 规格实现。

        Args:
            signals: RegimeSignals，包含 index_close 价格序列

        Returns:
            MarketRegime 枚举值。数据不足时降级为 RANGE_BOUND。
        """
        closes = signals.index_close
        if len(closes) < 5:
            return MarketRegime.RANGE_BOUND

        # 规则 1：STRUCTURAL_BREAK（近5日/前55日波动比）
        if self._is_structural_break(signals):
            return MarketRegime.STRUCTURAL_BREAK

        # 规则 2：HIGH_VOLATILITY
        daily_vol = self._compute_daily_vol(closes)
        if daily_vol > self._SIGNALS_HIGH_VOL:
            return MarketRegime.HIGH_VOLATILITY

        # 规则 3 & 4：趋势检测
        trend_return = self._compute_trend_return(closes)
        if trend_return > self._SIGNALS_TREND_MIN_RETURN:
            return MarketRegime.BULL_TREND
        if trend_return < -self._SIGNALS_TREND_MIN_RETURN:
            return MarketRegime.BEAR_TREND

        return MarketRegime.RANGE_BOUND

    # ── 内部辅助方法（detect_from_signals 路径） ──────────────────────────

    def _compute_trend_return(self, closes: List[float]) -> float:
        """计算价格序列的头尾涨跌幅。"""
        if len(closes) < 2 or closes[0] == 0:
            return 0.0
        return (closes[-1] - closes[0]) / closes[0]

    def _compute_daily_vol(self, closes: List[float]) -> float:
        """计算日收益率的标准差（无量纲）。"""
        if len(closes) < 5:
            return 0.0
        returns = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes))
            if closes[i - 1] != 0
        ]
        if len(returns) < 2:
            return 0.0
        return statistics.stdev(returns)

    def _is_structural_break(self, signals: RegimeSignals) -> bool:
        """检测近5日波动明显高于前55日（结构性突破信号）。

        近5日波动 / 前55日波动 > 2.5 时判定为结构性突破。
        """
        closes = signals.index_close
        if len(closes) < 10:
            return False
        recent_vol = self._compute_daily_vol(closes[-5:])
        prior_vol = self._compute_daily_vol(closes[-60:-5]) if len(closes) >= 60 else self._compute_daily_vol(closes[:-5])
        if prior_vol <= 0:
            return False
        return (recent_vol / prior_vol) > self._SIGNALS_STRUCTURAL_BREAK_RATIO
