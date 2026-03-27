from __future__ import annotations

import importlib.util
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def _load_harness_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "run_experiment_harness.py"
    module_name = "experiment_harness_test_module"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class _FakeProfile:
    doctor_mode: str = "core"
    single_island: str = "momentum"
    preflight_evolve_rounds: int = 2
    long_run_rounds: int = 20
    require_reset_clean: bool = False
    qlib_data_dir: str = "data/qlib_bin"
    report_every_n_rounds: int = 5
    max_rounds_env_override_allowed: bool = True
    human_gate_auto_action: str = "approve"
    profile_kind: str = "controlled_run"
    target_islands: list[str] | None = None
    target_subspaces: list[str] | None = None
    market_context_mode: str = "live"
    market_context_path: str = "data/market_context_cache/default.json"
    persistence_mode: str = "full"
    namespace: str = "controlled_run"
    stage1_enrichment_enabled: bool = False
    run_single: bool = True
    run_preflight_evolve: bool = True
    stage2_total_quota_override: int | None = None
    stage2_requested_note_count_override: int | None = None


@dataclass(frozen=True)
class _FakePreflightResult:
    ok: bool
    blocking_errors: list[str]
    runtime_truth: dict[str, object] | None = None


@pytest.mark.asyncio
async def test_harness_stops_on_preflight_blocking_failure():
    module = _load_harness_module()
    calls: list[str] = []

    async def fake_single(_island: str) -> None:
        calls.append("single")

    async def fake_evolve(_rounds: int) -> None:
        calls.append("evolve")

    result = await module.run_harness(
        _FakeProfile(),
        profile_path="dummy.json",
        long_run=False,
        preflight_fn=lambda *args, **kwargs: _FakePreflightResult(
            ok=False,
            blocking_errors=["doctor failed"],
            runtime_truth={"planned_phases": ["doctor", "single", "evolve_preflight"]},
        ),
        run_single_fn=fake_single,
        run_evolve_fn=fake_evolve,
        status_runner=lambda mode: (True, "ok"),
    )

    assert not result.ok
    assert calls == []
    assert result.phases[0].name == "preflight"
    assert not result.phases[0].ok


@pytest.mark.asyncio
async def test_harness_stops_when_single_stage_fails_status_check():
    module = _load_harness_module()
    calls: list[str] = []

    async def fake_single(_island: str) -> None:
        calls.append("single")

    async def fake_evolve(_rounds: int) -> None:
        calls.append("evolve")

    status_responses = [(False, "single failed")]

    def status_runner(_mode: str):
        return status_responses.pop(0)

    result = await module.run_harness(
        _FakeProfile(),
        profile_path="dummy.json",
        long_run=False,
        preflight_fn=lambda *args, **kwargs: _FakePreflightResult(
            ok=True,
            blocking_errors=[],
            runtime_truth={"planned_phases": ["doctor", "single", "evolve_preflight"]},
        ),
        run_single_fn=fake_single,
        run_evolve_fn=fake_evolve,
        status_runner=status_runner,
    )

    assert not result.ok
    assert calls == ["single"]
    assert [item.name for item in result.phases] == ["preflight", "single"]


@pytest.mark.asyncio
async def test_harness_runs_fixed_order_without_long_run():
    module = _load_harness_module()
    calls: list[tuple[str, object]] = []

    async def fake_single(island: str) -> None:
        calls.append(("single", island))

    async def fake_evolve(rounds: int) -> None:
        calls.append(("evolve", rounds))

    def status_runner(mode: str):
        return True, f"{mode} ok"

    result = await module.run_harness(
        _FakeProfile(preflight_evolve_rounds=2, long_run_rounds=50),
        profile_path="dummy.json",
        long_run=False,
        preflight_fn=lambda *args, **kwargs: _FakePreflightResult(
            ok=True,
            blocking_errors=[],
            runtime_truth={"planned_phases": ["doctor", "single", "evolve_preflight"]},
        ),
        run_single_fn=fake_single,
        run_evolve_fn=fake_evolve,
        status_runner=status_runner,
    )

    assert result.ok
    assert calls == [("single", "momentum"), ("evolve", 2)]
    assert not result.long_run_executed


