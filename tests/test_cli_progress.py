from __future__ import annotations

import os
from contextlib import suppress
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
    assert "Approved Notes" in rendered
    assert "Backtest Reports" in rendered
    assert "Verdicts" in rendered
    assert "pixiu approve" in rendered


def test_run_with_progress_skips_live_when_not_tty(monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    async def _coro():
        return 42

    assert _run_with_progress(_coro()) == 42


def test_run_with_progress_uses_transient_live_when_tty(monkeypatch):
    from src.cli import main as cli_main

    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    captured = {}
    configured = {}
    printed = []

    class FakeLive:
        def __init__(self, *args, **kwargs):
            captured["transient"] = kwargs.get("transient")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def update(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(cli_main, "Live", FakeLive)
    monkeypatch.setattr(cli_main, "_get_state_store", lambda: (_ for _ in ()).throw(RuntimeError("no state")))
    monkeypatch.setattr(cli_main, "_configure_tty_live_logging", lambda: configured.setdefault("path", Path("/tmp/pixiu.log")))
    monkeypatch.setattr(cli_main.console, "print", lambda *args, **kwargs: printed.append((args, kwargs)))

    async def _coro():
        return 7

    assert cli_main._run_with_progress(_coro()) == 7
    assert captured["transient"] is True
    assert configured["path"] == Path("/tmp/pixiu.log")
    assert printed


def test_configure_tty_live_logging_sets_mcp_log_level(monkeypatch, tmp_path: Path):
    from src.cli import main as cli_main
    import logging

    monkeypatch.delenv("PIXIU_MCP_LOG_LEVEL", raising=False)
    monkeypatch.setattr(cli_main, "_get_logs_dir", lambda: tmp_path / "logs")

    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    try:
        log_path = cli_main._configure_tty_live_logging()

        assert os.environ["PIXIU_MCP_LOG_LEVEL"] == "WARNING"
        assert log_path.parent.exists()
    finally:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            with suppress(Exception):
                handler.close()
        for handler in original_handlers:
            root_logger.addHandler(handler)
