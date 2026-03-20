from __future__ import annotations

import logging

from src.schemas.thresholds import THRESHOLDS

logger = logging.getLogger(__name__)


def summarize_failure(meta: dict) -> str:
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
        reasons.append(f"ICIR={icir:.2f}（低于{THRESHOLDS.min_icir}）")
    if turnover != 0.0 and turnover > THRESHOLDS.max_turnover_rate:
        reasons.append(f"换手率={turnover:.4f}（高于{THRESHOLDS.max_turnover_rate}）")

    return "; ".join(reasons) if reasons else "质量不过关，但未命中具体阈值"


def get_similar_failures(collection, formula: str, top_k: int = 3) -> list[dict]:
    results = collection.query(
        query_texts=[formula],
        n_results=min(top_k * 3, max(collection.count(), 1)),
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
    items.sort(key=lambda x: x[2])
    return [
        {
            **meta,
            "document": doc,
            "similarity_distance": dist,
            "id": fid,
            "failure_reason": summarize_failure(meta),
        }
        for meta, doc, dist, fid in items[:top_k]
    ]
