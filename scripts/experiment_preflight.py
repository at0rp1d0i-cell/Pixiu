#!/usr/bin/env python3
"""Experiment preflight gate for Pixiu harness."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Mapping

from src.core.env import apply_resolved_env, resolve_layered_env
from src.schemas.hypothesis import ExplorationSubspace

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
PROFILE_KINDS = {"controlled_run", "fast_feedback"}
PERSISTENCE_MODES = {"full", "test_namespace", "artifact_only"}
MARKET_CONTEXT_MODES = {"live", "cached", "frozen"}
DOCTOR_MODES = {"core", "full", "fast_feedback"}


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
    human_gate_auto_action: str = "none"
    profile_kind: str = "controlled_run"
    target_islands: list[str] = field(default_factory=list)
    target_subspaces: list[str] = field(default_factory=list)
    market_context_mode: str = "live"
    market_context_path: str = ""
    persistence_mode: str = "full"
    namespace: str = ""
    stage1_enrichment_enabled: bool = True
    run_single: bool = True
    run_preflight_evolve: bool = True


@dataclass(frozen=True)
class PreflightIssue:
    kind: str
    message: str
    next_step: str


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
    blocking_issues: list[dict[str, str]]
    warnings: list[str]
    runtime_truth: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedProfileEnv:
    merged_env: dict[str, str]
    qlib_data_dir: str
    sources: dict[str, str]
    runtime_truth: dict[str, object]


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
        human_gate_auto_action=str(payload.get("human_gate_auto_action", "none")),
        profile_kind=str(payload.get("profile_kind", "controlled_run")),
        target_islands=_normalize_string_list(payload.get("target_islands")) or [str(payload["single_island"])],
        target_subspaces=_normalize_subspace_list(payload.get("target_subspaces")),
        market_context_mode=str(payload.get("market_context_mode", "live")),
        market_context_path=str(payload.get("market_context_path", "")),
        persistence_mode=str(payload.get("persistence_mode", "full")),
        namespace=str(payload.get("namespace", "")),
        stage1_enrichment_enabled=bool(payload.get("stage1_enrichment_enabled", True)),
        run_single=bool(payload.get("run_single", True)),
        run_preflight_evolve=bool(payload.get("run_preflight_evolve", True)),
    )
    _validate_profile(profile)
    return profile


def _normalize_string_list(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result


def _normalize_subspace_list(raw) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in _normalize_string_list(raw):
        try:
            value = ExplorationSubspace(item).value
        except ValueError as exc:
            raise ValueError(f"Unknown target_subspace: {item}") from exc
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _validate_profile(profile: ExperimentProfile) -> None:
    if profile.doctor_mode not in DOCTOR_MODES:
        raise ValueError("doctor_mode must be one of: core, full, fast_feedback")
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
    if profile.profile_kind not in PROFILE_KINDS:
        raise ValueError("profile_kind must be one of: controlled_run, fast_feedback")
    if profile.persistence_mode not in PERSISTENCE_MODES:
        raise ValueError("persistence_mode must be one of: full, test_namespace, artifact_only")
    if profile.market_context_mode not in MARKET_CONTEXT_MODES:
        raise ValueError("market_context_mode must be one of: live, cached, frozen")
    if not profile.target_islands:
        raise ValueError("target_islands must include at least one island")
    if profile.single_island not in profile.target_islands:
        raise ValueError("single_island must be included in target_islands")
    if not profile.run_single and not profile.run_preflight_evolve:
        raise ValueError("At least one of run_single or run_preflight_evolve must be enabled")
    if profile.profile_kind == "fast_feedback" and profile.persistence_mode == "full":
        raise ValueError("fast_feedback profile cannot use persistence_mode=full")
    if profile.doctor_mode == "fast_feedback" and profile.market_context_mode == "live":
        raise ValueError("doctor_mode=fast_feedback requires market_context_mode=cached or frozen")
    action = profile.human_gate_auto_action.strip()
    if not action:
        raise ValueError("human_gate_auto_action must be non-empty")
    if action not in {"none", "approve", "stop"} and not action.startswith("redirect:"):
        raise ValueError(
            "human_gate_auto_action must be one of: none, approve, stop, redirect:<island>"
        )


def _resolve_profile_namespace(profile: ExperimentProfile, profile_path: str | Path) -> str:
    raw = profile.namespace.strip()
    if raw:
        return raw
    return Path(profile_path).stem.replace(".", "_") or profile.profile_kind


def _resolve_market_context_path(
    profile: ExperimentProfile,
    *,
    project_root: Path,
) -> Path:
    raw = profile.market_context_path.strip()
    if raw:
        path = Path(raw)
    else:
        path = project_root / "data" / "market_context_cache" / f"{profile.single_island}.json"
    if not path.is_absolute():
        path = project_root / path
    return path


def _build_runtime_truth(
    profile: ExperimentProfile,
    *,
    profile_path: str | Path,
    project_root: Path,
) -> dict[str, object]:
    namespace = _resolve_profile_namespace(profile, profile_path)
    market_context_path = _resolve_market_context_path(profile, project_root=project_root)

    if profile.persistence_mode == "full":
        data_root = project_root / "data"
        formal_writes_allowed = True
        write_scope = "formal_runtime"
    else:
        data_root = project_root / "data" / "runtime_namespaces" / namespace
        formal_writes_allowed = False
        write_scope = (
            "isolated_namespace"
            if profile.persistence_mode == "test_namespace"
            else "artifact_only_scratch"
        )

    planned_phases = ["doctor"]
    if profile.run_single:
        planned_phases.append("single")
    if profile.run_preflight_evolve:
        planned_phases.append("evolve_preflight")

    target_islands = list(profile.target_islands or [profile.single_island])
    target_subspaces = profile.target_subspaces or [subspace.value for subspace in ExplorationSubspace]

    return {
        "profile_kind": profile.profile_kind,
        "namespace": namespace,
        "target_islands": target_islands,
        "target_subspaces": list(target_subspaces),
        "market_context_mode": profile.market_context_mode,
        "market_context_path": str(market_context_path),
        "persistence_mode": profile.persistence_mode,
        "stage1_enrichment_enabled": profile.stage1_enrichment_enabled,
        "planned_phases": planned_phases,
        "formal_writes_allowed": formal_writes_allowed,
        "write_scope": write_scope,
        "state_store_path": str(data_root / "control_plane_state.db"),
        "factor_pool_db_path": str(data_root / "factor_pool_db"),
        "experiment_runs_dir": str(data_root / "experiment_runs"),
        "artifacts_dir": str(data_root / "artifacts"),
        "reports_dir": str(data_root / "reports"),
    }


def resolve_profile_env_truth(
    profile: ExperimentProfile,
    *,
    project_root: Path = PROJECT_ROOT,
    env: Mapping[str, str] | None = None,
    runtime_env_path: str | Path | None = None,
    repo_env_path: str | Path | None = None,
    profile_path: str | Path = DEFAULT_PROFILE_PATH,
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

    runtime_truth = _build_runtime_truth(
        profile,
        profile_path=profile_path,
        project_root=project_root,
    )
    runtime_truth["qlib_data_dir"] = str(qlib_path)

    merged_env["ACTIVE_ISLANDS"] = ",".join(runtime_truth["target_islands"])
    merged_env["PIXIU_TARGET_SUBSPACES"] = ",".join(runtime_truth["target_subspaces"])
    merged_env["PIXIU_STAGE1_CONTEXT_MODE"] = profile.market_context_mode
    merged_env["PIXIU_STAGE1_CONTEXT_PATH"] = str(runtime_truth["market_context_path"])
    merged_env["PIXIU_STAGE1_ENABLE_ENRICHMENT"] = "1" if profile.stage1_enrichment_enabled else "0"
    merged_env["PIXIU_EXPERIMENT_PROFILE_KIND"] = profile.profile_kind
    merged_env["PIXIU_EXPERIMENT_PERSISTENCE_MODE"] = profile.persistence_mode
    merged_env["PIXIU_EXPERIMENT_NAMESPACE"] = str(runtime_truth["namespace"])
    merged_env["PIXIU_STATE_STORE_PATH"] = str(runtime_truth["state_store_path"])
    merged_env["PIXIU_FACTOR_POOL_DB_PATH"] = str(runtime_truth["factor_pool_db_path"])
    merged_env["PIXIU_EXPERIMENT_RUNS_DIR"] = str(runtime_truth["experiment_runs_dir"])
    merged_env["PIXIU_ARTIFACTS_DIR"] = str(runtime_truth["artifacts_dir"])
    merged_env["PIXIU_REPORTS_DIR"] = str(runtime_truth["reports_dir"])
    merged_env["REPORT_EVERY_N_ROUNDS"] = str(profile.report_every_n_rounds)
    merged_env["PIXIU_HUMAN_GATE_AUTO_ACTION"] = profile.human_gate_auto_action

    return ResolvedProfileEnv(
        merged_env=merged_env,
        qlib_data_dir=str(qlib_path),
        sources=sources,
        runtime_truth=runtime_truth,
    )


def run_doctor(mode: str, env: Mapping[str, str], *, quiet: bool = False) -> int:
    command = [sys.executable, str(DOCTOR_SCRIPT_PATH), "--mode", mode]
    proc = subprocess.run(
        command,
        env=dict(env),
        check=False,
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.DEVNULL if quiet else None,
    )
    return proc.returncode


def _runtime_trace_targets(runtime_truth: Mapping[str, object]) -> tuple[Path, Path, Path]:
    return (
        Path(str(runtime_truth["state_store_path"])),
        Path(str(runtime_truth["experiment_runs_dir"])),
        Path(str(runtime_truth["artifacts_dir"])),
    )


def _has_runtime_traces(runtime_truth: Mapping[str, object]) -> bool:
    for target in _runtime_trace_targets(runtime_truth):
        if not target.exists():
            continue
        if target.is_file():
            return True
        if target.is_dir() and any(target.iterdir()):
            return True
    return False


def _load_context_validation(runtime_truth: Mapping[str, object]) -> tuple[object, list[dict[str, str]]]:
    from src.agents.market_analyst import _load_market_context_from_path

    return _load_market_context_from_path(Path(str(runtime_truth["market_context_path"])))


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
        profile_path=profile_path,
    )
    merged_env = env_truth.merged_env
    warnings: list[str] = []
    blocking: list[str] = []
    blocking_issues: list[PreflightIssue] = []

    def add_blocking(kind: str, message: str, next_step: str) -> None:
        blocking.append(message)
        blocking_issues.append(
            PreflightIssue(kind=kind, message=message, next_step=next_step)
        )

    qlib_path = Path(env_truth.qlib_data_dir)
    if not qlib_path.exists():
        add_blocking("env", f"QLIB_DATA_DIR not found: {qlib_path}", "Fix QLIB_DATA_DIR or sync local qlib data.")

    if profile.market_context_mode == "live" and not merged_env.get("TUSHARE_TOKEN"):
        add_blocking("env", "TUSHARE_TOKEN missing", "Provide TUSHARE_TOKEN or switch market_context_mode to cached/frozen.")

    if profile.market_context_mode in {"cached", "frozen"}:
        context_path = Path(str(env_truth.runtime_truth["market_context_path"]))
        if not context_path.exists():
            add_blocking(
                "context",
                f"market context file not found: {context_path}",
                "Provide market_context_path or run a live profile to materialize a cached context.",
            )
        else:
            try:
                memo, payload_warnings = _load_context_validation(env_truth.runtime_truth)
                from src.agents.market_analyst import is_degraded_market_context

                if is_degraded_market_context(memo):
                    add_blocking(
                        "context",
                        f"market context file is degraded: {context_path}",
                        "Refresh the cached/frozen context with a non-degraded Stage 1 memo.",
                    )
                if getattr(memo, "date", "") != date.today().strftime("%Y-%m-%d"):
                    warnings.append(
                        f"{profile.market_context_mode} market context date is {memo.date}, not today."
                    )
                for warning in payload_warnings:
                    warnings.append(
                        f"context payload warning [{warning['field']}]: {warning['message']}"
                    )
            except Exception as exc:
                add_blocking(
                    "context",
                    f"market context file invalid: {context_path} ({exc})",
                    "Replace the context file with a valid MarketContextMemo JSON payload.",
                )

    if profile.require_reset_clean and _has_runtime_traces(env_truth.runtime_truth):
        add_blocking(
            "runtime_state",
            "require_reset_clean=true but runtime traces exist; run scripts/reset_experiment_state.py",
            "Clear the runtime traces before starting this profile.",
        )

    doctor_exit_code: int | None = None
    if not blocking:
        doctor_exit_code = doctor_runner(profile.doctor_mode, merged_env)
        if doctor_exit_code != 0:
            add_blocking(
                "doctor",
                f"doctor --mode {profile.doctor_mode} failed (exit={doctor_exit_code})",
                "Fix doctor blocking checks before starting the experiment.",
            )

    if profile.doctor_mode == "full":
        warnings.append("full doctor mode includes enrichment/data-plane checks and may be slower.")
    if profile.profile_kind == "fast_feedback":
        warnings.append("fast_feedback writes are isolated from the formal runtime surfaces.")

    return PreflightResult(
        ok=not blocking,
        profile_path=str(Path(profile_path)),
        doctor_mode=profile.doctor_mode,
        qlib_data_dir=str(qlib_path),
        qlib_data_dir_source=env_truth.sources["QLIB_DATA_DIR"],
        tushare_token_source=env_truth.sources["TUSHARE_TOKEN"],
        doctor_exit_code=doctor_exit_code,
        blocking_errors=blocking,
        blocking_issues=[asdict(item) for item in blocking_issues],
        warnings=warnings,
        runtime_truth=env_truth.runtime_truth,
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
    print("[Preflight] profile_kind:", result.runtime_truth["profile_kind"])
    print("[Preflight] persistence_mode:", result.runtime_truth["persistence_mode"])
    print("[Preflight] market_context_mode:", result.runtime_truth["market_context_mode"])
    print("[Preflight] qlib_data_dir:", result.qlib_data_dir)
    print("[Preflight] qlib_data_dir_source:", result.qlib_data_dir_source)
    print("[Preflight] tushare_token_source:", result.tushare_token_source)
    print("[Preflight] target_islands:", ", ".join(result.runtime_truth["target_islands"]))
    print("[Preflight] target_subspaces:", ", ".join(result.runtime_truth["target_subspaces"]))
    print("[Preflight] planned_phases:", ", ".join(result.runtime_truth["planned_phases"]))
    print("[Preflight] write_scope:", result.runtime_truth["write_scope"])
    print("[Preflight] formal_writes_allowed:", result.runtime_truth["formal_writes_allowed"])
    print("[Preflight] state_store_path:", result.runtime_truth["state_store_path"])
    print("[Preflight] market_context_path:", result.runtime_truth["market_context_path"])
    if result.doctor_exit_code is not None:
        print("[Preflight] doctor_exit_code:", result.doctor_exit_code)
    if result.blocking_issues:
        print("[Preflight] blocking_issues:")
        for item in result.blocking_issues:
            print(f"  - [{item['kind']}] {item['message']}")
            print(f"    next_step: {item['next_step']}")
    elif result.blocking_errors:
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
    result = run_preflight(
        profile,
        profile_path=args.profile,
        doctor_runner=lambda mode, env: run_doctor(mode, env, quiet=args.json),
    )
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False))
    else:
        _print_text(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
