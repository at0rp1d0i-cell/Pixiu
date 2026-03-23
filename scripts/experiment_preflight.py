#!/usr/bin/env python3
"""Experiment preflight gate for Pixiu harness."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from src.core.env import apply_resolved_env, resolve_layered_env

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_PATH = PROJECT_ROOT / "config" / "experiments" / "default.json"
DOCTOR_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "doctor.py"
RESET_TARGETS = (
    PROJECT_ROOT / "data" / "control_plane_state.db",
    PROJECT_ROOT / "data" / "experiment_runs",
    PROJECT_ROOT / "data" / "artifacts",
)
CRITICAL_ENV_KEYS = ("TUSHARE_TOKEN", "QLIB_DATA_DIR")
SOURCE_PROFILE = "profile"
SOURCE_UNSET = "unset"


@dataclass(frozen=True)
class ExperimentProfile:
    doctor_mode: str
    single_island: str
    preflight_evolve_rounds: int
    long_run_rounds: int
    require_reset_clean: bool
    qlib_data_dir: str
    report_every_n_rounds: int
    max_rounds_env_override_allowed: bool


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    profile_path: str
    doctor_mode: str
    qlib_data_dir: str
    qlib_data_dir_source: str
    tushare_token_source: str
    doctor_exit_code: int | None
    blocking_errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedProfileEnv:
    merged_env: dict[str, str]
    qlib_data_dir: str
    sources: dict[str, str]


def _read_json(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON profile: {path} ({exc})") from exc


def load_profile(profile_path: str | Path = DEFAULT_PROFILE_PATH) -> ExperimentProfile:
    path = Path(profile_path)
    payload = _read_json(path)

    required = {
        "doctor_mode",
        "single_island",
        "preflight_evolve_rounds",
        "long_run_rounds",
        "require_reset_clean",
        "qlib_data_dir",
        "report_every_n_rounds",
        "max_rounds_env_override_allowed",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"Missing profile keys: {missing}")

    profile = ExperimentProfile(
        doctor_mode=str(payload["doctor_mode"]),
        single_island=str(payload["single_island"]),
        preflight_evolve_rounds=int(payload["preflight_evolve_rounds"]),
        long_run_rounds=int(payload["long_run_rounds"]),
        require_reset_clean=bool(payload["require_reset_clean"]),
        qlib_data_dir=str(payload["qlib_data_dir"]),
        report_every_n_rounds=int(payload["report_every_n_rounds"]),
        max_rounds_env_override_allowed=bool(payload["max_rounds_env_override_allowed"]),
    )
    _validate_profile(profile)
    return profile


def _validate_profile(profile: ExperimentProfile) -> None:
    if profile.doctor_mode not in {"core", "full"}:
        raise ValueError("doctor_mode must be one of: core, full")
    if profile.preflight_evolve_rounds <= 0:
        raise ValueError("preflight_evolve_rounds must be > 0")
    if profile.long_run_rounds <= 0:
        raise ValueError("long_run_rounds must be > 0")
    if profile.report_every_n_rounds <= 0:
        raise ValueError("report_every_n_rounds must be > 0")
    if not profile.single_island.strip():
        raise ValueError("single_island must be non-empty")
    if not profile.qlib_data_dir.strip():
        raise ValueError("qlib_data_dir must be non-empty")


def resolve_profile_env_truth(
    profile: ExperimentProfile,
    *,
    project_root: Path = PROJECT_ROOT,
    env: Mapping[str, str] | None = None,
    runtime_env_path: str | Path | None = None,
    repo_env_path: str | Path | None = None,
) -> ResolvedProfileEnv:
    merged_env = dict(os.environ) if env is None else dict(env)

    repo_path = Path(repo_env_path) if repo_env_path is not None else project_root / ".env"
    resolved = resolve_layered_env(
        keys=CRITICAL_ENV_KEYS,
        process_env=merged_env,
        runtime_env_path=runtime_env_path,
        repo_env_path=repo_path,
        defaults={"QLIB_DATA_DIR": profile.qlib_data_dir},
        default_source=SOURCE_PROFILE,
    )
    apply_resolved_env(resolved, target_env=merged_env)

    raw_qlib = Path(merged_env["QLIB_DATA_DIR"])
    qlib_path = raw_qlib if raw_qlib.is_absolute() else project_root / raw_qlib
    merged_env["QLIB_DATA_DIR"] = str(qlib_path)

    sources = dict(resolved.sources)
    if "TUSHARE_TOKEN" not in sources:
        sources["TUSHARE_TOKEN"] = SOURCE_UNSET
    if "QLIB_DATA_DIR" not in sources:
        sources["QLIB_DATA_DIR"] = SOURCE_PROFILE

    return ResolvedProfileEnv(
        merged_env=merged_env,
        qlib_data_dir=str(qlib_path),
        sources=sources,
    )


def run_doctor(mode: str, env: Mapping[str, str]) -> int:
    command = [sys.executable, str(DOCTOR_SCRIPT_PATH), "--mode", mode]
    proc = subprocess.run(command, env=dict(env), check=False)
    return proc.returncode


def _reset_targets(project_root: Path) -> tuple[Path, Path, Path]:
    return (
        project_root / "data" / "control_plane_state.db",
        project_root / "data" / "experiment_runs",
        project_root / "data" / "artifacts",
    )


def _has_runtime_traces(*, project_root: Path = PROJECT_ROOT) -> bool:
    for target in _reset_targets(project_root):
        if not target.exists():
            continue
        if target.is_file():
            return True
        if target.is_dir() and any(target.iterdir()):
            return True
    return False


def run_preflight(
    profile: ExperimentProfile,
    *,
    profile_path: str | Path = DEFAULT_PROFILE_PATH,
    project_root: Path = PROJECT_ROOT,
    env: Mapping[str, str] | None = None,
    doctor_runner=run_doctor,
    runtime_env_path: str | Path | None = None,
    repo_env_path: str | Path | None = None,
) -> PreflightResult:
    env_truth = resolve_profile_env_truth(
        profile,
        project_root=project_root,
        env=env,
        runtime_env_path=runtime_env_path,
        repo_env_path=repo_env_path,
    )
    merged_env = env_truth.merged_env
    warnings: list[str] = []
    blocking: list[str] = []

    qlib_path = Path(env_truth.qlib_data_dir)
    if not qlib_path.exists():
        blocking.append(f"QLIB_DATA_DIR not found: {qlib_path}")

    if not merged_env.get("TUSHARE_TOKEN"):
        blocking.append("TUSHARE_TOKEN missing")

    if profile.require_reset_clean and _has_runtime_traces(project_root=project_root):
        blocking.append("require_reset_clean=true but runtime traces exist; run scripts/reset_experiment_state.py")

    doctor_exit_code: int | None = None
    if not blocking:
        doctor_exit_code = doctor_runner(profile.doctor_mode, merged_env)
        if doctor_exit_code != 0:
            blocking.append(f"doctor --mode {profile.doctor_mode} failed (exit={doctor_exit_code})")

    if profile.doctor_mode == "full":
        warnings.append("full doctor mode includes enrichment/data-plane checks and may be slower.")

    return PreflightResult(
        ok=not blocking,
        profile_path=str(Path(profile_path)),
        doctor_mode=profile.doctor_mode,
        qlib_data_dir=str(qlib_path),
        qlib_data_dir_source=env_truth.sources["QLIB_DATA_DIR"],
        tushare_token_source=env_truth.sources["TUSHARE_TOKEN"],
        doctor_exit_code=doctor_exit_code,
        blocking_errors=blocking,
        warnings=warnings,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pixiu experiment preflight")
    parser.add_argument(
        "--profile",
        default=str(DEFAULT_PROFILE_PATH),
        help="Path to experiment profile JSON.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON result only.",
    )
    return parser.parse_args(argv)


def _print_text(result: PreflightResult) -> None:
    print("[Preflight] status:", "PASS" if result.ok else "FAIL")
    print("[Preflight] profile:", result.profile_path)
    print("[Preflight] doctor_mode:", result.doctor_mode)
    print("[Preflight] qlib_data_dir:", result.qlib_data_dir)
    print("[Preflight] qlib_data_dir_source:", result.qlib_data_dir_source)
    print("[Preflight] tushare_token_source:", result.tushare_token_source)
    if result.doctor_exit_code is not None:
        print("[Preflight] doctor_exit_code:", result.doctor_exit_code)
    if result.blocking_errors:
        print("[Preflight] blocking:")
        for item in result.blocking_errors:
            print("  -", item)
    if result.warnings:
        print("[Preflight] warnings:")
        for item in result.warnings:
            print("  -", item)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    profile = load_profile(args.profile)
    result = run_preflight(profile, profile_path=args.profile)
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False))
    else:
        _print_text(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
