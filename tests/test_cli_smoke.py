from __future__ import annotations

import pytest
from typer.testing import CliRunner

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


def test_approve_command_calls_inject_helper(monkeypatch):
    called: list[str] = []

    monkeypatch.setattr(
        cli_main,
        "_inject_human_decision",
        lambda decision: called.append(decision) or True,
    )

    runner = CliRunner()
    result = runner.invoke(cli_main.app, ["approve"])

    assert result.exit_code == 0
    assert called == ["approve"]
    assert "已批准" in result.stdout


def test_approve_command_stays_quiet_when_injection_fails(monkeypatch):
    monkeypatch.setattr(cli_main, "_inject_human_decision", lambda decision: False)

    runner = CliRunner()
    result = runner.invoke(cli_main.app, ["approve"])

    assert result.exit_code == 0
    assert "已批准" not in result.stdout
    assert result.stdout.strip() == ""
