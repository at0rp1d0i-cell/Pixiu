"""
Pixiu: FactorPool — 因子实验历史库
基于 ChromaDB 持久化，支持：
  - 存储因子假设 + 回测指标
  - 按 Island 分组管理
  - 向量相似检索（相似因子、相似失败案例）
  - Island 排行榜查询
"""
import json
import logging
import os
from datetime import datetime
from typing import Optional

import chromadb
from chromadb.config import Settings

from src.agents.schemas import BacktestMetrics, FactorHypothesis
from src.schemas.thresholds import THRESHOLDS
from src.schemas.backtest import BacktestReport
from src.schemas.judgment import CriticVerdict, RiskAuditReport
from src.schemas.research_note import FactorResearchNote
from .islands import ISLANDS


logger = logging.getLogger(__name__)

# ChromaDB 持久化路径
_DEFAULT_DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "factor_pool_db")
)

# ChromaDB collection 名称
COLLECTION_NAME = "factor_experiments"


class FactorPool:
    """因子实验历史库，支持 Island 分组和向量相似检索。"""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH):
        os.makedirs(db_path, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(anonymized_telemetry=False),
        )
        # v1 已有：因子回测结果
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
        )
        # v2 新增：研究笔记归档（供 SynthesisAgent 语义检索）
        self._notes_collection = self._client.get_or_create_collection(
            name="research_notes",
        )
        # v2 新增：EDA 探索结果归档
        self._explorations_collection = self._client.get_or_create_collection(
            name="exploration_results",
        )
        logger.info("[FactorPool] 初始化完成，数据库路径：%s", db_path)
        logger.info("[FactorPool] 当前存储因子数量：%d", self._collection.count())

    # ─────────────────────────────────────────────
    # 写入：注册新因子实验
    # ─────────────────────────────────────────────
    def register(
        self,
        hypothesis: FactorHypothesis,
        metrics: BacktestMetrics,
        island_name: str,
        run_id: Optional[str] = None,
    ) -> str:
        """将一次因子实验结果存入 FactorPool。

        Args:
            hypothesis: Researcher 提出的结构化因子假设
            metrics: Critic 解析的回测指标
            island_name: 所属 Island 名称（如 'momentum'）
            run_id: 可选的唯一标识符，默认自动生成

        Returns:
            factor_id: 存储的唯一 ID
        """
        if not run_id:
            run_id = f"{island_name}_{hypothesis.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 向量化文档：公式 + 假设 + 逻辑（用于相似检索）
        document = (
            f"公式: {hypothesis.formula}\n"
            f"假设: {hypothesis.hypothesis}\n"
            f"逻辑: {hypothesis.rationale}"
        )

        # 元数据：所有可查询的结构化字段
        metadata = {
            "island": island_name,
            "factor_name": hypothesis.name,
            "formula": hypothesis.formula,
            "hypothesis": hypothesis.hypothesis,
            "rationale": hypothesis.rationale,
            "expected_direction": hypothesis.expected_direction,
            "market_observation": hypothesis.market_observation or "",
            # 回测指标
            "sharpe": metrics.sharpe,
            "ic": metrics.ic,
            "icir": metrics.icir,
            "turnover": metrics.turnover,
            "annualized_return": metrics.annualized_return,
            "max_drawdown": metrics.max_drawdown,
            "parse_success": metrics.parse_success,
            # 时间戳
            "registered_at": datetime.now().isoformat(),
            # 是否达到基线（方便过滤）
            "beats_baseline": metrics.sharpe > THRESHOLDS.min_sharpe and metrics.parse_success,
        }

        self._collection.upsert(
            ids=[run_id],
            documents=[document],
            metadatas=[metadata],
        )
        logger.info(
            "[FactorPool] 注册因子 %s → Island=%s, Sharpe=%.2f",
            hypothesis.name, island_name, metrics.sharpe,
        )
        return run_id

    # ─────────────────────────────────────────────
    # 读取：Island 最优因子
    # ─────────────────────────────────────────────
    def get_island_best_factors(self, island_name: str, top_k: int = 3) -> list[dict]:
        """获取指定 Island 中 Sharpe 最高的 top_k 个因子。

        Args:
            island_name: Island 名称
            top_k: 返回数量，默认 3

        Returns:
            list of dict，每个 dict 包含因子的完整元数据
        """
        results = self._collection.get(
            where={"island": island_name},
            include=["metadatas", "documents"],
        )

        if not results["ids"]:
            return []

        # 按 Sharpe 降序排列
        items = list(zip(results["metadatas"], results["documents"], results["ids"]))
        items.sort(key=lambda x: x[0].get("sharpe", 0.0), reverse=True)

        return [
            {**meta, "document": doc, "id": fid}
            for meta, doc, fid in items[:top_k]
        ]

    # ─────────────────────────────────────────────
    # 读取：相似失败案例（error-driven RAG）
    # ─────────────────────────────────────────────
    def get_similar_failures(self, formula: str, top_k: int = 3) -> list[dict]:
        """查找与给定公式最相似的历史失败因子及其失败原因。

        失败定义：parse_success=True 但 Sharpe <= 2.67（已回测但未达标）。

        Args:
            formula: 当前因子的 Qlib 公式（用于向量相似检索）
            top_k: 返回数量

        Returns:
            list of dict，包含失败因子的元数据和失败上下文
        """
        # 只查失败的（已回测 + 未达标）
        results = self._collection.query(
            query_texts=[formula],
            n_results=min(top_k * 3, max(self._collection.count(), 1)),  # 多取一些再过滤
            where={"$and": [
                {"parse_success": True},
                {"beats_baseline": False},
            ]},
            include=["metadatas", "documents", "distances"],
        )

        if not results["ids"] or not results["ids"][0]:
            return []

        items = list(zip(
            results["metadatas"][0],
            results["documents"][0],
            results["distances"][0],
            results["ids"][0],
        ))
        # 按向量距离排序（最相似在前）
        items.sort(key=lambda x: x[2])

        return [
            {
                **meta,
                "document": doc,
                "similarity_distance": dist,
                "id": fid,
                "failure_reason": _summarize_failure(meta),
            }
            for meta, doc, dist, fid in items[:top_k]
        ]

    # ─────────────────────────────────────────────
    # 读取：Island 排行榜
    # ─────────────────────────────────────────────
    def get_island_leaderboard(self) -> list[dict]:
        """获取所有 Island 的表现排行榜。

        Returns:
            list of dict，每个 Island 一条记录，包含：
            island_name、factor_count、best_sharpe、avg_sharpe、best_factor_name
        """
        all_results = self._collection.get(include=["metadatas"])

        if not all_results["ids"]:
            return []

        # 按 Island 分组统计
        island_stats: dict[str, list[float]] = {}
        island_best: dict[str, dict] = {}

        for meta in all_results["metadatas"]:
            iname = meta.get("island", "unknown")
            sharpe = meta.get("sharpe", 0.0)

            if iname not in island_stats:
                island_stats[iname] = []
                island_best[iname] = meta

            island_stats[iname].append(sharpe)

            if sharpe > island_best[iname].get("sharpe", 0.0):
                island_best[iname] = meta

        leaderboard = []
        for iname, sharpes in island_stats.items():
            best_meta = island_best[iname]
            leaderboard.append({
                "island": iname,
                "island_display_name": ISLANDS.get(iname, {}).get("name", iname),
                "factor_count": len(sharpes),
                "best_sharpe": max(sharpes),
                "avg_sharpe": sum(sharpes) / len(sharpes),
                "best_factor_name": best_meta.get("factor_name", ""),
                "best_factor_formula": best_meta.get("formula", ""),
            })

        # 按 best_sharpe 降序
        leaderboard.sort(key=lambda x: x["best_sharpe"], reverse=True)
        return leaderboard

    # ─────────────────────────────────────────────
    # 读取：全局统计
    # ─────────────────────────────────────────────
    def get_stats(self) -> dict:
        """获取 FactorPool 全局统计信息。"""
        count = self._collection.count()
        if count == 0:
            return {"total_factors": 0, "beats_baseline_count": 0}

        all_results = self._collection.get(include=["metadatas"])
        sharpes = [m.get("sharpe", 0.0) for m in all_results["metadatas"]]
        beats = sum(1 for m in all_results["metadatas"] if m.get("beats_baseline", False))

        return {
            "total_factors": count,
            "beats_baseline_count": beats,
            "global_best_sharpe": max(sharpes) if sharpes else 0.0,
            "global_avg_sharpe": sum(sharpes) / len(sharpes) if sharpes else 0.0,
        }


    # ═══════════════════════════════════════════════════════
    # v2 新增 API
    # ═══════════════════════════════════════════════════════

    def register_factor(
        self,
        report: BacktestReport,
        verdict: CriticVerdict,
        risk_report: RiskAuditReport,
        hypothesis: str = "",
    ) -> None:
        """将完整执行结果（BacktestReport + CriticVerdict + RiskAuditReport）写入 factors collection。"""
        self._collection.upsert(
            ids=[report.factor_id],
            documents=[report.formula],
            metadatas=[{
                "island": report.island,
                "formula": report.formula,
                "hypothesis": hypothesis,
                "passed": verdict.overall_passed,
                "sharpe": report.metrics.sharpe,
                "ic_mean": report.metrics.ic_mean,
                "icir": report.metrics.icir,
                "turnover_rate": report.metrics.turnover_rate,
                "failure_mode": verdict.failure_mode or "",
                "overfitting_score": risk_report.overfitting_score,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "tags": json.dumps(verdict.pool_tags),
                # 向后兼容旧字段
                "beats_baseline": verdict.overall_passed,
                "parse_success": report.passed,
                "ic": report.metrics.ic_mean,
                "icir": report.metrics.icir,
                "turnover": report.metrics.turnover_rate,
                "sharpe": report.metrics.sharpe,
            }],
        )
        logger.info(
            "[FactorPool] register_factor: %s → passed=%s, Sharpe=%.2f",
            report.factor_id, verdict.overall_passed, report.metrics.sharpe,
        )

    def get_passed_factors(
        self,
        island: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """获取通过审核的因子，用于 RiskAuditor 相关性检测。"""
        where: dict = {"passed": True}
        if island:
            where = {"$and": [{"passed": True}, {"island": island}]}
        try:
            results = self._collection.query(
                query_texts=[""],
                n_results=limit,
                where=where,
                include=["metadatas", "documents"],
            )
            if not results["ids"] or not results["ids"][0]:
                return []
            return [
                {**meta, "document": doc}
                for meta, doc in zip(results["metadatas"][0], results["documents"][0])
            ]
        except Exception as e:
            logger.warning("[FactorPool] get_passed_factors failed: %s", e)
            return []

    def get_top_factors(self, limit: int = 20) -> list[dict]:
        """获取全局 Sharpe 最高的因子，用于 PortfolioManager 配仓。"""
        try:
            results = self._collection.query(
                query_texts=[""],
                n_results=min(limit * 3, max(self._collection.count(), 1)),
                where={"passed": True},
                include=["metadatas", "documents", "ids"],
            )
            if not results["ids"] or not results["ids"][0]:
                return []
            factors = [
                {**meta, "document": doc, "factor_id": fid}
                for meta, doc, fid in zip(
                    results["metadatas"][0],
                    results["documents"][0],
                    results["ids"][0],
                )
            ]
            factors.sort(key=lambda x: x.get("sharpe", 0), reverse=True)
            return factors[:limit]
        except Exception as e:
            logger.warning("[FactorPool] get_top_factors failed: %s", e)
            return []

    def get_common_failure_modes(
        self,
        island: str,
        limit: int = 10,
    ) -> list[dict]:
        """获取某 Island 的常见失败模式频率统计，给 LiteratureMiner 用。"""
        from collections import Counter
        try:
            results = self._collection.query(
                query_texts=[""],
                n_results=max(limit * 2, 1),
                where={"$and": [{"island": island}, {"passed": False}]},
                include=["metadatas"],
            )
            if not results["ids"] or not results["ids"][0]:
                return []
            modes = Counter(
                m.get("failure_mode")
                for m in results["metadatas"][0]
                if m.get("failure_mode")
            )
            return [{"failure_mode": k, "count": v} for k, v in modes.most_common()]
        except Exception as e:
            logger.warning("[FactorPool] get_common_failure_modes failed: %s", e)
            return []

    def archive_research_note(self, note: FactorResearchNote) -> None:
        """将 FactorResearchNote 存入 research_notes collection，供后续语义检索。"""
        self._notes_collection.upsert(
            ids=[note.note_id],
            documents=[note.hypothesis],
            metadatas=[{
                "island": note.island,
                "proposed_formula": note.proposed_formula,
                "final_formula": note.final_formula or "",
                "status": note.status,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "had_exploration": len(note.exploration_questions) > 0,
            }],
        )
        logger.info("[FactorPool] archive_research_note: %s", note.note_id)

    def get_island_factors(
        self,
        island: str,
        limit: int = 50,
    ) -> list[dict]:
        """获取某 Island 所有历史因子（含未通过的），供 NoveltyFilter 用于相似度检查。"""
        try:
            results = self._collection.get(
                where={"island": island},
                include=["metadatas", "documents"],
            )
            if not results["ids"]:
                return []
            return [
                {**meta, "formula": meta.get("formula", ""), "factor_id": fid}
                for meta, fid in zip(results["metadatas"], results["ids"])
            ][:limit]
        except Exception as e:
            logger.warning("[FactorPool] get_island_factors failed: %s", e)
            return []

def _summarize_failure(meta: dict) -> str:
    """从元数据生成人类可读的失败原因摘要（注入给 Researcher）。"""
    reasons = []
    sharpe = meta.get("sharpe", 0.0)
    ic = meta.get("ic", 0.0)
    icir = meta.get("icir", 0.0)
    turnover = meta.get("turnover", 0.0)

    if sharpe <= THRESHOLDS.min_sharpe:
        reasons.append(f"Sharpe={sharpe:.2f}（基线{THRESHOLDS.min_sharpe}）")
    if ic != 0.0 and ic < 0.02:
        reasons.append(f"IC={ic:.4f}（低于0.02）")
    if icir != 0.0 and icir < 0.3:
        reasons.append(f"ICIR={icir:.2f}（不稳定）")
    if turnover != 0.0 and turnover > 50.0:
        reasons.append(f"换手率={turnover:.1f}%（过高）")

    return "；".join(reasons) if reasons else "指标未达标"


# 模块级单例（跨调用复用连接）
_pool_instance: Optional[FactorPool] = None


def get_factor_pool() -> FactorPool:
    """获取 FactorPool 单例。"""
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = FactorPool()
    return _pool_instance
