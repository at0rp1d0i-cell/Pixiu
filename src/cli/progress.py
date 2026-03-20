"""CLI progress helpers for Pixiu run commands."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rich.console import Group
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from src.control_plane.state_store import StateStore
from src.schemas.control_plane import RunRecord, RunSnapshot

_DEFAULT_RUNS_DIR = Path(__file__).resolve().parents[2] / "data" / "experiment_runs"


@dataclass(frozen=True)
class RunProgressView:
    run_id: str
    mode: str
    status: str
    current_stage: str
    current_round: int
    total_rounds: int | None
    run_elapsed: timedelta
    stage_elapsed: timedelta
    awaiting_human_approval: bool
    snapshot_path: Path | None
    snapshot_updated_at: datetime | None
    latest_round_total_ms: float | None
    slowest_stage: str | None
    slowest_stage_ms: float | None
    last_error: str | None


@dataclass(frozen=True)
class SnapshotTimingSummary:
    path: Path
    round_total_ms: float | None
    slowest_stage: str | None
    slowest_stage_ms: float | None


@dataclass
class RunProgressTracker:
    """Track stage transitions locally while polling public run state."""

    _last_stage: str | None = None
    _stage_started_at: datetime | None = None

    def observe(
        self,
        run: RunRecord,
        snapshot: RunSnapshot | None,
        *,
        total_rounds: int | None = None,
        runs_dir: Path | None = None,
    ) -> RunProgressView:
        now = datetime.now(UTC)
        if run.current_stage != self._last_stage:
            self._last_stage = run.current_stage
            self._stage_started_at = now

        stage_started_at = self._stage_started_at or run.started_at
        latest_snapshot = load_latest_snapshot_timing(run.run_id, runs_dir=runs_dir)
        return RunProgressView(
            run_id=run.run_id,
            mode=run.mode,
            status=run.status,
            current_stage=run.current_stage,
            current_round=run.current_round,
            total_rounds=total_rounds,
            run_elapsed=now - run.started_at,
            stage_elapsed=now - stage_started_at,
            awaiting_human_approval=bool(
                snapshot.awaiting_human_approval if snapshot else False
            ),
            snapshot_path=latest_snapshot.path if latest_snapshot else None,
            snapshot_updated_at=snapshot.updated_at if snapshot else None,
            latest_round_total_ms=latest_snapshot.round_total_ms if latest_snapshot else None,
            slowest_stage=latest_snapshot.slowest_stage if latest_snapshot else None,
            slowest_stage_ms=latest_snapshot.slowest_stage_ms if latest_snapshot else None,
            last_error=run.last_error,
        )


def find_latest_snapshot_path(run_id: str, runs_dir: Path | None = None) -> Path | None:
    """Return the newest round snapshot file for a run, if any."""
    base_dir = (runs_dir or _DEFAULT_RUNS_DIR) / run_id
    if not base_dir.exists():
        return None

    candidates = sorted(base_dir.glob("round_*.json"))
    if not candidates:
        return None

    return max(
        candidates,
        key=lambda path: (
            _round_number(path),
            path.stat().st_mtime,
        ),
    )


def load_latest_snapshot_timing(run_id: str, runs_dir: Path | None = None) -> SnapshotTimingSummary | None:
    path = find_latest_snapshot_path(run_id, runs_dir=runs_dir)
    if path is None:
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return SnapshotTimingSummary(
            path=path,
            round_total_ms=None,
            slowest_stage=None,
            slowest_stage_ms=None,
        )

    timings = payload.get("timings", {}) if isinstance(payload, dict) else {}
    stage_timings = timings.get("stages_ms", {}) if isinstance(timings, dict) else {}
    round_total_ms = timings.get("round_total_ms") if isinstance(timings, dict) else None

    if not isinstance(stage_timings, dict) or not stage_timings:
        return SnapshotTimingSummary(
            path=path,
            round_total_ms=float(round_total_ms) if isinstance(round_total_ms, (int, float)) else None,
            slowest_stage=None,
            slowest_stage_ms=None,
        )

    slowest_stage, slowest_stage_ms = max(
        ((str(name), float(value)) for name, value in stage_timings.items()),
        key=lambda item: item[1],
    )
    return SnapshotTimingSummary(
        path=path,
        round_total_ms=float(round_total_ms) if isinstance(round_total_ms, (int, float)) else None,
        slowest_stage=slowest_stage,
        slowest_stage_ms=slowest_stage_ms,
    )


def build_run_progress_panel(
    view: RunProgressView,
) -> Panel:
    """Build a compact Rich panel for live run progress."""
    table = Table.grid(expand=True)
    table.add_column(style="bold cyan", ratio=1)
    table.add_column(ratio=3)

    table.add_row("Run", view.run_id)
    table.add_row("Mode", view.mode)
    table.add_row("Status", view.status)
    table.add_row("Stage", view.current_stage)
    table.add_row("Round", _format_round(view.current_round, view.total_rounds))
    table.add_row("Run Elapsed", _format_duration(view.run_elapsed))
    table.add_row("Stage Elapsed", _format_duration(view.stage_elapsed))
    table.add_row("Awaiting Approval", "yes" if view.awaiting_human_approval else "no")
    table.add_row("Snapshot", str(view.snapshot_path) if view.snapshot_path else "—")
    table.add_row("Snapshot File", view.snapshot_path.name if view.snapshot_path else "—")
    table.add_row(
        "Snapshot Age",
        _format_duration(datetime.now(UTC) - view.snapshot_updated_at)
        if view.snapshot_updated_at
        else "—",
    )
    table.add_row(
        "Last Round",
        f"{view.latest_round_total_ms:.2f} ms" if view.latest_round_total_ms is not None else "—",
    )
    table.add_row(
        "Slowest Stage",
        (
            f"{view.slowest_stage} ({view.slowest_stage_ms:.2f} ms)"
            if view.slowest_stage and view.slowest_stage_ms is not None
            else "—"
        ),
    )
    table.add_row("Last Error", view.last_error or "—")

    progress = None
    if view.total_rounds and view.total_rounds > 0:
        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            expand=True,
        )
        progress.add_task(
            "Rounds",
            total=view.total_rounds,
            completed=min(view.current_round, view.total_rounds),
        )

    body = Group(table, progress) if progress is not None else table
    return Panel(body, title="Pixiu Run Progress", border_style="cyan")


def load_run_state(store: StateStore, run_id: str | None = None) -> tuple[RunRecord | None, RunSnapshot | None]:
    """Load the latest run and its snapshot for the CLI monitor."""
    run = store.get_latest_run()
    if run is None:
        return None, None
    if run_id is not None and run.run_id != run_id:
        return None, None
    return run, store.get_snapshot(run.run_id)


def _round_number(path: Path) -> int:
    stem = path.stem
    if not stem.startswith("round_"):
        return -1
    try:
        return int(stem.split("_", 1)[1])
    except (IndexError, ValueError):
        return -1


def _format_duration(delta: timedelta) -> str:
    total_seconds = max(int(delta.total_seconds()), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _format_round(current: int, total: int | None) -> str:
    if total is None:
        return str(current)
    return f"{current}/{total}"
