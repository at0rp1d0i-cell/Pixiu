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
from difflib import SequenceMatcher
from datetime import UTC, datetime
from typing import Optional

import chromadb
from chromadb.config import Settings

from src.schemas.thresholds import THRESHOLDS
from src.schemas.backtest import BacktestReport
from src.schemas.judgment import CriticVerdict, RiskAuditReport
from src.schemas.research_note import FactorResearchNote
from src.schemas.factor_pool import FactorPoolRecord
from src.schemas.failure_constraint import FailureConstraint, FailureMode
from .islands import ISLANDS


logger = logging.getLogger(__name__)

# ChromaDB 持久化路径
_DEFAULT_DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "factor_pool_db")
)

# ChromaDB collection 名称
COLLECTION_NAME = "factor_experiments"


def _match_where(metadata: dict, where: Optional[dict]) -> bool:
    if not where:
        return True
    if "$and" in where:
        return all(_match_where(metadata, clause) for clause in where["$and"])
    return all(metadata.get(key) == value for key, value in where.items())


class _InMemoryCollection:
    def __init__(self, name: str):
        self.name = name
        self._items: dict[str, dict] = {}

    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict]):
        for item_id, document, metadata in zip(ids, documents, metadatas):
            self._items[item_id] = {
                "id": item_id,
                "document": document,
                "metadata": metadata,
            }

    def count(self) -> int:
        return len(self._items)

    def get(
        self,
        ids: Optional[list[str]] = None,
        where: Optional[dict] = None,
        include: Optional[list[str]] = None,
        limit: Optional[int] = None,
    ):
        records = list(self._items.values())
        if ids is not None:
            wanted = set(ids)
            records = [record for record in records if record["id"] in wanted]
        records = [
            record for record in records
            if _match_where(record["metadata"], where)
        ]
        if limit is not None:
            records = records[:limit]
        return {
            "ids": [record["id"] for record in records],
            "documents": [record["document"] for record in records] if not include or "documents" in include else [],
            "metadatas": [record["metadata"] for record in records] if not include or "metadatas" in include else [],
        }

    def query(
        self,
        query_texts: list[str],
        n_results: int,
        where: Optional[dict] = None,
        include: Optional[list[str]] = None,
    ):
        query_text = query_texts[0] if query_texts else ""
        records = [
            record for record in self._items.values()
            if _match_where(record["metadata"], where)
        ]
        scored = []
        for record in records:
            if query_text:
                similarity = SequenceMatcher(None, query_text, record["document"]).ratio()
                distance = 1.0 - similarity
            else:
                distance = 0.0
            scored.append((distance, record))

        scored.sort(key=lambda item: item[0])
        top = scored[:n_results]

        return {
            "ids": [[record["id"] for _, record in top]],
            "documents": [[record["document"] for _, record in top]] if include and "documents" in include else [[]],
            "metadatas": [[record["metadata"] for _, record in top]] if include and "metadatas" in include else [[]],
            "distances": [[distance for distance, _ in top]] if include and "distances" in include else [[]],
        }


class _InMemoryClient:
    def __init__(self):
        self._collections: dict[str, _InMemoryCollection] = {}

    def get_or_create_collection(self, name: str):
        if name not in self._collections:
            self._collections[name] = _InMemoryCollection(name)
        return self._collections[name]


