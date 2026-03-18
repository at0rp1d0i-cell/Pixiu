"""
SynthesisAgent: 跨 Island 语义关联与去重

Stage 2b — 在 hypothesis_gen 之后、prefilter 之前执行。

功能：
1. TF-IDF 向量化所有候选 research notes
2. cosine similarity > 0.85 → 去重（保留公式更复杂的）
3. 层次聚类（scipy）→ 识别 factor families（阈值 0.60）
4. 跨 island 互补假设 → 提出 merge 建议（最多 3 个）

任何步骤失败均降级为 pass-through，不阻塞主链。

设计规格：docs/design/synthesis-agent.md
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from src.schemas.research_note import FactorResearchNote, SynthesisInsight
from src.schemas.thresholds import THRESHOLDS

logger = logging.getLogger(__name__)


@dataclass
class SynthesisResult:
    """SynthesisAgent 的完整输出。"""

    filtered_notes: list[FactorResearchNote]
    removed_notes: list[str]                    # 被去重移除的 note_id 列表
    insights: list[SynthesisInsight]            # 去重 + family 关联
    families: dict[str, list[str]]              # family_label → [note_ids]
    merge_candidates: list[SynthesisInsight]    # 建议跨 island 合并的 pairs


class SynthesisAgent:
    """跨 Island 语义关联与去重 Agent。

    属性：
        DEDUP_THRESHOLD  — cosine similarity 超过此值视为重复，默认 0.85
        FAMILY_THRESHOLD — 层次聚类距离阈值，默认 0.60
        MAX_MERGE_CANDIDATES — 最多建议合并数，默认 3
    """

    DEDUP_THRESHOLD: float = THRESHOLDS.synthesis_dedup_threshold
    FAMILY_THRESHOLD: float = THRESHOLDS.synthesis_family_threshold
    MAX_MERGE_CANDIDATES: int = 3

    def __init__(self, vectorizer: str = "tfidf") -> None:
        """
        Args:
            vectorizer: "tfidf"（默认，无外部依赖）或 "sentence-transformers"
                        本实现只支持 "tfidf"；传入其他值时退回 tfidf 并记录警告。
        """
        if vectorizer != "tfidf":
            logger.warning(
                "[SynthesisAgent] vectorizer=%r 暂不支持，退回 tfidf", vectorizer
            )
        self.vectorizer = "tfidf"

    # ─────────────────────────────────────────────────────────
    # 公开接口
    # ─────────────────────────────────────────────────────────

    async def synthesize(
        self,
        notes: list[FactorResearchNote],
    ) -> SynthesisResult:
        """对给定的 research notes 执行去重、聚类、merge 建议。

        <= 1 个输入时直接返回，不执行任何分析。
        任何子步骤抛出异常时记录警告，并在可能的范围内继续。
        """
        if len(notes) <= 1:
            return SynthesisResult(
                filtered_notes=list(notes),
                removed_notes=[],
                insights=[],
                families={},
                merge_candidates=[],
            )

        try:
            vectors = self._vectorize(notes)
        except Exception as exc:
            logger.warning("[SynthesisAgent] 向量化失败，跳过 synthesis: %s", exc)
            return SynthesisResult(
                filtered_notes=list(notes),
                removed_notes=[],
                insights=[],
                families={},
                merge_candidates=[],
            )

        # Step 2: 去重
        try:
            filtered, removed_ids, dedup_insights = self._deduplicate(notes, vectors)
        except Exception as exc:
            logger.warning("[SynthesisAgent] 去重失败，跳过: %s", exc)
            filtered, removed_ids, dedup_insights = list(notes), [], []

        # 去重后重新对 filtered 向量化（保持 vectors 与 filtered 对齐）
        try:
            if removed_ids:
                filtered_vectors = self._vectorize(filtered)
            else:
                filtered_vectors = vectors
        except Exception as exc:
            logger.warning("[SynthesisAgent] 去重后再向量化失败: %s", exc)
            filtered_vectors = vectors[: len(filtered)]

        # Step 3: 聚类成 families
        try:
            families, family_insights = self._cluster_families(
                filtered, filtered_vectors
            )
        except Exception as exc:
            logger.warning("[SynthesisAgent] family 聚类失败，跳过: %s", exc)
            families, family_insights = {}, []

        # Step 4: 跨 island merge 建议
        try:
            merge_candidates = self._suggest_merges(filtered, filtered_vectors)
        except Exception as exc:
            logger.warning("[SynthesisAgent] merge 建议失败，跳过: %s", exc)
            merge_candidates = []

        return SynthesisResult(
            filtered_notes=filtered,
            removed_notes=removed_ids,
            insights=dedup_insights + family_insights,
            families=families,
            merge_candidates=merge_candidates,
        )

    # ─────────────────────────────────────────────────────────
    # 内部步骤
    # ─────────────────────────────────────────────────────────

    def _vectorize(self, notes: list[FactorResearchNote]):
        """TF-IDF 向量化，返回稀疏矩阵（shape: n_notes × vocab）。"""
        from sklearn.feature_extraction.text import TfidfVectorizer

        docs = [
            " ".join(
                [
                    note.hypothesis or "",
                    note.economic_intuition or "",
                    note.proposed_formula or "",
                ]
            )
            for note in notes
        ]
        vec = TfidfVectorizer(
            analyzer="char_wb",   # 字符 n-gram，对中文友好
            ngram_range=(2, 4),
            min_df=1,
            sublinear_tf=True,
        )
        return vec.fit_transform(docs)

    def _deduplicate(
        self,
        notes: list[FactorResearchNote],
        vectors,
    ) -> tuple[list[FactorResearchNote], list[str], list[SynthesisInsight]]:
        """cosine similarity > DEDUP_THRESHOLD 的 pair，保留公式更复杂（更长）的一个。"""
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        sim_matrix = cosine_similarity(vectors)
        removed_ids: set[str] = set()
        insights: list[SynthesisInsight] = []

        for i in range(len(notes)):
            if notes[i].note_id in removed_ids:
                continue
            for j in range(i + 1, len(notes)):
                if notes[j].note_id in removed_ids:
                    continue
                if sim_matrix[i][j] > self.DEDUP_THRESHOLD:
                    # 保留公式更复杂的（启发式：更长的公式通常更有信息量）
                    if len(notes[i].proposed_formula) >= len(notes[j].proposed_formula):
                        keep, drop = i, j
                    else:
                        keep, drop = j, i

                    removed_ids.add(notes[drop].note_id)
                    insights.append(
                        SynthesisInsight(
                            island_a=notes[keep].island,
                            island_b=notes[drop].island,
                            note_id_a=notes[keep].note_id,
                            note_id_b=notes[drop].note_id,
                            relationship="duplicate",
                            combined_hypothesis=None,
                            priority="low",
                        )
                    )

        filtered = [n for n in notes if n.note_id not in removed_ids]
        return filtered, list(removed_ids), insights

    def _cluster_families(
        self,
        notes: list[FactorResearchNote],
        vectors,
    ) -> tuple[dict[str, list[str]], list[SynthesisInsight]]:
        """层次聚类（average linkage），distance threshold = 1 - FAMILY_THRESHOLD。

        少于 3 个 notes 时跳过聚类，返回空结果。
        """
        if len(notes) < 3:
            return {}, []

        from scipy.cluster.hierarchy import fcluster, linkage
        from scipy.spatial.distance import squareform
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        sim_matrix = cosine_similarity(vectors).astype(float)
        dist_matrix = 1.0 - sim_matrix

        # 确保对称性 + 对角线为 0，防止浮点误差
        n = len(notes)
        for i in range(n):
            dist_matrix[i][i] = 0.0
            for j in range(i + 1, n):
                avg = max(0.0, (dist_matrix[i][j] + dist_matrix[j][i]) / 2.0)
                dist_matrix[i][j] = avg
                dist_matrix[j][i] = avg

        condensed = squareform(dist_matrix)
        linkage_matrix = linkage(condensed, method="average")
        labels = fcluster(
            linkage_matrix,
            t=1.0 - self.FAMILY_THRESHOLD,
            criterion="distance",
        )

        # label → note_id 列表
        raw_families: dict[str, list[str]] = {}
        for note, label in zip(notes, labels):
            key = f"family_{label}"
            raw_families.setdefault(key, []).append(note.note_id)

        # 只保留 size > 1 的 family
        families = {k: v for k, v in raw_families.items() if len(v) > 1}

        # 每个 family 中相邻 pair 生成 insight
        insights: list[SynthesisInsight] = []
        for family_label, note_ids in families.items():
            for id_a, id_b in zip(note_ids, note_ids[1:]):
                insights.append(
                    SynthesisInsight(
                        island_a=self._get_island(notes, id_a),
                        island_b=self._get_island(notes, id_b),
                        note_id_a=id_a,
                        note_id_b=id_b,
                        relationship="family",
                        combined_hypothesis=None,
                        priority="medium",
                    )
                )

        return families, insights

    def _suggest_merges(
        self,
        notes: list[FactorResearchNote],
        vectors,
    ) -> list[SynthesisInsight]:
        """在跨 island 的相似但不重复的 pair 上提出合并建议（限制 MAX_MERGE_CANDIDATES）。

        相似区间：0.50 < sim < DEDUP_THRESHOLD（既相似又不构成重复）
        """
        from sklearn.metrics.pairwise import cosine_similarity

        sim_matrix = cosine_similarity(vectors)
        candidates: list[tuple[int, int, float]] = []

        for i in range(len(notes)):
            for j in range(i + 1, len(notes)):
                if notes[i].island == notes[j].island:
                    continue
                sim = float(sim_matrix[i][j])
                if THRESHOLDS.synthesis_family_similarity_min < sim < self.DEDUP_THRESHOLD:
                    candidates.append((i, j, sim))

        # 取 top-K（按相似度降序）
        candidates.sort(key=lambda x: x[2], reverse=True)
        candidates = candidates[: self.MAX_MERGE_CANDIDATES]

        merge_insights: list[SynthesisInsight] = []
        for i, j, sim in candidates:
            merge_insights.append(
                SynthesisInsight(
                    island_a=notes[i].island,
                    island_b=notes[j].island,
                    note_id_a=notes[i].note_id,
                    note_id_b=notes[j].note_id,
                    relationship="complement",
                    combined_hypothesis=None,  # LLM 填充（Phase 2.2 后续迭代）
                    priority="high" if sim > THRESHOLDS.synthesis_high_priority_threshold else "medium",
                )
            )

        return merge_insights

    # ─────────────────────────────────────────────────────────
    # 工具方法
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _get_island(notes: list[FactorResearchNote], note_id: str) -> str:
        """根据 note_id 查找 island 名称；找不到时返回 'unknown'。"""
        for note in notes:
            if note.note_id == note_id:
                return note.island
        return "unknown"
