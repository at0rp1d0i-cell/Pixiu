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

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "profile_path": self.profile_path,
            "long_run_requested": self.long_run_requested,
            "long_run_executed": self.long_run_executed,
            "phases": [asdict(item) for item in self.phases],
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
    run = StateStore().get_latest_run()
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


def _apply_runtime_env(profile, env: Mapping[str, str] | None = None) -> dict[str, str]:
    env_truth = resolve_profile_env_truth(
        profile,
        project_root=PROJECT_ROOT,
        env=env,
        repo_env_path=PROJECT_ROOT / ".env",
    )
    merged = dict(env_truth.merged_env)
    merged["REPORT_EVERY_N_ROUNDS"] = str(profile.report_every_n_rounds)
    for key in env_truth.sources:
        os.environ[key] = merged[key]
    os.environ["REPORT_EVERY_N_ROUNDS"] = merged["REPORT_EVERY_N_ROUNDS"]
    return merged


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
        )

    _apply_runtime_env(profile, env=env)

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
        )

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
        )

    if not long_run:
        return HarnessResult(
            ok=True,
            profile_path=str(profile_path),
            long_run_requested=False,
            long_run_executed=False,
            phases=phases,
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
    )


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
    print("[Harness] long_run_requested:", result.long_run_requested)
    print("[Harness] long_run_executed:", result.long_run_executed)
    for phase in result.phases:
        marker = "PASS" if phase.ok else "FAIL"
        print(f"[Harness] {phase.name}: {marker} - {phase.detail}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    profile = load_profile(args.profile)
    result = asyncio.run(
        run_harness(
            profile,
            profile_path=args.profile,
            long_run=args.long_run,
        )
    )
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False))
    else:
        _print_text_summary(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