@pytest.mark.asyncio
async def test_harness_long_run_requires_flag_and_respects_env_override(monkeypatch: pytest.MonkeyPatch):
    module = _load_harness_module()
    calls: list[tuple[str, object]] = []
    monkeypatch.setenv("MAX_ROUNDS", "7")

    async def fake_single(island: str) -> None:
        calls.append(("single", island))

    async def fake_evolve(rounds: int) -> None:
        calls.append(("evolve", rounds))

    result = await module.run_harness(
        _FakeProfile(preflight_evolve_rounds=2, long_run_rounds=50, max_rounds_env_override_allowed=True),
        profile_path="dummy.json",
        long_run=True,
        preflight_fn=lambda *args, **kwargs: _FakePreflightResult(
            ok=True,
            blocking_errors=[],
            runtime_truth={"planned_phases": ["doctor", "single", "evolve_preflight", "evolve_long"]},
        ),
        run_single_fn=fake_single,
        run_evolve_fn=fake_evolve,
        status_runner=lambda mode: (True, f"{mode} ok"),
    )

    assert result.ok
    assert result.long_run_executed
    assert calls == [("single", "momentum"), ("evolve", 2), ("evolve", 7)]


@pytest.mark.asyncio
async def test_harness_applies_resolved_env_truth_before_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    module = _load_harness_module()
    qlib_dir = tmp_path / "qlib_runtime"
    qlib_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("QLIB_DATA_DIR", raising=False)
    monkeypatch.delenv("REPORT_EVERY_N_ROUNDS", raising=False)
    monkeypatch.delenv("PIXIU_HUMAN_GATE_AUTO_ACTION", raising=False)

    def fake_resolve_profile_env_truth(profile, **kwargs):
        return SimpleNamespace(
            merged_env={
                "TUSHARE_TOKEN": "runtime-token",
                "QLIB_DATA_DIR": str(qlib_dir),
            },
            sources={
                "TUSHARE_TOKEN": "user_runtime_env",
                "QLIB_DATA_DIR": "user_runtime_env",
            },
        )

    observed: dict[str, str] = {}

    async def fake_single(_island: str) -> None:
        observed["TUSHARE_TOKEN"] = os.environ.get("TUSHARE_TOKEN", "")
        observed["QLIB_DATA_DIR"] = os.environ.get("QLIB_DATA_DIR", "")
        observed["REPORT_EVERY_N_ROUNDS"] = os.environ.get("REPORT_EVERY_N_ROUNDS", "")
        observed["PIXIU_HUMAN_GATE_AUTO_ACTION"] = os.environ.get("PIXIU_HUMAN_GATE_AUTO_ACTION", "")
        observed["ACTIVE_ISLANDS"] = os.environ.get("ACTIVE_ISLANDS", "")
        observed["PIXIU_TARGET_SUBSPACES"] = os.environ.get("PIXIU_TARGET_SUBSPACES", "")
        observed["PIXIU_STAGE1_CONTEXT_MODE"] = os.environ.get("PIXIU_STAGE1_CONTEXT_MODE", "")
        observed["PIXIU_STAGE2_TOTAL_QUOTA"] = os.environ.get("PIXIU_STAGE2_TOTAL_QUOTA", "")
        observed["PIXIU_STAGE2_REQUESTED_NOTE_COUNT"] = os.environ.get("PIXIU_STAGE2_REQUESTED_NOTE_COUNT", "")
        observed["PIXIU_EXPERIMENT_PROFILE_KIND"] = os.environ.get("PIXIU_EXPERIMENT_PROFILE_KIND", "")
        observed["PIXIU_EXPERIMENT_PERSISTENCE_MODE"] = os.environ.get("PIXIU_EXPERIMENT_PERSISTENCE_MODE", "")
        observed["PIXIU_STATE_STORE_PATH"] = os.environ.get("PIXIU_STATE_STORE_PATH", "")
        from src.core.orchestrator import config as orchestrator_config
        observed["config_active_islands"] = ",".join(orchestrator_config.ACTIVE_ISLANDS)
        observed["config_report_every"] = str(orchestrator_config.REPORT_EVERY_N_ROUNDS)
        observed["config_reports_dir"] = str(orchestrator_config.REPORTS_DIR)

    async def fake_evolve(_rounds: int) -> None:
        return None

    monkeypatch.setattr(module, "resolve_profile_env_truth", fake_resolve_profile_env_truth)

    result = await module.run_harness(
        _FakeProfile(
            report_every_n_rounds=9,
            profile_kind="fast_feedback",
            target_islands=["momentum"],
            target_subspaces=["factor_algebra"],
            market_context_mode="frozen",
            market_context_path=str(tmp_path / "frozen_context.json"),
            persistence_mode="artifact_only",
            namespace="fast_feedback",
            stage1_enrichment_enabled=False,
            stage2_total_quota_override=2,
            stage2_requested_note_count_override=1,
            run_preflight_evolve=False,
        ),
        profile_path="dummy.json",
        long_run=False,
        preflight_fn=lambda *args, **kwargs: _FakePreflightResult(
            ok=True,
            blocking_errors=[],
            runtime_truth={"planned_phases": ["doctor", "single"], "profile_kind": "fast_feedback"},
        ),
        run_single_fn=fake_single,
        run_evolve_fn=fake_evolve,
        status_runner=lambda mode: (True, f"{mode} ok"),
    )

    assert result.ok
    assert observed["TUSHARE_TOKEN"] == "runtime-token"
    assert observed["QLIB_DATA_DIR"] == str(qlib_dir)
    assert observed["REPORT_EVERY_N_ROUNDS"] == "9"
    assert observed["PIXIU_HUMAN_GATE_AUTO_ACTION"] == "approve"
    assert observed["ACTIVE_ISLANDS"] == "momentum"
    assert observed["PIXIU_TARGET_SUBSPACES"] == "factor_algebra"
    assert observed["PIXIU_STAGE1_CONTEXT_MODE"] == "frozen"
    assert observed["PIXIU_STAGE2_TOTAL_QUOTA"] == "2"
    assert observed["PIXIU_STAGE2_REQUESTED_NOTE_COUNT"] == "1"
    assert observed["PIXIU_EXPERIMENT_PROFILE_KIND"] == "fast_feedback"
    assert observed["PIXIU_EXPERIMENT_PERSISTENCE_MODE"] == "artifact_only"
    assert "runtime_namespaces/fast_feedback" in observed["PIXIU_STATE_STORE_PATH"]
    assert module._runtime.peek_scheduler() is None
    assert observed["config_active_islands"] == "momentum"
    assert observed["config_report_every"] == "9"
    assert "runtime_namespaces/fast_feedback/reports" in observed["config_reports_dir"]
    assert result.runtime_truth["profile_kind"] == "fast_feedback"


