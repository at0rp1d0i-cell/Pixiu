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
            }
        ),
        encoding="utf-8",
    )

    profile = module.load_profile(profile_path)
    assert profile.single_island == "momentum"
    assert profile.preflight_evolve_rounds == 2


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


def test_run_preflight_blocks_when_env_missing(tmp_path: Path):
    module = _load_preflight_module()
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
