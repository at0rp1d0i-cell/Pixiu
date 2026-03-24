from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.control_plane import state_store as state_store_module
from src.core import experiment_logger as experiment_logger_module
from src.core.orchestrator import config as orchestrator_config
from src.core.orchestrator import runtime as orchestrator_runtime
from src.execution import coder as coder_module
from src.factor_pool import pool as factor_pool_module
from src.factor_pool import storage as factor_pool_storage

pytestmark = pytest.mark.unit


def test_factor_pool_singleton_rebuilds_when_env_db_path_changes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    calls: list[str] = []

    def fake_factor_pool(db_path: str | None = None):
        calls.append(str(db_path))
        return SimpleNamespace(db_path=str(db_path))

    monkeypatch.setattr(factor_pool_module, "FactorPool", fake_factor_pool)
    monkeypatch.setattr(factor_pool_module, "_pool_instance", None)
    monkeypatch.setattr(factor_pool_module, "_pool_instance_path", None)

    first_path = tmp_path / "pool_a"
    second_path = tmp_path / "pool_b"

    monkeypatch.setenv("PIXIU_FACTOR_POOL_DB_PATH", str(first_path))
    first = factor_pool_module.get_factor_pool()

    monkeypatch.setenv("PIXIU_FACTOR_POOL_DB_PATH", str(second_path))
    second = factor_pool_module.get_factor_pool()

    assert first.db_path == str(first_path)
    assert second.db_path == str(second_path)
    assert calls == [str(first_path), str(second_path)]


def test_state_store_singleton_rebuilds_when_env_path_changes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    calls: list[Path] = []

    class FakeStateStore:
        def __init__(self, db_path=None):
            path = Path(db_path)
            calls.append(path)
            self.db_path = path

    monkeypatch.setattr(state_store_module, "StateStore", FakeStateStore)
    monkeypatch.setattr(state_store_module, "_state_store", None)
    monkeypatch.setattr(state_store_module, "_state_store_path", None)

    first_path = tmp_path / "state_a.sqlite"
    second_path = tmp_path / "state_b.sqlite"

    monkeypatch.setenv("PIXIU_STATE_STORE_PATH", str(first_path))
    first = state_store_module.get_state_store()

    monkeypatch.setenv("PIXIU_STATE_STORE_PATH", str(second_path))
    second = state_store_module.get_state_store()

    assert first.db_path == first_path
    assert second.db_path == second_path
    assert calls == [first_path, second_path]


def test_experiment_logger_singleton_rebuilds_when_runs_dir_changes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(experiment_logger_module, "_logger_instance", None)
    monkeypatch.setattr(experiment_logger_module, "_logger_instance_key", None)

    monkeypatch.setenv("PIXIU_RUN_ID", "run-a")
    monkeypatch.setenv("PIXIU_EXPERIMENT_RUNS_DIR", str(tmp_path / "runs_a"))
    first = experiment_logger_module.get_experiment_logger()

    monkeypatch.setenv("PIXIU_EXPERIMENT_RUNS_DIR", str(tmp_path / "runs_b"))
    second = experiment_logger_module.get_experiment_logger()

    assert first is not second
    assert first._base_dir == (tmp_path / "runs_a" / "run-a")
    assert second._base_dir == (tmp_path / "runs_b" / "run-a")


def test_experiment_logger_manual_override_wins_when_key_is_stale(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(experiment_logger_module, "_logger_instance", None)
    monkeypatch.setattr(experiment_logger_module, "_logger_instance_key", None)

    monkeypatch.setenv("PIXIU_RUN_ID", "run-a")
    monkeypatch.setenv("PIXIU_EXPERIMENT_RUNS_DIR", str(tmp_path / "runs_a"))
    _ = experiment_logger_module.get_experiment_logger()

    manual = experiment_logger_module.ExperimentLogger(
        run_id="manual-run",
        runs_dir=tmp_path / "manual_runs",
    )
    experiment_logger_module._logger_instance = manual

    monkeypatch.setenv("PIXIU_RUN_ID", "run-b")
    monkeypatch.setenv("PIXIU_EXPERIMENT_RUNS_DIR", str(tmp_path / "runs_b"))
    resolved = experiment_logger_module.get_experiment_logger()

    assert resolved is manual
    assert experiment_logger_module._logger_instance_key == (
        "manual-run",
        str(tmp_path / "manual_runs"),
    )


def test_path_resolvers_follow_env_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("PIXIU_FACTOR_POOL_DB_PATH", str(tmp_path / "factor_pool"))
    monkeypatch.setenv("PIXIU_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("PIXIU_EXPERIMENT_RUNS_DIR", str(tmp_path / "experiment_runs"))

    assert factor_pool_storage.resolve_default_db_path() == str(tmp_path / "factor_pool")
    assert coder_module.resolve_artifacts_dir() == tmp_path / "artifacts"
    assert experiment_logger_module.resolve_experiment_runs_dir() == tmp_path / "experiment_runs"


def test_runtime_scheduler_uses_configured_active_islands(monkeypatch: pytest.MonkeyPatch):
    fake_pool = SimpleNamespace(get_island_leaderboard=lambda: [])
    original_active_islands = list(orchestrator_config.ACTIVE_ISLANDS)

    monkeypatch.setattr(orchestrator_runtime, "get_factor_pool", lambda: fake_pool)
    orchestrator_runtime.reset_runtime_state()
    orchestrator_config.ACTIVE_ISLANDS = ["momentum"]

    try:
        scheduler = orchestrator_runtime.get_scheduler()
        assert scheduler.get_active_islands() == ["momentum"]
    finally:
        orchestrator_runtime.reset_runtime_state()
        orchestrator_config.ACTIVE_ISLANDS = original_active_islands
