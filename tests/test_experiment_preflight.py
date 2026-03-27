from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _load_preflight_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "experiment_preflight.py"
    module_name = "experiment_preflight_test_module"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_load_profile_parses_minimal_schema(tmp_path: Path):
    module = _load_preflight_module()
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "doctor_mode": "core",
                "single_island": "momentum",
                "preflight_evolve_rounds": 2,
                "long_run_rounds": 20,
                "require_reset_clean": False,
                "qlib_data_dir": "data/qlib_bin",
                "report_every_n_rounds": 5,
                "max_rounds_env_override_allowed": True,
                "profile_kind": "controlled_run",
                "target_islands": ["momentum", "northbound"],
                "target_subspaces": ["factor_algebra", "cross_market"],
                "market_context_mode": "live",
                "market_context_path": "data/market_context_cache/default.json",
                "persistence_mode": "full",
                "namespace": "controlled_run",
                "stage1_enrichment_enabled": False,
                "run_single": True,
                "run_preflight_evolve": True,
                "stage2_total_quota_override": 3,
                "stage2_requested_note_count_override": 1,
            }
        ),
        encoding="utf-8",
    )

    profile = module.load_profile(profile_path)
    assert profile.profile_kind == "controlled_run"
    assert profile.single_island == "momentum"
    assert profile.target_islands == ["momentum", "northbound"]
    assert profile.target_subspaces == ["factor_algebra", "cross_market"]
    assert profile.market_context_mode == "live"
    assert profile.persistence_mode == "full"
    assert profile.stage1_enrichment_enabled is False
    assert profile.preflight_evolve_rounds == 2
    assert profile.stage2_total_quota_override == 3
    assert profile.stage2_requested_note_count_override == 1


