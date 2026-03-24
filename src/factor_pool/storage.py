"""FactorPool storage/bootstrap helpers."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

import chromadb
from chromadb.config import Settings

from .chroma_runtime import build_default_chroma_embedding_function


logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "factor_pool_db")
)


def resolve_default_db_path() -> str:
    return os.getenv("PIXIU_FACTOR_POOL_DB_PATH", DEFAULT_DB_PATH)

COLLECTION_NAME = "factor_experiments"
NOTE_COLLECTION_NAME = "research_notes"
EXPLORATION_COLLECTION_NAME = "exploration_results"
CONSTRAINT_COLLECTION_NAME = "failure_constraints"


def _match_where(metadata: dict, where: Optional[dict]) -> bool:
    if not where:
        return True
    if "$and" in where:
        return all(_match_where(metadata, clause) for clause in where["$and"])
    return all(metadata.get(key) == value for key, value in where.items())


class _InMemoryCollection:
    def __init__(self, name: str):
        self.name = name
        self._embedding_function = None
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

    def get_or_create_collection(self, name: str, **kwargs):
        if name not in self._collections:
            self._collections[name] = _InMemoryCollection(name)
        return self._collections[name]


@dataclass(slots=True)
class FactorPoolStorage:
    client: object
    storage_mode: str
    embedding_function: object
    factor_collection: object
    notes_collection: object
    explorations_collection: object
    constraints_collection: object


def _attach_embedding_function(collection: object, embedding_function: object) -> None:
    if hasattr(collection, "_embedding_function"):
        collection._embedding_function = embedding_function


def _build_client(
    db_path: str,
    persistent_client_factory=None,
) -> tuple[object, str]:
    os.makedirs(db_path, exist_ok=True)
    if persistent_client_factory is None:
        persistent_client_factory = chromadb.PersistentClient
    try:
        client = persistent_client_factory(
            path=db_path,
            settings=Settings(anonymized_telemetry=False),
        )
        return client, "persistent"
    except Exception as exc:
        logger.warning(
            "[FactorPool] PersistentClient 初始化失败，降级为 in-memory client: %s",
            exc,
        )
        return _InMemoryClient(), "in_memory"


def build_factor_pool_storage(
    db_path: str | None = None,
    *,
    persistent_client_factory=None,
    embedding_function_factory=None,
) -> FactorPoolStorage:
    resolved_db_path = db_path or resolve_default_db_path()
    if persistent_client_factory is None:
        persistent_client_factory = chromadb.PersistentClient
    if embedding_function_factory is None:
        embedding_function_factory = build_default_chroma_embedding_function
    client, storage_mode = _build_client(
        resolved_db_path,
        persistent_client_factory=persistent_client_factory,
    )
    embedding_function = embedding_function_factory()

    factor_collection = client.get_or_create_collection(name=COLLECTION_NAME)
    _attach_embedding_function(factor_collection, embedding_function)

    notes_collection = client.get_or_create_collection(name=NOTE_COLLECTION_NAME)
    _attach_embedding_function(notes_collection, embedding_function)

    explorations_collection = client.get_or_create_collection(
        name=EXPLORATION_COLLECTION_NAME,
    )
    _attach_embedding_function(explorations_collection, embedding_function)

    constraints_collection = client.get_or_create_collection(name=CONSTRAINT_COLLECTION_NAME)
    _attach_embedding_function(constraints_collection, embedding_function)

    logger.info("[FactorPool] 初始化完成，数据库路径：%s，模式：%s", resolved_db_path, storage_mode)
    logger.info("[FactorPool] 当前存储因子数量：%d", factor_collection.count())

    return FactorPoolStorage(
        client=client,
        storage_mode=storage_mode,
        embedding_function=embedding_function,
        factor_collection=factor_collection,
        notes_collection=notes_collection,
        explorations_collection=explorations_collection,
        constraints_collection=constraints_collection,
    )
