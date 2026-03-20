from __future__ import annotations

import logging
from collections import Counter
from typing import Optional

from src.factor_pool.islands import ISLANDS

logger = logging.getLogger(__name__)


def get_island_best_factors(collection, island_name: str, top_k: int = 3) -> list[dict]:
    results = collection.get(where={"island": island_name}, include=["metadatas", "documents"])
    if not results["ids"]:
        return []
    items = list(zip(results["metadatas"], results["documents"], results["ids"]))
    items.sort(key=lambda x: x[0].get("sharpe", 0.0), reverse=True)
    return [{**meta, "document": doc, "id": fid} for meta, doc, fid in items[:top_k]]


def get_island_leaderboard(collection) -> list[dict]:
    all_results = collection.get(include=["metadatas"])
    if not all_results["ids"]:
        return []

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
    leaderboard.sort(key=lambda x: x["best_sharpe"], reverse=True)
    return leaderboard


def get_stats(collection) -> dict:
    count = collection.count()
    if count == 0:
        return {"total_factors": 0, "beats_baseline_count": 0}
    all_results = collection.get(include=["metadatas"])
    sharpes = [m.get("sharpe", 0.0) for m in all_results["metadatas"]]
    beats = sum(1 for m in all_results["metadatas"] if m.get("beats_baseline", False))
    return {
        "total_factors": count,
        "beats_baseline_count": beats,
        "global_best_sharpe": max(sharpes) if sharpes else 0.0,
        "global_avg_sharpe": sum(sharpes) / len(sharpes) if sharpes else 0.0,
    }


def get_passed_factors(collection, island: Optional[str] = None, limit: int = 20) -> list[dict]:
    where: dict = {"passed": True}
    if island:
        where = {"$and": [{"passed": True}, {"island": island}]}
    try:
        results = collection.query(
            query_texts=[""],
            n_results=limit,
            where=where,
            include=["metadatas", "documents"],
        )
        if not results["ids"] or not results["ids"][0]:
            return []
        return [{**meta, "document": doc} for meta, doc in zip(results["metadatas"][0], results["documents"][0])]
    except Exception as exc:
        logger.warning("[FactorPool] get_passed_factors failed: %s", exc)
        return []


def get_top_factors(collection, limit: int = 20) -> list[dict]:
    try:
        results = collection.query(
            query_texts=[""],
            n_results=min(limit * 3, max(collection.count(), 1)),
            where={"passed": True},
            include=["metadatas", "documents"],
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
    except Exception as exc:
        logger.warning("[FactorPool] get_top_factors failed: %s", exc)
        return []


def get_island_factors(collection, island: str, limit: int = 50) -> list[dict]:
    try:
        results = collection.get(where={"island": island}, include=["metadatas", "documents"])
        if not results["ids"]:
            return []
        return [{**meta, "formula": meta.get("formula", ""), "factor_id": fid}
                for meta, fid in zip(results["metadatas"], results["ids"])][:limit]
    except Exception as exc:
        logger.warning("[FactorPool] get_island_factors failed: %s", exc)
        return []


def get_common_failure_modes(collection, island: str, limit: int = 10) -> list[dict]:
    try:
        results = collection.query(
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
    except Exception as exc:
        logger.warning("[FactorPool] get_common_failure_modes failed: %s", exc)
        return []