class FactorPool:
    """因子实验历史库，支持 Island 分组和向量相似检索。"""

    CONSTRAINT_COLLECTION = "failure_constraints"

    def __init__(self, db_path: str = _DEFAULT_DB_PATH):
        os.makedirs(db_path, exist_ok=True)
        self._storage_mode = "persistent"
        try:
            self._client = chromadb.PersistentClient(
                path=db_path,
                settings=Settings(anonymized_telemetry=False),
            )
        except Exception as e:
            logger.warning(
                "[FactorPool] PersistentClient 初始化失败，降级为 in-memory client: %s",
                e,
            )
            self._client = _InMemoryClient()
            self._storage_mode = "in_memory"
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
        # v2 新增：结构化失败约束
        self._constraints_collection = self._client.get_or_create_collection(
            name=self.CONSTRAINT_COLLECTION,
        )
        logger.info("[FactorPool] 初始化完成，数据库路径：%s，模式：%s", db_path, self._storage_mode)
        logger.info("[FactorPool] 当前存储因子数量：%d", self._collection.count())

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
        note: Optional[FactorResearchNote] = None,
    ) -> None:
        """将完整执行结果（BacktestReport + CriticVerdict + RiskAuditReport）写入 factors collection。"""
        factor_spec = report.factor_spec
        turnover = report.metrics.turnover_rate
        coverage = report.metrics.coverage
        subspace_origin = (
            note.exploration_subspace.value if note and note.exploration_subspace else None
        )
        record = FactorPoolRecord(
            factor_id=report.factor_id,
            note_id=report.note_id,
            formula=factor_spec.formula if factor_spec else report.formula,
            hypothesis=factor_spec.hypothesis if factor_spec else hypothesis,
            economic_rationale=factor_spec.economic_rationale if factor_spec else "",
            backtest_report_id=report.report_id,
            verdict_id=verdict.verdict_id,
            decision=verdict.decision or "",
            score=verdict.score,
            sharpe=report.metrics.sharpe,
            ic_mean=report.metrics.ic_mean,
            icir=report.metrics.icir,
            turnover=turnover,
            max_drawdown=report.metrics.max_drawdown,
            coverage=coverage,
            created_at=datetime.now(UTC),
            tags=verdict.pool_tags,
            subspace_origin=subspace_origin,
        )
        self._collection.upsert(
            ids=[report.factor_id],
            documents=[record.formula],
            metadatas=[{
                "island": report.island,
                "note_id": record.note_id,
                "formula": record.formula,
                "hypothesis": record.hypothesis,
                "economic_rationale": record.economic_rationale,
                "backtest_report_id": record.backtest_report_id,
                "verdict_id": record.verdict_id,
                "passed": verdict.overall_passed,
                "decision": record.decision,
                "score": record.score,
                "sharpe": record.sharpe,
                "ic_mean": record.ic_mean,
                "icir": record.icir,
                "turnover": record.turnover,
                "max_drawdown": record.max_drawdown,
                "coverage": record.coverage if record.coverage is not None else 0.0,
                "failure_mode": verdict.failure_mode or "",
                "reason_codes": json.dumps(verdict.reason_codes),
                "overfitting_score": risk_report.overfitting_score,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "tags": json.dumps(record.tags),
                "subspace_origin": record.subspace_origin or "",
                # 向后兼容旧字段
                "beats_baseline": verdict.overall_passed,
                "parse_success": report.passed,
                "ic": report.metrics.ic_mean,
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

    def register_factor_v2(self, record: FactorPoolRecord) -> None:
        """
        v2 Golden Path: 写入 FactorPoolRecord

        按照 v2_stage45_golden_path.md 规格实现
        """
        # 向量化文档：公式 + 假设 + 逻辑
        document = (
            f"公式: {record.formula}\n"
            f"假设: {record.hypothesis}\n"
            f"逻辑: {record.economic_rationale}"
        )

        # 元数据
        metadata = {
            "factor_id": record.factor_id,
            "note_id": record.note_id,
            "formula": record.formula,
            "hypothesis": record.hypothesis,
            "economic_rationale": record.economic_rationale,
            "backtest_report_id": record.backtest_report_id,
            "verdict_id": record.verdict_id,
            "decision": record.decision,
            "score": record.score,
            "sharpe": record.sharpe or 0.0,
            "ic_mean": record.ic_mean or 0.0,
            "icir": record.icir or 0.0,
            "turnover": record.turnover or 0.0,
            "max_drawdown": record.max_drawdown or 0.0,
            "coverage": record.coverage or 0.0,
            "created_at": record.created_at.isoformat(),
            "tags": json.dumps(record.tags),
            "subspace_origin": record.subspace_origin or "",
            # 向后兼容
            "passed": record.decision == "promote",
            "beats_baseline": record.decision == "promote",
        }

        self._collection.upsert(
            ids=[record.factor_id],
            documents=[document],
            metadatas=[metadata],
        )
        logger.info(
            "[FactorPool] register_factor_v2: %s → decision=%s, score=%.3f",
            record.factor_id, record.decision, record.score,
        )

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

    # ═══════════════════════════════════════════════════════
    # v2 失败约束 API
    # ═══════════════════════════════════════════════════════

    def register_constraint(self, constraint: FailureConstraint) -> None:
        """写入一条 FailureConstraint。"""
        self._constraints_collection.upsert(
            ids=[constraint.constraint_id],
            documents=[constraint.constraint_rule],
            metadatas=[{
                "failure_mode": constraint.failure_mode.value,
                "island": constraint.island,
                "subspace": constraint.subspace or "",
                "formula_pattern": constraint.formula_pattern,
                "severity": constraint.severity,
                "times_violated": constraint.times_violated,
                "times_checked": constraint.times_checked,
                "created_at": constraint.created_at,
                "source_note_id": constraint.source_note_id,
                "source_verdict_id": constraint.source_verdict_id,
                "last_violated_at": constraint.last_violated_at or "",
            }],
        )
        logger.info(
            "[FactorPool] register_constraint: %s → island=%s, mode=%s, severity=%s",
            constraint.constraint_id, constraint.island,
            constraint.failure_mode.value, constraint.severity,
        )

    def query_constraints(
        self,
        island: Optional[str] = None,
        failure_mode: Optional[FailureMode] = None,
        limit: int = 10,
    ) -> list[FailureConstraint]:
        """按 island / failure_mode 查询约束。"""
        where_clauses: dict = {}
        if island and failure_mode:
            where_clauses = {"$and": [
                {"island": island},
                {"failure_mode": failure_mode.value},
            ]}
        elif island:
            where_clauses = {"island": island}
        elif failure_mode:
            where_clauses = {"failure_mode": failure_mode.value}

        try:
            results = self._constraints_collection.get(
                where=where_clauses if where_clauses else None,
                include=["metadatas", "documents"],
            )
            return self._parse_constraint_results_get(results)[:limit]
        except Exception as e:
            logger.warning("[FactorPool] query_constraints failed: %s", e)
            return []

    def query_constraints_by_formula(
        self,
        formula: str,
        limit: int = 5,
    ) -> list[FailureConstraint]:
        """按公式相似度检索相关约束（fallback 模式下退化为精确匹配）。"""
        try:
            count = self._constraints_collection.count()
            if count == 0:
                return []
            results = self._constraints_collection.query(
                query_texts=[formula],
                n_results=min(limit, count),
                include=["metadatas", "documents"],
            )
            return self._parse_constraint_results_query(results)
        except Exception as e:
            logger.warning("[FactorPool] query_constraints_by_formula failed: %s", e)
            return []

    def increment_checked(self, constraint_id: str) -> None:
        """记录一次约束检查（无论是否匹配），递增 times_checked。"""
        try:
            result = self._constraints_collection.get(
                ids=[constraint_id],
                include=["metadatas", "documents"],
            )
            if not result["ids"]:
                return
            meta = result["metadatas"][0]
            doc = result["documents"][0] if result.get("documents") else meta.get("constraint_rule", "")
            updated_meta = {
                **meta,
                "times_checked": meta.get("times_checked", 0) + 1,
            }
            self._constraints_collection.upsert(
                ids=[constraint_id],
                documents=[doc],
                metadatas=[updated_meta],
            )
        except Exception as e:
            logger.warning("[FactorPool] increment_checked failed: %s", e)

    def increment_violation(self, constraint_id: str) -> None:
        """记录一次约束违反，更新 times_violated / times_checked / last_violated_at。"""
        try:
            result = self._constraints_collection.get(
                ids=[constraint_id],
                include=["metadatas", "documents"],
            )
            if not result["ids"]:
                logger.warning("[FactorPool] increment_violation: constraint %s not found", constraint_id)
                return
            meta = result["metadatas"][0]
            doc = result["documents"][0] if result.get("documents") else meta.get("constraint_rule", "")
            now_iso = datetime.now(UTC).isoformat()
            updated_meta = {
                **meta,
                "times_violated": meta.get("times_violated", 0) + 1,
                "times_checked": meta.get("times_checked", 0) + 1,
                "last_violated_at": now_iso,
            }
            self._constraints_collection.upsert(
                ids=[constraint_id],
                documents=[doc],
                metadatas=[updated_meta],
            )
        except Exception as e:
            logger.warning("[FactorPool] increment_violation failed: %s", e)

    def _parse_constraint_results_get(self, results: dict) -> list[FailureConstraint]:
        """从 collection.get() 结果中解析 FailureConstraint 列表。"""
        constraints = []
        ids = results.get("ids", [])
        metadatas = results.get("metadatas", [])
        documents = results.get("documents", [])
        for i, cid in enumerate(ids):
            meta = metadatas[i] if i < len(metadatas) else {}
            doc = documents[i] if i < len(documents) else meta.get("constraint_rule", "")
            try:
                constraints.append(FailureConstraint(
                    constraint_id=cid,
                    source_note_id=meta.get("source_note_id", ""),
                    source_verdict_id=meta.get("source_verdict_id", ""),
                    failure_mode=FailureMode(meta["failure_mode"]),
                    island=meta.get("island", ""),
                    subspace=meta.get("subspace") or None,
                    formula_pattern=meta.get("formula_pattern", ""),
                    constraint_rule=doc,
                    severity=meta.get("severity", "warning"),
                    created_at=meta.get("created_at", datetime.now(UTC).isoformat()),
                    times_violated=int(meta.get("times_violated", 0)),
                    times_checked=int(meta.get("times_checked", 0)),
                    last_violated_at=meta.get("last_violated_at") or None,
                ))
            except Exception as e:
                logger.warning("[FactorPool] _parse_constraint_results_get skip %s: %s", cid, e)
        return constraints

    def _parse_constraint_results_query(self, results: dict) -> list[FailureConstraint]:
        """从 collection.query() 结果中解析 FailureConstraint 列表。"""
        # query() wraps results in an extra list dimension
        ids_outer = results.get("ids", [[]])
        metas_outer = results.get("metadatas", [[]])
        docs_outer = results.get("documents", [[]])
        ids = ids_outer[0] if ids_outer else []
        metadatas = metas_outer[0] if metas_outer else []
        documents = docs_outer[0] if docs_outer else []
        flat = {"ids": ids, "metadatas": metadatas, "documents": documents}
        return self._parse_constraint_results_get(flat)


def _summarize_failure(meta: dict) -> str:
    """从元数据生成人类可读的失败原因摘要（注入给 Researcher）。"""
    reasons = []
    sharpe = meta.get("sharpe", 0.0)
    ic = meta.get("ic", 0.0)
    icir = meta.get("icir", 0.0)
    turnover = meta.get("turnover", 0.0)

    if sharpe <= THRESHOLDS.min_sharpe:
        reasons.append(f"Sharpe={sharpe:.2f}（基线{THRESHOLDS.min_sharpe}）")
    if ic != 0.0 and ic < THRESHOLDS.min_ic_mean:
        reasons.append(f"IC={ic:.4f}（低于{THRESHOLDS.min_ic_mean}）")
    if icir != 0.0 and icir < THRESHOLDS.min_icir:
        # THRESHOLDS.min_icir = 0.30
        reasons.append(f"ICIR={icir:.2f}（低于{THRESHOLDS.min_icir}）")
    if turnover != 0.0 and turnover > THRESHOLDS.max_turnover_rate:
        # turnover_rate 单位为小数（0~1），THRESHOLDS.max_turnover_rate = 0.50
        reasons.append(f"换手率={turnover:.4f}（高于{THRESHOLDS.max_turnover_rate}）")

    return "；".join(reasons) if reasons else "指标未达标"


# 模块级单例（跨调用复用连接）
_pool_instance: Optional[FactorPool] = None


def get_factor_pool() -> FactorPool:
    """获取 FactorPool 单例。"""
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = FactorPool()
    return _pool_instance
