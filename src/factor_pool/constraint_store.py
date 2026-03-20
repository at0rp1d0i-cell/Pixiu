from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Optional

from src.schemas.failure_constraint import FailureConstraint, FailureMode

logger = logging.getLogger(__name__)


def register_constraint(collection, constraint: FailureConstraint) -> None:
    collection.upsert(
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


def query_constraints(collection, island: Optional[str] = None, failure_mode: Optional[FailureMode] = None, limit: int = 10) -> list[FailureConstraint]:
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
        results = collection.get(
            where=where_clauses if where_clauses else None,
            include=["metadatas", "documents"],
        )
        return parse_constraint_results_get(results)[:limit]
    except Exception as exc:
        logger.warning("[FactorPool] query_constraints failed: %s", exc)
        return []


def query_constraints_by_formula(collection, formula: str, limit: int = 5) -> list[FailureConstraint]:
    try:
        count = collection.count()
        if count == 0:
            return []
        results = collection.query(
            query_texts=[formula],
            n_results=min(limit, count),
            include=["metadatas", "documents"],
        )
        return parse_constraint_results_query(results)
    except Exception as exc:
        logger.warning("[FactorPool] query_constraints_by_formula failed: %s", exc)
        return []


def increment_checked(collection, constraint_id: str) -> None:
    try:
        result = collection.get(ids=[constraint_id], include=["metadatas", "documents"])
        if not result["ids"]:
            return
        meta = result["metadatas"][0]
        doc = result["documents"][0] if result.get("documents") else meta.get("constraint_rule", "")
        updated_meta = {**meta, "times_checked": meta.get("times_checked", 0) + 1}
        collection.upsert(ids=[constraint_id], documents=[doc], metadatas=[updated_meta])
    except Exception as exc:
        logger.warning("[FactorPool] increment_checked failed: %s", exc)


def increment_violation(collection, constraint_id: str) -> None:
    try:
        result = collection.get(ids=[constraint_id], include=["metadatas", "documents"])
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
        collection.upsert(ids=[constraint_id], documents=[doc], metadatas=[updated_meta])
    except Exception as exc:
        logger.warning("[FactorPool] increment_violation failed: %s", exc)


def parse_constraint_results_get(results: dict) -> list[FailureConstraint]:
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
        except Exception as exc:
            logger.warning("[FactorPool] parse_constraint_results_get skip %s: %s", cid, exc)
    return constraints


def parse_constraint_results_query(results: dict) -> list[FailureConstraint]:
    ids_outer = results.get("ids", [[]])
    metas_outer = results.get("metadatas", [[]])
    docs_outer = results.get("documents", [[]])
    ids = ids_outer[0] if ids_outer else []
    metadatas = metas_outer[0] if metas_outer else []
    documents = docs_outer[0] if docs_outer else []
    flat = {"ids": ids, "metadatas": metadatas, "documents": documents}
    return parse_constraint_results_get(flat)