@pytest.mark.asyncio
async def test_harness_restores_runtime_env_after_return(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    module = _load_harness_module()
    qlib_dir = tmp_path / "qlib_runtime"
    qlib_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ACTIVE_ISLANDS", "momentum,northbound")
    monkeypatch.setenv("PIXIU_TARGET_SUBSPACES", "cross_market")
    monkeypatch.setenv("PIXIU_STAGE2_TOTAL_QUOTA", "9")
    monkeypatch.setenv("PIXIU_EXPERIMENT_RUNS_DIR", str(tmp_path / "runs_before"))

    def fake_resolve_profile_env_truth(profile, **kwargs):
        return SimpleNamespace(
            merged_env={
                "TUSHARE_TOKEN": "runtime-token",
                "QLIB_DATA_DIR": str(qlib_dir),
            },
            sources={
                "TUSHARE_TOKEN": "user_runtime_env",
                "QLIB_DATA_DIR": "user_runtime_env",
            },
        )

    monkeypatch.setattr(module, "resolve_profile_env_truth", fake_resolve_profile_env_truth)

    from src.core.orchestrator import config as orchestrator_config

    original_active = list(orchestrator_config.ACTIVE_ISLANDS)
    original_report_every = orchestrator_config.REPORT_EVERY_N_ROUNDS
    original_reports_dir = orchestrator_config.REPORTS_DIR

    async def fake_single(_island: str) -> None:
        return None

    async def fake_evolve(_rounds: int) -> None:
        return None

    result = await module.run_harness(
        _FakeProfile(
            profile_kind="fast_feedback",
            target_islands=["momentum"],
            target_subspaces=["factor_algebra"],
            market_context_mode="frozen",
            market_context_path=str(tmp_path / "frozen_context.json"),
            persistence_mode="artifact_only",
            namespace="fast_feedback",
            stage1_enrichment_enabled=False,
            stage2_total_quota_override=2,
            run_preflight_evolve=False,
        ),
        profile_path="dummy.json",
        long_run=False,
        preflight_fn=lambda *args, **kwargs: _FakePreflightResult(
            ok=True,
            blocking_errors=[],
            runtime_truth={"planned_phases": ["doctor", "single"], "profile_kind": "fast_feedback"},
        ),
        run_single_fn=fake_single,
        run_evolve_fn=fake_evolve,
        status_runner=lambda mode: (True, f"{mode} ok"),
    )

    assert result.ok
    assert os.environ["ACTIVE_ISLANDS"] == "momentum,northbound"
    assert os.environ["PIXIU_TARGET_SUBSPACES"] == "cross_market"
    assert os.environ["PIXIU_STAGE2_TOTAL_QUOTA"] == "9"
    assert os.environ["PIXIU_EXPERIMENT_RUNS_DIR"] == str(tmp_path / "runs_before")
    assert orchestrator_config.ACTIVE_ISLANDS == original_active
    assert orchestrator_config.REPORT_EVERY_N_ROUNDS == original_report_every
    assert orchestrator_config.REPORTS_DIR == original_reports_dir


@pytest.mark.asyncio
async def test_harness_fast_feedback_profile_can_skip_preflight_evolve():
    module = _load_harness_module()
    calls: list[tuple[str, object]] = []

    async def fake_single(island: str) -> None:
        calls.append(("single", island))

    async def fake_evolve(rounds: int) -> None:
        calls.append(("evolve", rounds))

    result = await module.run_harness(
        _FakeProfile(
            profile_kind="fast_feedback",
            target_islands=["momentum"],
            target_subspaces=["factor_algebra"],
            market_context_mode="frozen",
            persistence_mode="artifact_only",
            namespace="fast_feedback",
            run_preflight_evolve=False,
        ),
        profile_path="fast_feedback.json",
        long_run=False,
        preflight_fn=lambda *args, **kwargs: _FakePreflightResult(
            ok=True,
            blocking_errors=[],
            runtime_truth={"planned_phases": ["doctor", "single"], "profile_kind": "fast_feedback"},
        ),
        run_single_fn=fake_single,
        run_evolve_fn=fake_evolve,
        status_runner=lambda mode: (True, f"{mode} ok"),
    )

    assert result.ok
    assert calls == [("single", "momentum")]
    assert [phase.name for phase in result.phases] == ["preflight", "single"]


def test_harness_print_text_summary_includes_profile_policy_details(capsys: pytest.CaptureFixture[str]):
    module = _load_harness_module()
    result = module.HarnessResult(
        ok=False,
        profile_path="config/experiments/fast_feedback.json",
        long_run_requested=False,
        long_run_executed=False,
        phases=[module.PhaseResult(name="preflight", ok=False, detail="doctor failed")],
        runtime_truth={
            "profile_kind": "fast_feedback",
            "namespace": "fast_feedback",
            "persistence_mode": "artifact_only",
            "market_context_mode": "frozen",
            "planned_phases": ["doctor", "single"],
            "write_scope": "artifact_only_scratch",
        },
        failure_stage="preflight",
        next_step="Resolve doctor blocking checks.",
    )

    module._print_text_summary(result)
    captured = capsys.readouterr().out

    assert "[Harness] namespace: fast_feedback" in captured
    assert "[Harness] planned_phases: doctor, single" in captured
    assert "[Harness] write_scope: artifact_only_scratch" in captured
    assert "[Harness] next_step: Resolve doctor blocking checks." in captured


def test_default_status_runner_prefers_current_run_id_over_latest(monkeypatch: pytest.MonkeyPatch):
    module = _load_harness_module()
    current_run = SimpleNamespace(
        run_id="run-current",
        mode="single",
        status="completed",
        current_round=1,
        last_error=None,
    )
    latest_run = SimpleNamespace(
        run_id="run-latest",
        mode="evolve",
        status="running",
        current_round=99,
        last_error=None,
    )

    class FakeStore:
        def get_run(self, run_id: str):
            assert run_id == "run-current"
            return current_run

        def get_latest_run(self):
            return latest_run

    monkeypatch.setattr(module, "StateStore", lambda: FakeStore())
    monkeypatch.setattr(module._runtime, "get_current_run_id", lambda: "run-current")

    ok, detail = module._default_status_runner("single")

    assert ok
    assert "run_id=run-current" in detail


def test_experiment_logger_persists_subspace_aware_rejection_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from src.core.experiment_logger import ExperimentLogger
    from src.schemas.state import AgentState
    from src.schemas.research_note import FactorResearchNote
    from src.schemas.hypothesis import ExplorationSubspace

    note = FactorResearchNote(
        note_id="n1",
        island="momentum",
        iteration=1,
        hypothesis="h",
        economic_intuition="i",
        proposed_formula="Mean($close, 5)",
        risk_factors=[],
        market_context_date="2026-03-23",
        exploration_subspace=ExplorationSubspace.FACTOR_ALGEBRA,
    )
    state = AgentState(
        current_round=0,
        research_notes=[note],
        stage2_diagnostics={
            "generated_count": 2,
            "delivered_count": 1,
            "local_retry_count": 0,
            "rejection_counts_by_filter": {"validator": 1},
            "rejection_counts_by_filter_and_subspace": {"validator": {"factor_algebra": 1}},
            "sample_rejections": [
                {
                    "note_id": "n_bad",
                    "filter": "validator",
                    "reason": "bad",
                    "exploration_subspace": "factor_algebra",
                }
            ],
        },
        prefilter_diagnostics={
            "input_count": 1,
            "approved_count": 0,
            "rejection_counts_by_filter": {"alignment": 1},
            "rejection_counts_by_filter_and_subspace": {"alignment": {"factor_algebra": 1}},
            "sample_rejections": [
                {
                    "note_id": "n1",
                    "filter": "alignment",
                    "reason": "mismatch",
                    "exploration_subspace": "factor_algebra",
                }
            ],
        },
    )

    monkeypatch.setattr(
        "src.factor_pool.pool.get_factor_pool",
        lambda: SimpleNamespace(get_passed_factors=lambda limit=9999: []),
    )

    logger = ExperimentLogger(run_id="telemetry_test", runs_dir=tmp_path)
    logger.snapshot(0, state)

    payload = json.loads((tmp_path / "telemetry_test" / "round_000.json").read_text(encoding="utf-8"))
    assert payload["stage2"]["rejection_counts_by_filter_and_subspace"]["validator"]["factor_algebra"] == 1
    assert payload["stage2"]["sample_rejections"][0]["exploration_subspace"] == "factor_algebra"
    assert payload["prefilter"]["rejection_counts_by_filter_and_subspace"]["alignment"]["factor_algebra"] == 1
    assert payload["prefilter"]["sample_rejections"][0]["exploration_subspace"] == "factor_algebra"