def test_load_profile_missing_key_raises(tmp_path: Path):
    module = _load_preflight_module()
    profile_path = tmp_path / "broken.json"
    profile_path.write_text(
        json.dumps(
            {
                "doctor_mode": "core",
                "single_island": "momentum",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Missing profile keys"):
        module.load_profile(profile_path)


def test_run_preflight_blocks_when_env_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_preflight_module()
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("QLIB_DATA_DIR", raising=False)
    profile = module.ExperimentProfile(
        doctor_mode="core",
        single_island="momentum",
        preflight_evolve_rounds=2,
        long_run_rounds=20,
        require_reset_clean=False,
        qlib_data_dir=str(tmp_path / "qlib_bin_missing"),
        report_every_n_rounds=5,
        max_rounds_env_override_allowed=True,
    )

    called = {"doctor": False}

    def fake_doctor(mode, env):
        called["doctor"] = True
        return 0

    result = module.run_preflight(
        profile,
        profile_path="dummy.json",
        project_root=tmp_path,
        env={},
        doctor_runner=fake_doctor,
    )
    assert not result.ok
    assert not called["doctor"]
    assert any("QLIB_DATA_DIR not found" in err for err in result.blocking_errors)
    assert any("TUSHARE_TOKEN missing" in err for err in result.blocking_errors)
    assert result.qlib_data_dir_source == "profile"
    assert result.tushare_token_source == "unset"


def test_run_preflight_propagates_doctor_failure(tmp_path: Path):
    module = _load_preflight_module()
    qlib_dir = tmp_path / "qlib_bin"
    qlib_dir.mkdir(parents=True, exist_ok=True)
    profile = module.ExperimentProfile(
        doctor_mode="core",
        single_island="momentum",
        preflight_evolve_rounds=2,
        long_run_rounds=20,
        require_reset_clean=False,
        qlib_data_dir=str(qlib_dir),
        report_every_n_rounds=5,
        max_rounds_env_override_allowed=True,
    )

    result = module.run_preflight(
        profile,
        profile_path="dummy.json",
        project_root=tmp_path,
        env={"TUSHARE_TOKEN": "token"},
        doctor_runner=lambda mode, env: 7,
    )
    assert not result.ok
    assert result.doctor_exit_code == 7
    assert any("doctor --mode core failed (exit=7)" in err for err in result.blocking_errors)
    assert result.qlib_data_dir_source == "profile"
    assert result.tushare_token_source == "process_env"


def test_run_preflight_passes_with_structured_success(tmp_path: Path):
    module = _load_preflight_module()
    qlib_dir = tmp_path / "qlib_bin"
    qlib_dir.mkdir(parents=True, exist_ok=True)
    profile = module.ExperimentProfile(
        doctor_mode="core",
        single_island="momentum",
        preflight_evolve_rounds=2,
        long_run_rounds=20,
        require_reset_clean=False,
        qlib_data_dir=str(qlib_dir),
        report_every_n_rounds=5,
        max_rounds_env_override_allowed=True,
    )

    result = module.run_preflight(
        profile,
        profile_path="dummy.json",
        project_root=tmp_path,
        env={"TUSHARE_TOKEN": "token"},
        doctor_runner=lambda mode, env: 0,
    )
    assert result.ok
    assert result.blocking_errors == []
    assert result.doctor_exit_code == 0
    assert result.qlib_data_dir_source == "profile"
    assert result.tushare_token_source == "process_env"


def test_preflight_print_text_includes_runtime_truth_and_next_steps(capsys: pytest.CaptureFixture[str]):
    module = _load_preflight_module()
    result = module.PreflightResult(
        ok=False,
        profile_path="config/experiments/fast_feedback.json",
        doctor_mode="fast_feedback",
        qlib_data_dir="/tmp/qlib",
        qlib_data_dir_source="process_env",
        tushare_token_source="unset",
        doctor_exit_code=3,
        blocking_errors=["doctor failed"],
        blocking_issues=[
            {
                "kind": "doctor",
                "message": "doctor --mode fast_feedback failed (exit=3)",
                "next_step": "Fix doctor blocking checks before starting the experiment.",
            }
        ],
        warnings=["fast_feedback writes are isolated from the formal runtime surfaces."],
        runtime_truth={
            "profile_kind": "fast_feedback",
            "persistence_mode": "artifact_only",
            "market_context_mode": "frozen",
            "target_islands": ["momentum"],
            "target_subspaces": ["factor_algebra"],
            "planned_phases": ["doctor", "single"],
            "stage2_total_quota_override": 2,
            "stage2_requested_note_count_override": 1,
            "write_scope": "artifact_only_scratch",
            "formal_writes_allowed": False,
            "state_store_path": "/tmp/state.sqlite",
            "market_context_path": "/tmp/context.json",
        },
    )

    module._print_text(result)
    captured = capsys.readouterr().out

    assert "[Preflight] planned_phases: doctor, single" in captured
    assert "[Preflight] stage2_total_quota_override: 2" in captured
    assert "[Preflight] stage2_requested_note_count_override: 1" in captured
    assert "[Preflight] formal_writes_allowed: False" in captured
    assert "[Preflight] market_context_path: /tmp/context.json" in captured
    assert "[Preflight] blocking_issues:" in captured
    assert "[doctor] doctor --mode fast_feedback failed (exit=3)" in captured
    assert "next_step: Fix doctor blocking checks before starting the experiment." in captured


def test_run_preflight_prefers_env_qlib_data_dir_override(tmp_path: Path):
    module = _load_preflight_module()
    qlib_dir = tmp_path / "qlib_from_env"
    qlib_dir.mkdir(parents=True, exist_ok=True)
    profile = module.ExperimentProfile(
        doctor_mode="core",
        single_island="momentum",
        preflight_evolve_rounds=2,
        long_run_rounds=20,
        require_reset_clean=False,
        qlib_data_dir="data/qlib_bin_missing_in_profile",
        report_every_n_rounds=5,
        max_rounds_env_override_allowed=True,
    )

    seen = {}

    def fake_doctor(mode, env):
        seen["qlib"] = env.get("QLIB_DATA_DIR")
        return 0

    result = module.run_preflight(
        profile,
        profile_path="dummy.json",
        project_root=tmp_path,
        env={"TUSHARE_TOKEN": "token", "QLIB_DATA_DIR": str(qlib_dir)},
        doctor_runner=fake_doctor,
    )
    assert result.ok
    assert result.qlib_data_dir == str(qlib_dir)
    assert seen["qlib"] == str(qlib_dir)
    assert result.qlib_data_dir_source == "process_env"


def test_run_preflight_require_reset_clean_honors_project_root(tmp_path: Path, monkeypatch):
    module = _load_preflight_module()
    qlib_dir = tmp_path / "qlib_bin"
    qlib_dir.mkdir(parents=True, exist_ok=True)
    traces_dir = tmp_path / "data" / "artifacts"
    traces_dir.mkdir(parents=True, exist_ok=True)
    (traces_dir / "trace.txt").write_text("x", encoding="utf-8")

    # Ensure the check is not accidentally tied to module-load reset targets.
    monkeypatch.setattr(module, "RESET_TARGETS", ())

    profile = module.ExperimentProfile(
        doctor_mode="core",
        single_island="momentum",
        preflight_evolve_rounds=2,
        long_run_rounds=20,
        require_reset_clean=True,
        qlib_data_dir=str(qlib_dir),
        report_every_n_rounds=5,
        max_rounds_env_override_allowed=True,
    )

    result = module.run_preflight(
        profile,
        profile_path="dummy.json",
        project_root=tmp_path,
        env={"TUSHARE_TOKEN": "token"},
        doctor_runner=lambda mode, env: 0,
    )
    assert not result.ok
    assert any("require_reset_clean=true" in err for err in result.blocking_errors)
    assert result.tushare_token_source == "process_env"


def test_run_preflight_user_runtime_env_beats_repo_env_and_reports_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load_preflight_module()
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("QLIB_DATA_DIR", raising=False)

    qlib_runtime = tmp_path / "qlib_runtime"
    qlib_runtime.mkdir(parents=True, exist_ok=True)
    qlib_repo = tmp_path / "qlib_repo"
    qlib_repo.mkdir(parents=True, exist_ok=True)

    runtime_env_path = tmp_path / "runtime.env"
    runtime_env_path.write_text(
        f"TUSHARE_TOKEN=runtime-token\nQLIB_DATA_DIR={qlib_runtime}\n",
        encoding="utf-8",
    )

    repo_env_path = tmp_path / ".env"
    repo_env_path.write_text(
        f"TUSHARE_TOKEN=repo-token\nQLIB_DATA_DIR={qlib_repo}\n",
        encoding="utf-8",
    )

    profile = module.ExperimentProfile(
        doctor_mode="core",
        single_island="momentum",
        preflight_evolve_rounds=2,
        long_run_rounds=20,
        require_reset_clean=False,
        qlib_data_dir="data/qlib_bin_in_profile",
        report_every_n_rounds=5,
        max_rounds_env_override_allowed=True,
    )

    observed_env: dict[str, str] = {}

    def fake_doctor(mode, env):
        observed_env["TUSHARE_TOKEN"] = env.get("TUSHARE_TOKEN", "")
        observed_env["QLIB_DATA_DIR"] = env.get("QLIB_DATA_DIR", "")
        return 0

    result = module.run_preflight(
        profile,
        profile_path="dummy.json",
        project_root=tmp_path,
        env={},
        doctor_runner=fake_doctor,
        runtime_env_path=runtime_env_path,
        repo_env_path=repo_env_path,
    )

    assert result.ok
    assert result.tushare_token_source == "user_runtime_env"
    assert result.qlib_data_dir_source == "user_runtime_env"
    assert result.qlib_data_dir == str(qlib_runtime)
    assert observed_env["TUSHARE_TOKEN"] == "runtime-token"
    assert observed_env["QLIB_DATA_DIR"] == str(qlib_runtime)


def test_run_preflight_fast_feedback_frozen_context_skips_tushare_and_reports_runtime_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load_preflight_module()
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

    qlib_dir = tmp_path / "qlib_bin"
    qlib_dir.mkdir(parents=True, exist_ok=True)
    context_path = tmp_path / "frozen_context.json"
    context_path.write_text(
        json.dumps(
            {
                "date": "2026-03-24",
                "northbound": None,
                "macro_signals": [],
                "hot_themes": ["AI算力"],
                "historical_insights": [],
                "suggested_islands": ["momentum"],
                "market_regime": "range_bound",
                "raw_summary": "frozen context",
            }
        ),
        encoding="utf-8",
    )

    profile = module.ExperimentProfile(
        doctor_mode="fast_feedback",
        single_island="momentum",
        preflight_evolve_rounds=1,
        long_run_rounds=5,
        require_reset_clean=False,
        qlib_data_dir=str(qlib_dir),
        report_every_n_rounds=1,
        max_rounds_env_override_allowed=False,
        profile_kind="fast_feedback",
        target_islands=["momentum"],
        target_subspaces=["factor_algebra"],
        market_context_mode="frozen",
        market_context_path=str(context_path),
        persistence_mode="artifact_only",
        namespace="fast_feedback",
        stage1_enrichment_enabled=False,
        run_single=True,
        run_preflight_evolve=False,
    )

    called = {}

    def fake_doctor(mode, env):
        called["mode"] = mode
        called["tushare"] = env.get("TUSHARE_TOKEN")
        called["context_mode"] = env.get("PIXIU_STAGE1_CONTEXT_MODE")
        called["target_subspaces"] = env.get("PIXIU_TARGET_SUBSPACES")
        called["state_store_path"] = env.get("PIXIU_STATE_STORE_PATH")
        return 0

    result = module.run_preflight(
        profile,
        profile_path="fast_feedback.json",
        project_root=tmp_path,
        env={},
        doctor_runner=fake_doctor,
    )

    assert result.ok
    assert result.blocking_errors == []
    assert result.tushare_token_source == "unset"
    assert called["mode"] == "fast_feedback"
    assert called["tushare"] is None
    assert called["context_mode"] == "frozen"
    assert called["target_subspaces"] == "factor_algebra"
    assert "runtime_namespaces/fast_feedback" in called["state_store_path"]
    assert result.runtime_truth["profile_kind"] == "fast_feedback"
    assert result.runtime_truth["market_context_mode"] == "frozen"
    assert result.runtime_truth["persistence_mode"] == "artifact_only"
    assert result.runtime_truth["target_islands"] == ["momentum"]
    assert result.runtime_truth["target_subspaces"] == ["factor_algebra"]
    assert result.runtime_truth["planned_phases"] == ["doctor", "single"]
    assert result.runtime_truth["formal_writes_allowed"] is False


def test_run_preflight_blocks_when_frozen_context_path_missing(tmp_path: Path):
    module = _load_preflight_module()
    qlib_dir = tmp_path / "qlib_bin"
    qlib_dir.mkdir(parents=True, exist_ok=True)

    profile = module.ExperimentProfile(
        doctor_mode="fast_feedback",
        single_island="momentum",
        preflight_evolve_rounds=1,
        long_run_rounds=5,
        require_reset_clean=False,
        qlib_data_dir=str(qlib_dir),
        report_every_n_rounds=1,
        max_rounds_env_override_allowed=False,
        profile_kind="fast_feedback",
        target_islands=["momentum"],
        target_subspaces=["factor_algebra"],
        market_context_mode="frozen",
        market_context_path=str(tmp_path / "missing_context.json"),
        persistence_mode="artifact_only",
        namespace="fast_feedback",
        stage1_enrichment_enabled=False,
        run_single=True,
        run_preflight_evolve=False,
    )

    result = module.run_preflight(
        profile,
        profile_path="fast_feedback.json",
        project_root=tmp_path,
        env={},
        doctor_runner=lambda mode, env: 0,
    )

    assert not result.ok
    assert any("market context file not found" in err for err in result.blocking_errors)


def test_load_profile_rejects_fast_feedback_full_persistence(tmp_path: Path):
    module = _load_preflight_module()
    profile_path = tmp_path / "invalid_fast_feedback.json"
    profile_path.write_text(
        json.dumps(
            {
                "doctor_mode": "fast_feedback",
                "single_island": "momentum",
                "preflight_evolve_rounds": 1,
                "long_run_rounds": 5,
                "require_reset_clean": False,
                "qlib_data_dir": "data/qlib_bin",
                "report_every_n_rounds": 1,
                "max_rounds_env_override_allowed": False,
                "profile_kind": "fast_feedback",
                "target_islands": ["momentum"],
                "target_subspaces": ["factor_algebra"],
                "market_context_mode": "frozen",
                "market_context_path": "config/experiments/context/fast_feedback_momentum.json",
                "persistence_mode": "full",
                "namespace": "fast_feedback",
                "stage1_enrichment_enabled": False,
                "run_single": True,
                "run_preflight_evolve": False,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="fast_feedback profile cannot use persistence_mode=full"):
        module.load_profile(profile_path)


def test_load_profile_rejects_stage2_quota_below_subspace_minimum(tmp_path: Path):
    module = _load_preflight_module()
    profile_path = tmp_path / "invalid_fast_feedback_quota.json"
    profile_path.write_text(
        json.dumps(
            {
                "doctor_mode": "fast_feedback",
                "single_island": "momentum",
                "preflight_evolve_rounds": 1,
                "long_run_rounds": 5,
                "require_reset_clean": False,
                "qlib_data_dir": "data/qlib_bin",
                "report_every_n_rounds": 1,
                "max_rounds_env_override_allowed": False,
                "human_gate_auto_action": "approve",
                "profile_kind": "fast_feedback",
                "target_islands": ["momentum"],
                "target_subspaces": ["factor_algebra"],
                "market_context_mode": "frozen",
                "market_context_path": "config/experiments/context/fast_feedback_momentum.json",
                "persistence_mode": "artifact_only",
                "namespace": "fast_feedback",
                "stage1_enrichment_enabled": False,
                "run_single": True,
                "run_preflight_evolve": False,
                "stage2_total_quota_override": 1,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="stage2_total_quota_override must be >= minimum quota required by target_subspaces",
    ):
        module.load_profile(profile_path)
