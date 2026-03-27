#!/usr/bin/env python3
"""Fixed-order experiment harness for Pixiu."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Awaitable, Callable, Mapping

from src.control_plane.state_store import StateStore
from src.core.orchestrator import runtime as _runtime


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PREFLIGHT_PATH = Path(__file__).resolve().with_name("experiment_preflight.py")


def _load_preflight_module():
    spec = importlib.util.spec_from_file_location("pixiu_experiment_preflight", _PREFLIGHT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load preflight module: {_PREFLIGHT_PATH}")
    module = importlib.util.module_from_spec(spec)
    # Register module before execution so import-time decorators resolve __module__ correctly.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_PRE = _load_preflight_module()
DEFAULT_PROFILE_PATH = _PRE.DEFAULT_PROFILE_PATH
load_profile = _PRE.load_profile
run_preflight = _PRE.run_preflight
resolve_profile_env_truth = _PRE.resolve_profile_env_truth


@dataclass(frozen=True)
class PhaseResult:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class HarnessResult:
    ok: bool
    profile_path: str
    long_run_requested: bool
    long_run_executed: bool
    phases: list[PhaseResult]
    runtime_truth: dict[str, object]
    failure_stage: str | None = None
    next_step: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "profile_path": self.profile_path,
            "long_run_requested": self.long_run_requested,
            "long_run_executed": self.long_run_executed,
            "phases": [asdict(item) for item in self.phases],
            "runtime_truth": self.runtime_truth,
            "failure_stage": self.failure_stage,
            "next_step": self.next_step,
        }


StatusRunner = Callable[[str], tuple[bool, str]]
RunSingleRunner = Callable[[str], Awaitable[None]]
RunEvolveRunner = Callable[[int], Awaitable[None]]


async def _default_run_single(island: str) -> None:
    from src.core.orchestrator._entrypoints import run_single

    await run_single(island)


async def _default_run_evolve(rounds: int) -> None:
    from src.core.orchestrator._entrypoints import run_evolve

    await run_evolve(rounds=rounds)


def _default_status_runner(expected_mode: str) -> tuple[bool, str]:
    store = StateStore()
    run_id = _runtime.get_current_run_id()
    run = store.get_run(run_id) if run_id else store.get_latest_run()
    if run is None:
        return False, "No run record found after execution."
    if run.mode != expected_mode:
        return False, f"Unexpected run mode. expected={expected_mode} actual={run.mode}"
    if run.status not in {"completed", "stopped"}:
        return False, f"Run status is not successful: {run.status}"
    if run.last_error:
        return False, f"Run recorded last_error: {run.last_error}"
    return True, f"run_id={run.run_id} status={run.status} round={run.current_round}"


def _resolve_long_run_rounds(profile) -> int:
    rounds = int(profile.long_run_rounds)
    if profile.max_rounds_env_override_allowed:
        raw = os.getenv("MAX_ROUNDS")
        if raw:
            rounds = int(raw)
    return rounds


_MANAGED_RUNTIME_ENV_KEYS = (
    "TUSHARE_TOKEN",
    "QLIB_DATA_DIR",
    "ACTIVE_ISLANDS",
    "PIXIU_TARGET_SUBSPACES",
    "PIXIU_STAGE1_CONTEXT_MODE",
    "PIXIU_STAGE1_CONTEXT_PATH",
    "PIXIU_STAGE1_ENABLE_ENRICHMENT",
    "PIXIU_EXPERIMENT_PROFILE_KIND",
    "PIXIU_EXPERIMENT_PERSISTENCE_MODE",
    "PIXIU_EXPERIMENT_NAMESPACE",
    "PIXIU_STATE_STORE_PATH",
    "PIXIU_FACTOR_POOL_DB_PATH",
    "PIXIU_EXPERIMENT_RUNS_DIR",
    "PIXIU_ARTIFACTS_DIR",
    "PIXIU_REPORTS_DIR",
    "PIXIU_STAGE2_TOTAL_QUOTA",
    "PIXIU_STAGE2_REQUESTED_NOTE_COUNT",
    "REPORT_EVERY_N_ROUNDS",
    "PIXIU_HUMAN_GATE_AUTO_ACTION",
)


@dataclass(frozen=True)
class _RuntimeMutationBackup:
    managed_env: dict[str, str | None]
    active_islands: list[str]
    report_every_n_rounds: int
    reports_dir: Path


def _fallback_runtime_truth(profile) -> dict[str, object]:
    profile_kind = getattr(profile, "profile_kind", "controlled_run")
    persistence_mode = getattr(profile, "persistence_mode", "full")
    namespace = getattr(profile, "namespace", "") or profile_kind
    target_islands = list(getattr(profile, "target_islands", None) or [profile.single_island])
    target_subspaces = list(getattr(profile, "target_subspaces", None) or [])
    market_context_mode = getattr(profile, "market_context_mode", "live")
    market_context_path = getattr(profile, "market_context_path", "") or str(
        PROJECT_ROOT / "data" / "market_context_cache" / f"{profile.single_island}.json"
    )
    if persistence_mode == "full":
        data_root = PROJECT_ROOT / "data"
        formal_writes_allowed = True
    else:
        data_root = PROJECT_ROOT / "data" / "runtime_namespaces" / namespace
        formal_writes_allowed = False
    planned_phases = ["doctor"]
    if getattr(profile, "run_single", True):
        planned_phases.append("single")
    if getattr(profile, "run_preflight_evolve", True):
        planned_phases.append("evolve_preflight")
    return {
        "profile_kind": profile_kind,
        "persistence_mode": persistence_mode,
        "namespace": namespace,
        "target_islands": target_islands,
        "target_subspaces": target_subspaces,
        "market_context_mode": market_context_mode,
        "market_context_path": market_context_path,
        "stage1_enrichment_enabled": getattr(profile, "stage1_enrichment_enabled", True),
        "stage2_total_quota_override": getattr(profile, "stage2_total_quota_override", None),
        "stage2_requested_note_count_override": getattr(profile, "stage2_requested_note_count_override", None),
        "planned_phases": planned_phases,
        "formal_writes_allowed": formal_writes_allowed,
        "state_store_path": str(data_root / "control_plane_state.db"),
        "factor_pool_db_path": str(data_root / "factor_pool_db"),
        "experiment_runs_dir": str(data_root / "experiment_runs"),
        "artifacts_dir": str(data_root / "artifacts"),
        "reports_dir": str(data_root / "reports"),
    }


def _apply_runtime_env(
    profile,
    *,
    profile_path: str,
    env: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, object]]:
    env_truth = resolve_profile_env_truth(
        profile,
        project_root=PROJECT_ROOT,
        env=env,
        repo_env_path=PROJECT_ROOT / ".env",
        profile_path=profile_path,
    )
    merged = dict(env_truth.merged_env)
    runtime_truth = dict(getattr(env_truth, "runtime_truth", {}) or {})
    if not runtime_truth:
        runtime_truth = _fallback_runtime_truth(profile)

    merged.setdefault("ACTIVE_ISLANDS", ",".join(runtime_truth.get("target_islands", [])))
    merged.setdefault("PIXIU_TARGET_SUBSPACES", ",".join(runtime_truth.get("target_subspaces", [])))
    merged.setdefault("PIXIU_STAGE1_CONTEXT_MODE", str(runtime_truth.get("market_context_mode", "live")))
    merged.setdefault("PIXIU_STAGE1_CONTEXT_PATH", str(runtime_truth.get("market_context_path", "")))
    merged.setdefault(
        "PIXIU_STAGE1_ENABLE_ENRICHMENT",
        "1" if runtime_truth.get("stage1_enrichment_enabled", True) else "0",
    )
    merged.setdefault("PIXIU_EXPERIMENT_PROFILE_KIND", str(runtime_truth.get("profile_kind", "controlled_run")))
    merged.setdefault("PIXIU_EXPERIMENT_PERSISTENCE_MODE", str(runtime_truth.get("persistence_mode", "full")))
    merged.setdefault("PIXIU_EXPERIMENT_NAMESPACE", str(runtime_truth.get("namespace", "")))
    merged.setdefault("PIXIU_STATE_STORE_PATH", str(runtime_truth.get("state_store_path", "")))
    merged.setdefault("PIXIU_FACTOR_POOL_DB_PATH", str(runtime_truth.get("factor_pool_db_path", "")))
    merged.setdefault("PIXIU_EXPERIMENT_RUNS_DIR", str(runtime_truth.get("experiment_runs_dir", "")))
    merged.setdefault("PIXIU_ARTIFACTS_DIR", str(runtime_truth.get("artifacts_dir", "")))
    merged.setdefault("PIXIU_REPORTS_DIR", str(runtime_truth.get("reports_dir", "")))
    if runtime_truth.get("stage2_total_quota_override") is not None:
        merged.setdefault("PIXIU_STAGE2_TOTAL_QUOTA", str(runtime_truth["stage2_total_quota_override"]))
    if runtime_truth.get("stage2_requested_note_count_override") is not None:
        merged.setdefault(
            "PIXIU_STAGE2_REQUESTED_NOTE_COUNT",
            str(runtime_truth["stage2_requested_note_count_override"]),
        )
    merged.setdefault("REPORT_EVERY_N_ROUNDS", str(profile.report_every_n_rounds))
    merged.setdefault("PIXIU_HUMAN_GATE_AUTO_ACTION", str(profile.human_gate_auto_action))
    for key in _MANAGED_RUNTIME_ENV_KEYS:
        value = merged.get(key, "")
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)

    from src.core.orchestrator import config as orchestrator_config
    from src.control_plane.state_store import reset_state_store
    from src.core.experiment_logger import reset_experiment_logger
    from src.factor_pool.pool import reset_factor_pool

    target_islands = [str(item) for item in runtime_truth.get("target_islands", []) if str(item)]
    if target_islands:
        orchestrator_config.ACTIVE_ISLANDS = target_islands
    orchestrator_config.REPORT_EVERY_N_ROUNDS = int(profile.report_every_n_rounds)
    reports_dir = runtime_truth.get("reports_dir")
    if reports_dir:
        orchestrator_config.REPORTS_DIR = Path(str(reports_dir))

    reset_state_store()
    reset_experiment_logger()
    reset_factor_pool()
    _runtime.reset_runtime_state()
    return merged, runtime_truth


def _capture_runtime_mutation_backup() -> _RuntimeMutationBackup:
    from src.core.orchestrator import config as orchestrator_config

    return _RuntimeMutationBackup(
        managed_env={key: os.environ.get(key) for key in _MANAGED_RUNTIME_ENV_KEYS},
        active_islands=list(orchestrator_config.ACTIVE_ISLANDS),
        report_every_n_rounds=int(orchestrator_config.REPORT_EVERY_N_ROUNDS),
        reports_dir=Path(orchestrator_config.REPORTS_DIR),
    )


def _restore_runtime_env(backup: _RuntimeMutationBackup) -> None:
    from src.core.orchestrator import config as orchestrator_config
    from src.control_plane.state_store import reset_state_store
    from src.core.experiment_logger import reset_experiment_logger
    from src.factor_pool.pool import reset_factor_pool

    for key, value in backup.managed_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    orchestrator_config.ACTIVE_ISLANDS = list(backup.active_islands)
    orchestrator_config.REPORT_EVERY_N_ROUNDS = backup.report_every_n_rounds
    orchestrator_config.REPORTS_DIR = Path(backup.reports_dir)

    reset_state_store()
    reset_experiment_logger()
    reset_factor_pool()
    _runtime.reset_runtime_state()


async def run_harness(
    profile,
    *,
    profile_path: str,
    long_run: bool,
    env: Mapping[str, str] | None = None,
    preflight_fn=run_preflight,
    run_single_fn: RunSingleRunner = _default_run_single,
    run_evolve_fn: RunEvolveRunner = _default_run_evolve,
    status_runner: StatusRunner = _default_status_runner,
) -> HarnessResult:
    phases: list[PhaseResult] = []

    preflight = preflight_fn(profile, profile_path=profile_path, env=env)
    runtime_truth = dict(getattr(preflight, "runtime_truth", {}) or {})
    if preflight.ok:
        detail = "profile/env/doctor passed"
    else:
        detail = "; ".join(preflight.blocking_errors) if preflight.blocking_errors else "preflight failed"
    phases.append(PhaseResult(name="preflight", ok=preflight.ok, detail=detail))
    if not preflight.ok:
        return HarnessResult(
            ok=False,
            profile_path=str(profile_path),
            long_run_requested=long_run,
            long_run_executed=False,
            phases=phases,
            runtime_truth=runtime_truth,
            failure_stage="preflight",
            next_step="Resolve preflight blocking errors before starting the run.",
        )

    runtime_backup = _capture_runtime_mutation_backup()
    _, runtime_truth = _apply_runtime_env(profile, profile_path=profile_path, env=env)

    try:
        if profile.run_single:
            await run_single_fn(profile.single_island)
            single_ok, single_detail = status_runner("single")
            phases.append(PhaseResult(name="single", ok=single_ok, detail=single_detail))
            if not single_ok:
                return HarnessResult(
                    ok=False,
                    profile_path=str(profile_path),
                    long_run_requested=long_run,
                    long_run_executed=False,
                    phases=phases,
                    runtime_truth=runtime_truth,
                    failure_stage="single",
                    next_step="Inspect single-run artifacts before retrying evolve.",
                )

        if profile.run_preflight_evolve:
            await run_evolve_fn(int(profile.preflight_evolve_rounds))
            preflight_evolve_ok, preflight_evolve_detail = status_runner("evolve")
            phases.append(PhaseResult(name="evolve_preflight", ok=preflight_evolve_ok, detail=preflight_evolve_detail))
            if not preflight_evolve_ok:
                return HarnessResult(
                    ok=False,
                    profile_path=str(profile_path),
                    long_run_requested=long_run,
                    long_run_executed=False,
                    phases=phases,
                    runtime_truth=runtime_truth,
                    failure_stage="evolve_preflight",
                    next_step="Fix the short evolve failure before requesting a long run.",
                )

        if not long_run:
            return HarnessResult(
                ok=True,
                profile_path=str(profile_path),
                long_run_requested=False,
                long_run_executed=False,
                phases=phases,
                runtime_truth=runtime_truth,
            )

        if not profile.run_preflight_evolve:
            phases.append(
                PhaseResult(
                    name="evolve_long",
                    ok=False,
                    detail="long run requires run_preflight_evolve=true in the selected profile",
                )
            )
            return HarnessResult(
                ok=False,
                profile_path=str(profile_path),
                long_run_requested=True,
                long_run_executed=False,
                phases=phases,
                runtime_truth=runtime_truth,
                failure_stage="profile_policy",
                next_step="Use a controlled_run profile or enable run_preflight_evolve before requesting --long-run.",
            )

        long_rounds = _resolve_long_run_rounds(profile)
        await run_evolve_fn(long_rounds)
        long_ok, long_detail = status_runner("evolve")
        phases.append(PhaseResult(name="evolve_long", ok=long_ok, detail=f"rounds={long_rounds}; {long_detail}"))
        return HarnessResult(
            ok=long_ok,
            profile_path=str(profile_path),
            long_run_requested=True,
            long_run_executed=True,
            phases=phases,
            runtime_truth=runtime_truth,
            failure_stage=None if long_ok else "evolve_long",
            next_step=None if long_ok else "Inspect long-run diagnostics before re-running the profile.",
        )
    finally:
        _restore_runtime_env(runtime_backup)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pixiu fixed-order experiment harness")
    parser.add_argument(
        "--profile",
        default=str(DEFAULT_PROFILE_PATH),
        help="Path to experiment profile JSON.",
    )
    parser.add_argument(
        "--long-run",
        action="store_true",
        help="Run the long evolve stage after preflight evolve succeeds.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON summary only.",
    )
    return parser.parse_args(argv)


def _print_text_summary(result: HarnessResult) -> None:
    print("[Harness] status:", "PASS" if result.ok else "FAIL")
    print("[Harness] profile:", result.profile_path)
    print("[Harness] profile_kind:", result.runtime_truth.get("profile_kind"))
    print("[Harness] namespace:", result.runtime_truth.get("namespace"))
    print("[Harness] persistence_mode:", result.runtime_truth.get("persistence_mode"))
    print("[Harness] market_context_mode:", result.runtime_truth.get("market_context_mode"))
    print("[Harness] planned_phases:", ", ".join(result.runtime_truth.get("planned_phases", [])))
    print("[Harness] write_scope:", result.runtime_truth.get("write_scope"))
    print("[Harness] long_run_requested:", result.long_run_requested)
    print("[Harness] long_run_executed:", result.long_run_executed)
    if result.failure_stage:
        print("[Harness] failure_stage:", result.failure_stage)
    if result.next_step:
        print("[Harness] next_step:", result.next_step)
    for phase in result.phases:
        marker = "PASS" if phase.ok else "FAIL"
        print(f"[Harness] {phase.name}: {marker} - {phase.detail}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    profile = load_profile(args.profile)
    def _preflight_with_output_policy(*pre_args, **pre_kwargs):
        return run_preflight(
            *pre_args,
            **pre_kwargs,
            doctor_runner=lambda mode, env: _PRE.run_doctor(mode, env, quiet=args.json),
        )

    result = asyncio.run(
        run_harness(
            profile,
            profile_path=args.profile,
            long_run=args.long_run,
            preflight_fn=_preflight_with_output_policy,
        )
    )
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False))
    else:
        _print_text_summary(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
