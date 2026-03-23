from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

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


@dataclass(frozen=True)
class _FakePreflightResult:
    ok: bool
    blocking_errors: list[str]


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
        preflight_fn=lambda *args, **kwargs: _FakePreflightResult(ok=False, blocking_errors=["doctor failed"]),
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
        preflight_fn=lambda *args, **kwargs: _FakePreflightResult(ok=True, blocking_errors=[]),
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
        preflight_fn=lambda *args, **kwargs: _FakePreflightResult(ok=True, blocking_errors=[]),
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
        preflight_fn=lambda *args, **kwargs: _FakePreflightResult(ok=True, blocking_errors=[]),
        run_single_fn=fake_single,
        run_evolve_fn=fake_evolve,
        status_runner=lambda mode: (True, f"{mode} ok"),
    )

    assert result.ok
    assert result.long_run_executed
    assert calls == [("single", "momentum"), ("evolve", 2), ("evolve", 7)]
