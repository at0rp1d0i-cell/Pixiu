"""Pixiu: FactorPool facade."""
import logging
from typing import Optional

from src.schemas.backtest import BacktestReport
from src.schemas.judgment import CriticVerdict, RiskAuditReport
from src.schemas.research_note import FactorResearchNote
from src.schemas.factor_pool import FactorPoolRecord
from src.schemas.failure_constraint import FailureConstraint, FailureMode
from . import storage as _storage
from .constraint_store import (
    increment_checked as _increment_checked,
    increment_violation as _increment_violation,
    parse_constraint_results_get as _parse_constraint_results_get,
    parse_constraint_results_query as _parse_constraint_results_query,
    query_constraints as _query_constraints,
    query_constraints_by_formula as _query_constraints_by_formula,
    register_constraint as _register_constraint,
)
from .factor_writer import (
    archive_research_note as _archive_research_note,
    write_factor as _write_factor,
    write_factor_v2 as _write_factor_v2,
)
from .queries import (
    get_common_failure_modes as _get_common_failure_modes,
    get_island_best_factors as _get_island_best_factors,
    get_island_factors as _get_island_factors,
    get_island_leaderboard as _get_island_leaderboard,
    get_passed_factors as _get_passed_factors,
    get_stats as _get_stats,
    get_top_factors as _get_top_factors,
)
from .similarity import get_similar_failures as _get_similar_failures


logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = _storage.DEFAULT_DB_PATH
COLLECTION_NAME = _storage.COLLECTION_NAME
CONSTRAINT_COLLECTION_NAME = _storage.CONSTRAINT_COLLECTION_NAME
EXPLORATION_COLLECTION_NAME = _storage.EXPLORATION_COLLECTION_NAME
NOTE_COLLECTION_NAME = _storage.NOTE_COLLECTION_NAME
_InMemoryClient = _storage._InMemoryClient
FactorPoolStorage = _storage.FactorPoolStorage
chromadb = _storage.chromadb
build_default_chroma_embedding_function = _storage.build_default_chroma_embedding_function
resolve_default_db_path = _storage.resolve_default_db_path


def build_factor_pool_storage(db_path: str | None = None) -> FactorPoolStorage:
    return _storage.build_factor_pool_storage(
        db_path=db_path or resolve_default_db_path(),
        persistent_client_factory=chromadb.PersistentClient,
        embedding_function_factory=build_default_chroma_embedding_function,
    )


class FactorPool:
    """因子实验历史库，支持 Island 分组和向量相似检索。"""

    CONSTRAINT_COLLECTION = CONSTRAINT_COLLECTION_NAME

    def __init__(self, db_path: str | None = None):
        resolved_db_path = db_path or resolve_default_db_path()
        storage: FactorPoolStorage = build_factor_pool_storage(resolved_db_path)
        self._client = storage.client
        self._storage_mode = storage.storage_mode
        self._embedding_function = storage.embedding_function
        self._collection = storage.factor_collection
        self._notes_collection = storage.notes_collection
        self._explorations_collection = storage.explorations_collection
        self._constraints_collection = storage.constraints_collection
        self._db_path = resolved_db_path

    def get_island_best_factors(self, island_name: str, top_k: int = 3) -> list[dict]:
        return _get_island_best_factors(self._collection, island_name, top_k)

    def get_similar_failures(self, formula: str, top_k: int = 3) -> list[dict]:
        return _get_similar_failures(self._collection, formula, top_k)

    def get_island_leaderboard(self) -> list[dict]:
        return _get_island_leaderboard(self._collection)

    def get_stats(self) -> dict:
        return _get_stats(self._collection)

    def register_factor(
        self,
        report: BacktestReport,
        verdict: CriticVerdict,
        risk_report: RiskAuditReport,
        hypothesis: str = "",
        note: Optional[FactorResearchNote] = None,
    ) -> None:
        _write_factor(self._collection, report, verdict, risk_report, hypothesis=hypothesis, note=note)

    def get_passed_factors(
        self,
        island: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        return _get_passed_factors(self._collection, island=island, limit=limit)

    def get_top_factors(self, limit: int = 20) -> list[dict]:
        return _get_top_factors(self._collection, limit=limit)

    def register_factor_v2(self, record: FactorPoolRecord) -> None:
        _write_factor_v2(self._collection, record)

    def get_common_failure_modes(
        self,
        island: str,
        limit: int = 10,
    ) -> list[dict]:
        return _get_common_failure_modes(self._collection, island=island, limit=limit)

    def archive_research_note(self, note: FactorResearchNote) -> None:
        _archive_research_note(self._notes_collection, note)

    def get_island_factors(
        self,
        island: str,
        limit: int = 50,
    ) -> list[dict]:
        return _get_island_factors(self._collection, island=island, limit=limit)

    def register_constraint(self, constraint: FailureConstraint) -> None:
        _register_constraint(self._constraints_collection, constraint)

    def query_constraints(
        self,
        island: Optional[str] = None,
        failure_mode: Optional[FailureMode] = None,
        limit: int = 10,
    ) -> list[FailureConstraint]:
        return _query_constraints(self._constraints_collection, island=island, failure_mode=failure_mode, limit=limit)

    def query_constraints_by_formula(
        self,
        formula: str,
        limit: int = 5,
    ) -> list[FailureConstraint]:
        return _query_constraints_by_formula(self._constraints_collection, formula=formula, limit=limit)

    def increment_checked(self, constraint_id: str) -> None:
        _increment_checked(self._constraints_collection, constraint_id)

    def increment_violation(self, constraint_id: str) -> None:
        _increment_violation(self._constraints_collection, constraint_id)

    def _parse_constraint_results_get(self, results: dict) -> list[FailureConstraint]:
        return _parse_constraint_results_get(results)

    def _parse_constraint_results_query(self, results: dict) -> list[FailureConstraint]:
        return _parse_constraint_results_query(results)


# 模块级单例（跨调用复用连接）
_pool_instance: Optional[FactorPool] = None
_pool_instance_path: str | None = None


def get_factor_pool(db_path: str | None = None) -> FactorPool:
    """获取 FactorPool 单例。"""
    global _pool_instance, _pool_instance_path
    resolved_db_path = db_path or resolve_default_db_path()
    if _pool_instance is None or _pool_instance_path != resolved_db_path:
        _pool_instance = FactorPool(db_path=resolved_db_path)
        _pool_instance_path = resolved_db_path
    return _pool_instance


def reset_factor_pool() -> None:
    global _pool_instance, _pool_instance_path
    _pool_instance = None
    _pool_instance_path = None
