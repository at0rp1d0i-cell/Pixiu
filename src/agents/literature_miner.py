"""
Pixiu v2 Stage 1：LiteratureMiner Agent

职责：从 FactorPool 检索各 Island 的历史优秀因子和常见失败模式，
      生成 HistoricalInsight 列表，为 AlphaResearcher 提供历史参考。

不使用 LLM，直接调用 FactorPool API。
"""
import logging
from src.schemas.market_context import HistoricalInsight
from src.factor_pool.pool import FactorPool

logger = logging.getLogger(__name__)


class LiteratureMiner:
    """
    Stage 1 历史文献挖掘器。

    不使用 LLM，直接调用 FactorPool API 生成结构化摘要。
    FactorPool 为空时返回提示性 HistoricalInsight，不报错。
    """

    def __init__(self, factor_pool: FactorPool):
        self.pool = factor_pool

    async def retrieve_insights(
        self,
        active_islands: list[str],
    ) -> list[HistoricalInsight]:
        """
        为每个 active Island 检索历史洞察。

        Args:
            active_islands: 当前激活的 Island 列表

        Returns:
            list[HistoricalInsight]，每个 Island 一条
        """
        insights = []
        for island in active_islands:
            try:
                top = self.pool.get_island_best_factors(island_name=island, top_k=3)
                failures = self.pool.get_common_failure_modes(island=island, limit=5)
            except Exception as e:
                logger.warning("[LiteratureMiner] FactorPool 查询失败 (island=%s): %s", island, e)
                top, failures = [], []

            if not top:
                # 该 Island 尚无历史数据，给出引导性提示
                insights.append(HistoricalInsight(
                    island=island,
                    best_factor_formula="（无历史记录）",
                    best_sharpe=0.0,
                    common_failure_modes=[],
                    suggested_directions=["从基础动量因子开始探索"],
                ))
                continue

            best = top[0]
            insights.append(HistoricalInsight(
                island=island,
                best_factor_formula=best.get("formula", best.get("formula_str", "")),
                best_sharpe=best.get("sharpe", 0.0),
                common_failure_modes=[f.get("failure_mode", "") for f in failures],
                suggested_directions=self._infer_directions(top, failures),
            ))

        return insights

    def _infer_directions(
        self,
        top_factors: list[dict],
        failure_modes: list[dict],
    ) -> list[str]:
        """
        基于历史最优因子和失败模式，推断本轮建议方向。

        规则：
        - high_turnover 是常见失败 → 建议增大时间窗口
        - low_ic 是常见失败 → 建议换信号类型
        - 历史最优 Sharpe > 3.0 → 建议在此方向深化
        """
        suggestions = []
        failure_types = {f.get("failure_mode", "") for f in failure_modes}

        if "high_turnover" in failure_types:
            suggestions.append("增大时间窗口参数（如 Mean(x,5) → Mean(x,20)）")
        if "low_ic" in failure_types:
            suggestions.append("尝试换用不同类型的信号（量价/资金流/情绪等）")
        if top_factors and top_factors[0].get("sharpe", 0) > 3.0:
            best_formula = top_factors[0].get("formula", "")
            suggestions.append(f"在已有最优因子基础上组合变体：{best_formula[:60]}")
        if not suggestions:
            suggestions.append("当前方向进展正常，继续探索")

        return suggestions[:3]
