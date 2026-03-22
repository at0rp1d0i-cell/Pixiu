#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


@dataclass(frozen=True)
class ResetTarget:
    label: str
    relative_path: str
    path: Path
    kind: str
    default: bool
    note: str


def build_targets(*, project_root: Path | None = None, include_factor_pool: bool = False) -> list[ResetTarget]:
    root = project_root or PROJECT_ROOT
    data_dir = root / "data"
    targets = [
        ResetTarget(
            label="control plane state",
            relative_path="data/control_plane_state.db",
            path=data_dir / "control_plane_state.db",
            kind="file",
            default=True,
            note="Delete stale experiment orchestration state.",
        ),
        ResetTarget(
            label="experiment runs",
            relative_path="data/experiment_runs/",
            path=data_dir / "experiment_runs",
            kind="dir",
            default=True,
            note="Delete persisted run metadata and per-run traces.",
        ),
        ResetTarget(
            label="artifacts",
            relative_path="data/artifacts/",
            path=data_dir / "artifacts",
            kind="dir",
            default=True,
            note="Delete generated artifacts from invalid experiment runs.",
        ),
        ResetTarget(
            label="factor pool",
            relative_path="data/factor_pool_db/",
            path=data_dir / "factor_pool_db",
            kind="dir",
            default=False,
            note=(
                "Delete passed-factor knowledge store only when an explicit full reset is intended."
                if include_factor_pool
                else "Preserved by default because passed factors are knowledge assets."
            ),
        ),
    ]
    return [target for target in targets if target.default or include_factor_pool]


def preserved_targets(*, project_root: Path | None = None, include_factor_pool: bool = False) -> list[ResetTarget]:
    if include_factor_pool:
        return []
    root = project_root or PROJECT_ROOT
    return [
        ResetTarget(
            label="factor pool",
            relative_path="data/factor_pool_db/",
            path=root / "data" / "factor_pool_db",
            kind="dir",
            default=False,
            note="Use --include-factor-pool to delete this knowledge store explicitly.",
        )
    ]


def _assert_safe_target(target: ResetTarget, *, data_dir: Path) -> None:
    resolved_target = target.path.resolve(strict=False)
    resolved_data_dir = data_dir.resolve(strict=False)
    if resolved_target == resolved_data_dir or resolved_data_dir not in resolved_target.parents:
        raise ValueError(f"Refusing to delete unsafe path outside data/: {target.path}")


def _remove_target(target: ResetTarget) -> str:
    if not target.path.exists():
        return "skip-missing"
    if target.kind == "dir":
        shutil.rmtree(target.path)
        return "deleted-dir"
    target.path.unlink()
    return "deleted-file"


def _write_plan(
    *,
    out: TextIO,
    project_root: Path,
    targets: list[ResetTarget],
    preserved: list[ResetTarget],
    dry_run: bool,
) -> None:
    out.write("Pixiu experiment reset\n")
    out.write(f"Project root: {project_root}\n")
    out.write(f"Mode: {'dry-run' if dry_run else 'delete'}\n")
    out.write("Targets:\n")
    for target in targets:
        state = "exists" if target.path.exists() else "missing"
        out.write(
            f"  - {target.relative_path} [{target.kind}, {state}] {target.note}\n"
        )
    if preserved:
        out.write("Preserved by default:\n")
        for target in preserved:
            state = "exists" if target.path.exists() else "missing"
            out.write(
                f"  - {target.relative_path} [{target.kind}, {state}] {target.note}\n"
            )


def run_reset(
    *,
    project_root: Path | None = None,
    include_factor_pool: bool = False,
    dry_run: bool = False,
    out: TextIO | None = None,
) -> int:
    stream = out or sys.stdout
    root = project_root or PROJECT_ROOT
    data_dir = root / "data"
    targets = build_targets(project_root=root, include_factor_pool=include_factor_pool)
    preserved = preserved_targets(project_root=root, include_factor_pool=include_factor_pool)

    _write_plan(
        out=stream,
        project_root=root,
        targets=targets,
        preserved=preserved,
        dry_run=dry_run,
    )

    for target in targets:
        _assert_safe_target(target, data_dir=data_dir)

    if dry_run:
        stream.write("Dry run only. No files were deleted.\n")
        return 0

    stream.write("Applying reset:\n")
    for target in targets:
        result = _remove_target(target)
        stream.write(f"  - {target.relative_path}: {result}\n")
    stream.write("Reset complete.\n")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Delete Pixiu experiment runtime traces while preserving factor_pool_db by default."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the reset plan without deleting anything.",
    )
    parser.add_argument(
        "--include-factor-pool",
        action="store_true",
        help="Also delete data/factor_pool_db/. Use with care.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_reset(
        include_factor_pool=args.include_factor_pool,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
