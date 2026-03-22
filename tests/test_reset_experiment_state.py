from __future__ import annotations

import importlib.util
import sys
from io import StringIO
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def _load_script_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "reset_experiment_state.py"
    module_name = "reset_experiment_state_test"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _seed_runtime_state(project_root: Path) -> None:
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "control_plane_state.db").write_text("state", encoding="utf-8")
    experiment_runs = data_dir / "experiment_runs"
    experiment_runs.mkdir()
    (experiment_runs / "round_001.json").write_text("{}", encoding="utf-8")
    artifacts = data_dir / "artifacts"
    artifacts.mkdir()
    (artifacts / "trace.log").write_text("artifact", encoding="utf-8")
    factor_pool = data_dir / "factor_pool_db"
    factor_pool.mkdir()
    (factor_pool / "pool.sqlite").write_text("factor", encoding="utf-8")


def test_build_targets_excludes_factor_pool_by_default():
    module = _load_script_module()

    targets = module.build_targets(project_root=Path("/tmp/pixiu-reset-test"))

    assert [target.relative_path for target in targets] == [
        "data/control_plane_state.db",
        "data/experiment_runs/",
        "data/artifacts/",
    ]


def test_build_targets_can_include_factor_pool():
    module = _load_script_module()

    targets = module.build_targets(
        project_root=Path("/tmp/pixiu-reset-test"),
        include_factor_pool=True,
    )

    assert [target.relative_path for target in targets] == [
        "data/control_plane_state.db",
        "data/experiment_runs/",
        "data/artifacts/",
        "data/factor_pool_db/",
    ]


def test_run_reset_dry_run_keeps_all_targets(tmp_path: Path):
    module = _load_script_module()
    _seed_runtime_state(tmp_path)
    output = StringIO()

    exit_code = module.run_reset(project_root=tmp_path, dry_run=True, out=output)

    assert exit_code == 0
    assert (tmp_path / "data" / "control_plane_state.db").exists()
    assert (tmp_path / "data" / "experiment_runs").exists()
    assert (tmp_path / "data" / "artifacts").exists()
    assert (tmp_path / "data" / "factor_pool_db").exists()
    text = output.getvalue()
    assert "Mode: dry-run" in text
    assert "Dry run only. No files were deleted." in text
    assert "data/factor_pool_db/" in text
    assert "Preserved by default" in text


def test_run_reset_deletes_default_targets_only(tmp_path: Path):
    module = _load_script_module()
    _seed_runtime_state(tmp_path)
    output = StringIO()

    exit_code = module.run_reset(project_root=tmp_path, out=output)

    assert exit_code == 0
    assert not (tmp_path / "data" / "control_plane_state.db").exists()
    assert not (tmp_path / "data" / "experiment_runs").exists()
    assert not (tmp_path / "data" / "artifacts").exists()
    assert (tmp_path / "data" / "factor_pool_db").exists()
    text = output.getvalue()
    assert "Applying reset:" in text
    assert "data/factor_pool_db/" in text
    assert "Preserved by default" in text


def test_run_reset_can_delete_factor_pool_when_requested(tmp_path: Path):
    module = _load_script_module()
    _seed_runtime_state(tmp_path)
    output = StringIO()

    exit_code = module.run_reset(
        project_root=tmp_path,
        include_factor_pool=True,
        out=output,
    )

    assert exit_code == 0
    assert not (tmp_path / "data" / "control_plane_state.db").exists()
    assert not (tmp_path / "data" / "experiment_runs").exists()
    assert not (tmp_path / "data" / "artifacts").exists()
    assert not (tmp_path / "data" / "factor_pool_db").exists()
    text = output.getvalue()
    assert "Preserved by default" not in text
    assert "data/factor_pool_db/: deleted-dir" in text
