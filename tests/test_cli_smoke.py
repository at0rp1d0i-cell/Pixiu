from __future__ import annotations

from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from src.control_plane.state_store import StateStore
from src.schemas.control_plane import RunSnapshot
from src.cli import main as cli_main

pytestmark = pytest.mark.smoke


def test_cli_help_lists_core_commands():
    runner = CliRunner()
    result = runner.invoke(cli_main.app, ["--help"])

    assert result.exit_code == 0
    for command_name in [
        "run",
        "status",
        "factors",
        "approve",
        "redirect",
        "stop",
        "report",
    ]:
        assert command_name in result.stdout


def test_approve_command_queues_decision_and_prints_success(tmp_path, monkeypatch):
    store = StateStore(tmp_path / "state_store.sqlite")
    run = store.create_run(mode="single")
    store.write_snapshot(
        RunSnapshot(
            run_id=run.run_id,
            approved_notes_count=1,
            backtest_reports_count=1,
            verdicts_count=1,
            awaiting_human_approval=True,
            updated_at=datetime.now(UTC),
        )
    )
    monkeypatch.setattr(cli_main, "_get_state_store", lambda: store)

    runner = CliRunner()
    result = runner.invoke(cli_main.app, ["approve"])

    assert result.exit_code == 0
    assert "已批准" in result.stdout
    latest = store.pop_latest_human_decision(run.run_id)
    assert latest is not None
    assert latest.action == "approve"


def test_approve_command_reports_missing_waiting_snapshot(tmp_path, monkeypatch):
    store = StateStore(tmp_path / "state_store.sqlite")
    store.create_run(mode="single")
    monkeypatch.setattr(cli_main, "_get_state_store", lambda: store)

    runner = CliRunner()
    result = runner.invoke(cli_main.app, ["approve"])

    assert result.exit_code == 0
    assert "已批准" not in result.stdout
    assert "当前没有等待审批的实验" in result.stdout


def test_redirect_command_prints_success_message(monkeypatch):
    called: list[str] = []

    monkeypatch.setattr(
        cli_main,
        "_inject_human_decision",
        lambda decision: called.append(decision) or True,
    )

    runner = CliRunner()
    result = runner.invoke(cli_main.app, ["redirect", "momentum"])

    assert result.exit_code == 0
    assert called == ["redirect:momentum"]
    assert "momentum" in result.stdout


def test_stop_command_stays_quiet_when_injection_fails(monkeypatch):
    monkeypatch.setattr(cli_main, "_inject_human_decision", lambda decision: False)

    runner = CliRunner()
    result = runner.invoke(cli_main.app, ["stop"])

    assert result.exit_code == 0
    assert result.stdout.strip() == ""


def test_run_command_skips_static_banner_when_tty(monkeypatch):
    import src.core.orchestrator as orchestrator

    monkeypatch.setattr(cli_main.sys.stdout, "isatty", lambda: True, raising=False)

    calls: list[object] = []

    monkeypatch.setattr(cli_main.console, "print", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(cli_main, "_run_with_progress", lambda coro, total_rounds=None: None)
    monkeypatch.setattr(orchestrator, "run_evolve", lambda rounds, islands=None: object())

    cli_main.run(mode="evolve", rounds=2, island="momentum", islands=None, verbose=False)
    assert calls == []
