from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from rich.console import Console

from src.cli.main import _run_with_progress
from src.cli.progress import RunProgressTracker, build_run_progress_panel
from src.control_plane.state_store import StateStore
from src.schemas.control_plane import RunSnapshot

import pytest

pytestmark = pytest.mark.unit


def test_run_progress_panel_includes_stage_round_and_snapshot_path(tmp_path: Path):
    store = StateStore(tmp_path / "state.sqlite")
    run = store.create_run(mode="evolve")
    updated = store.update_run(
        run.run_id,
        current_stage="market_context",
        current_round=3,
    )
    snapshot = RunSnapshot(
        run_id=run.run_id,
        approved_notes_count=1,
        backtest_reports_count=2,
        verdicts_count=3,
        awaiting_human_approval=True,
        updated_at=datetime.now(UTC) - timedelta(seconds=7),
    )

    run_dir = tmp_path / "experiment_runs" / run.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "round_000.json").write_text("{}", encoding="utf-8")
    (run_dir / "round_003.json").write_text(
        (
            '{"timings":{"stages_ms":{"market_context":1250.5,"hypothesis_gen":620.0},'
            '"round_total_ms":1870.5}}'
        ),
        encoding="utf-8",
    )

    tracker = RunProgressTracker()
    view = tracker.observe(
        updated,
        snapshot,
        total_rounds=20,
        runs_dir=tmp_path / "experiment_runs",
    )

    console = Console(record=True, width=120)
    console.print(build_run_progress_panel(view))
    rendered = console.export_text()

    assert run.run_id in rendered
    assert "market_context" in rendered
    assert "3/20" in rendered
    assert "round_003.json" in rendered
    assert "1870.50 ms" in rendered
    assert "market_context (1250.50 ms)" in rendered


def test_run_with_progress_skips_live_when_not_tty(monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    async def _coro():
        return 42

    assert _run_with_progress(_coro()) == 42
