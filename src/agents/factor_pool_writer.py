"""
Compatibility utility for writing a `FactorPoolRecord`.

Canonical Stage 5 runtime writes through `src.agents.judgment` +
`FactorPool.register_factor`. This helper remains for tests and narrow
standalone flows that already operate on `report + verdict`.
"""
import logging
from datetime import UTC, datetime
from src.schemas.backtest import BacktestReport
from src.schemas.judgment import CriticVerdict
from src.schemas.factor_pool import FactorPoolRecord
from src.factor_pool.pool import FactorPool

logger = logging.getLogger(__name__)

class FactorPoolWriter:
    """
    负责将 BacktestReport + CriticVerdict 写入 FactorPool
    """

    def __init__(self, pool: FactorPool):
        self.pool = pool

    def write_record(
        self,
        report: BacktestReport,
        verdict: CriticVerdict,
    ) -> str:
        """
        写入 FactorPool 记录

        Returns:
            factor_id: 写入的因子 ID
        """
        # 构建 FactorPoolRecord
        record = FactorPoolRecord(
            factor_id=f"{report.island_id}_{report.note_id}",
            note_id=report.note_id,
            formula=report.factor_spec.formula,
            hypothesis=report.factor_spec.hypothesis,
            economic_rationale=report.factor_spec.economic_rationale,
            backtest_report_id=report.report_id,
            verdict_id=verdict.verdict_id,
            decision=verdict.decision,
            score=verdict.score,
            sharpe=report.metrics.sharpe,
            ic_mean=report.metrics.ic_mean,
            icir=report.metrics.icir,
            turnover=report.metrics.turnover_rate,
            max_drawdown=report.metrics.max_drawdown,
            coverage=report.metrics.coverage,
            created_at=datetime.now(UTC),
            tags=self._build_tags(report, verdict),
        )

        # 写入 ChromaDB
        try:
            self.pool.register_factor_v2(record)
            logger.info(f"[FactorPoolWriter] 写入成功: {record.factor_id}")
            return record.factor_id
        except Exception as e:
            logger.error(f"[FactorPoolWriter] 写入失败: {e}")
            raise

    def _build_tags(self, report: BacktestReport, verdict: CriticVerdict) -> list:
        """构建标签"""
        tags = [
            f"island:{report.island_id}",
            f"decision:{verdict.decision}",
        ]

        # 添加原因码标签
        for reason in verdict.reason_codes:
            tags.append(f"reason:{reason}")

        # 添加分数区间标签
        if verdict.score >= 0.8:
            tags.append("score:excellent")
        elif verdict.score >= 0.6:
            tags.append("score:good")
        elif verdict.score >= 0.4:
            tags.append("score:fair")
        else:
            tags.append("score:poor")

        return tags
