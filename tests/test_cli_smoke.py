from __future__ import annotations

from datetime import UTC, datetime
import pytest
from typer.testing import CliRunner

from src.control_plane.state_store import StateStore
from src.schemas.control_plane import ArtifactRecord, RunSnapshot
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


def test_status_command_renders_run_snapshot_and_latest_report(tmp_path, monkeypatch):
    store = StateStore(tmp_path / "state_store.sqlite")
    run = store.create_run(mode="evolve")
    store.write_snapshot(
        RunSnapshot(
            run_id=run.run_id,
            approved_notes_count=2,
            backtest_reports_count=3,
            verdicts_count=1,
            awaiting_human_approval=True,
            updated_at=datetime.now(UTC),
        )
    )
    report_path = tmp_path / "reports" / "latest.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("# CIO Review", encoding="utf-8")
    store.append_artifact(
        ArtifactRecord(
            run_id=run.run_id,
            kind="cio_report",
            ref_id="report-latest",
            path=str(report_path),
        )
    )
    monkeypatch.setattr(cli_main, "_get_state_store", lambda: store)

    runner = CliRunner()
    result = runner.invoke(cli_main.app, ["status"])

    assert result.exit_code == 0
    assert "Pixiu Runtime Status" in result.stdout
    assert run.run_id in result.stdout
    assert "Approved Notes" in result.stdout
    assert "report-latest" in result.stdout
    assert "pixiu approve" in result.stdout


def test_status_command_reports_store_failure(monkeypatch):
    monkeypatch.setattr(
        cli_main,
        "_get_state_store",
        lambda: (_ for _ in ()).throw(RuntimeError("db boom")),
    )

    runner = CliRunner()
    result = runner.invoke(cli_main.app, ["status"])

    assert result.exit_code == 0
    assert "读取状态失败" in result.stdout
    assert "db boom" in result.stdout


def test_factors_command_renders_ranked_table(monkeypatch):
    import src.factor_pool.pool as pool_module

    class _StubPool:
        def get_top_factors(self, limit: int = 20):
            assert limit >= 2
            return [
                {
                    "factor_id": "momentum_factor_01",
                    "island": "momentum",
                    "sharpe": 2.81,
                    "ic_mean": 0.0432,
                    "icir": 1.72,
                    "formula": "Mean($close, 5) / Ref($close, 5)",
                },
                {
                    "factor_id": "value_factor_02",
                    "island": "value",
                    "sharpe": 1.91,
                    "ic_mean": 0.0310,
                    "icir": 1.21,
                    "formula": "Rank($pb)",
                },
            ]

    monkeypatch.setattr(pool_module, "get_factor_pool", lambda: _StubPool())

    runner = CliRunner()
    result = runner.invoke(cli_main.app, ["factors", "--top", "1", "--island", "momentum"])

    assert result.exit_code == 0
    assert "Factor Leaderboard" in result.stdout
    assert "momentum_factor_01" in result.stdout
    assert "2.81" in result.stdout
    assert "Mean($close, 5)" in result.stdout
    assert "value_factor_02" not in result.stdout


def test_factors_command_reports_empty_leaderboard(monkeypatch):
    import src.factor_pool.pool as pool_module

    class _StubPool:
        def get_top_factors(self, limit: int = 20):
            return []

    monkeypatch.setattr(pool_module, "get_factor_pool", lambda: _StubPool())

    runner = CliRunner()
    result = runner.invoke(cli_main.app, ["factors", "--top", "5"])

    assert result.exit_code == 0
    assert "No promoted factors found" in result.stdout


def test_report_command_accepts_latest_flag_and_renders_metadata(tmp_path, monkeypatch):
    store = StateStore(tmp_path / "state_store.sqlite")
    run = store.create_run(mode="single")
    report_path = tmp_path / "reports" / "latest.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("# CIO Review\n\nall good", encoding="utf-8")
    store.append_artifact(
        ArtifactRecord(
            run_id=run.run_id,
            kind="cio_report",
            ref_id="report-001",
            path=str(report_path),
        )
    )
    monkeypatch.setattr(cli_main, "_get_state_store", lambda: store)

    runner = CliRunner()
    result = runner.invoke(cli_main.app, ["report", "--latest"])

    assert result.exit_code == 0
    assert "CIO Report" in result.stdout
    assert "report-001" in result.stdout
    assert "CIO Review" in result.stdout


def test_report_command_reports_missing_file(tmp_path, monkeypatch):
    store = StateStore(tmp_path / "state_store.sqlite")
    run = store.create_run(mode="single")
    missing_path = tmp_path / "reports" / "missing.md"
    store.append_artifact(
        ArtifactRecord(
            run_id=run.run_id,
            kind="cio_report",
            ref_id="report-missing",
            path=str(missing_path),
        )
    )
    monkeypatch.setattr(cli_main, "_get_state_store", lambda: store)

    runner = CliRunner()
    result = runner.invoke(cli_main.app, ["report"])

    assert result.exit_code == 0
    assert "报告文件不存在" in result.stdout
    assert str(missing_path) in result.stdout
