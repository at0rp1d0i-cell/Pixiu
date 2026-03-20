"""Unit tests for FactorPool storage/bootstrap wiring."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.factor_pool import pool as factor_pool_mod
from src.factor_pool import storage

pytestmark = pytest.mark.unit


class _StubCollection:
    def __init__(self, name: str, count_value: int = 3):
        self.name = name
        self._embedding_function = None
        self._count_value = count_value

    def count(self) -> int:
        return self._count_value


class _StubClient:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.collections: dict[str, _StubCollection] = {}

    def get_or_create_collection(self, name: str, **kwargs):
        self.calls.append((name, dict(kwargs)))
        if name not in self.collections:
            self.collections[name] = _StubCollection(name)
        return self.collections[name]


def test_build_factor_pool_storage_wires_persistent_collections(monkeypatch, tmp_path):
    client = _StubClient()
    embedding_function = object()

    monkeypatch.setattr(storage.chromadb, "PersistentClient", lambda **kwargs: client)
    monkeypatch.setattr(
        storage,
        "build_default_chroma_embedding_function",
        lambda: embedding_function,
    )

    bundle = storage.build_factor_pool_storage(str(tmp_path / "factor_pool_db"))

    assert bundle.storage_mode == "persistent"
    assert bundle.client is client
    assert client.calls == [
        (storage.COLLECTION_NAME, {}),
        (storage.NOTE_COLLECTION_NAME, {}),
        (storage.EXPLORATION_COLLECTION_NAME, {}),
        (storage.CONSTRAINT_COLLECTION_NAME, {}),
    ]
    assert bundle.factor_collection._embedding_function is embedding_function
    assert bundle.notes_collection._embedding_function is embedding_function
    assert bundle.explorations_collection._embedding_function is embedding_function
    assert bundle.constraints_collection._embedding_function is embedding_function


def test_build_factor_pool_storage_falls_back_to_in_memory_client(monkeypatch, tmp_path):
    embedding_function = object()

    def _raise_persistent_client(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(storage.chromadb, "PersistentClient", _raise_persistent_client)
    monkeypatch.setattr(
        storage,
        "build_default_chroma_embedding_function",
        lambda: embedding_function,
    )

    bundle = storage.build_factor_pool_storage(str(tmp_path / "factor_pool_db"))

    assert bundle.storage_mode == "in_memory"
    assert isinstance(bundle.client, storage._InMemoryClient)
    assert sorted(bundle.client._collections) == sorted(
        [
            storage.COLLECTION_NAME,
            storage.NOTE_COLLECTION_NAME,
            storage.EXPLORATION_COLLECTION_NAME,
            storage.CONSTRAINT_COLLECTION_NAME,
        ]
    )
    assert bundle.factor_collection._embedding_function is embedding_function


def test_factor_pool_constructor_uses_storage_bundle(monkeypatch):
    fake_bundle = SimpleNamespace(
        client=object(),
        storage_mode="in_memory",
        embedding_function=object(),
        factor_collection=object(),
        notes_collection=object(),
        explorations_collection=object(),
        constraints_collection=object(),
    )

    monkeypatch.setattr(factor_pool_mod, "build_factor_pool_storage", lambda db_path: fake_bundle)

    pool = factor_pool_mod.FactorPool(db_path="/tmp/factor_pool_storage_test")

    assert pool._client is fake_bundle.client
    assert pool._storage_mode == "in_memory"
    assert pool._embedding_function is fake_bundle.embedding_function
    assert pool._collection is fake_bundle.factor_collection
    assert pool._notes_collection is fake_bundle.notes_collection
    assert pool._explorations_collection is fake_bundle.explorations_collection
    assert pool._constraints_collection is fake_bundle.constraints_collection
