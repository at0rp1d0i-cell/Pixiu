"""
State store tests: core StateStore + API layer + orchestrator integration.

Sources:
  - tests/test_state_store.py  (original)
  - tests/test_api_state_store.py
  - tests/test_orchestrator_state_store.py
"""
import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.unit

from src.api import server
from src.control_plane.state_store import StateStore
from src.core import orchestrator
from src.core.orchestrator import coder_node, judgment_node, portfolio_node, report_node
from src.schemas.backtest import BacktestMetrics, BacktestReport
from src.schemas.control_plane import ArtifactRecord, HumanDecisionRecord, RunSnapshot
from src.schemas.research_note import FactorResearchNote
from src.schemas.state import AgentState


def test_create_update_and_get_latest_run(tmp_path):
    db_path = tmp_path / "state_store.sqlite"
    store = StateStore(db_path)

    run = store.create_run(mode="evolve")
    assert run.mode == "evolve"
    assert run.status == "running"
    assert run.current_stage == "pending"

    updated = store.update_run(
        run.run_id,
        status="completed",
        current_round=3,
        current_stage="report",
        finished_at=datetime.now(UTC),
        last_error=None,
    )
    assert updated.status == "completed"
    assert updated.current_round == 3
    assert updated.current_stage == "report"
    assert updated.finished_at is not None

    latest = store.get_latest_run()
    assert latest is not None
    assert latest.run_id == run.run_id
    assert latest.status == "completed"


def test_write_snapshot_and_get_snapshot(tmp_path):
    db_path = tmp_path / "state_store.sqlite"
    store = StateStore(db_path)
    run = store.create_run(mode="single")

    snapshot = RunSnapshot(
        run_id=run.run_id,
        approved_notes_count=2,
        backtest_reports_count=1,
        verdicts_count=1,
        awaiting_human_approval=True,
        updated_at=datetime.now(UTC),
    )
    store.write_snapshot(snapshot)

    got = store.get_snapshot(run.run_id)
    assert got is not None
    assert got.run_id == run.run_id
    assert got.approved_notes_count == 2
    assert got.awaiting_human_approval is True

    updated_snapshot = RunSnapshot(
        run_id=run.run_id,
        approved_notes_count=3,
        backtest_reports_count=2,
        verdicts_count=2,
        awaiting_human_approval=False,
        updated_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    store.write_snapshot(updated_snapshot)

    got2 = store.get_snapshot(run.run_id)
    assert got2 is not None
    assert got2.approved_notes_count == 3
    assert got2.backtest_reports_count == 2
    assert got2.awaiting_human_approval is False


def test_append_and_list_artifacts_and_reports_order(tmp_path):
    db_path = tmp_path / "state_store.sqlite"
    store = StateStore(db_path)
    run = store.create_run(mode="evolve")
    now = datetime.now(UTC)

    store.append_artifact(
        ArtifactRecord(
            run_id=run.run_id,
            kind="backtest_report",
            ref_id="bt-old",
            path="/tmp/bt-old.json",
            created_at=now - timedelta(minutes=3),
        )
    )
    store.append_artifact(
        ArtifactRecord(
            run_id=run.run_id,
            kind="cio_report",
            ref_id="cio-old",
            path="/tmp/cio-old.md",
            created_at=now - timedelta(minutes=2),
        )
    )
    store.append_artifact(
        ArtifactRecord(
            run_id=run.run_id,
            kind="cio_report",
            ref_id="cio-new",
            path="/tmp/cio-new.md",
            created_at=now - timedelta(minutes=1),
        )
    )

    all_artifacts = store.list_artifacts(run.run_id)
    assert [a.ref_id for a in all_artifacts] == ["cio-new", "cio-old", "bt-old"]

    cio_artifacts = store.list_artifacts(run.run_id, kind="cio_report")
    assert [a.ref_id for a in cio_artifacts] == ["cio-new", "cio-old"]
    assert all(a.kind == "cio_report" for a in cio_artifacts)

    reports = store.list_reports()
    assert [r.ref_id for r in reports] == ["cio-new", "cio-old"]
    assert all(r.kind == "cio_report" for r in reports)

    reports_limited = store.list_reports(limit=1)
    assert len(reports_limited) == 1
    assert reports_limited[0].ref_id == "cio-new"


def test_append_human_decision_no_crash(tmp_path):
    db_path = tmp_path / "state_store.sqlite"
    store = StateStore(db_path)
    run = store.create_run(mode="single")

    store.append_human_decision(
        HumanDecisionRecord(run_id=run.run_id, action="approve")
    )
    store.append_human_decision(
        HumanDecisionRecord(run_id=run.run_id, action="redirect:momentum")
    )
    store.append_human_decision(
        HumanDecisionRecord(run_id=run.run_id, action="stop")
    )

    # This test validates write-path coverage for the decisions table.
    assert store.get_latest_run() is not None


# ─────────────────────────────────────────────────────────
# From test_api_state_store.py
# ─────────────────────────────────────────────────────────

def test_api_status_reads_latest_run_and_snapshot(tmp_path, monkeypatch):
    store = StateStore(tmp_path / "state_store.sqlite")
    run = store.create_run(mode="single")
    store.update_run(
        run.run_id,
        status="awaiting_human_approval",
        current_round=2,
        current_stage="report",
    )
    store.write_snapshot(
        RunSnapshot(
            run_id=run.run_id,
            approved_notes_count=2,
            backtest_reports_count=1,
            verdicts_count=1,
            awaiting_human_approval=True,
            updated_at=datetime.now(UTC),
        )
    )

    monkeypatch.setattr(server, "_get_state_store", lambda: store)

    payload = server.get_status()

    assert payload["status"] == "awaiting_human_approval"
    assert payload["run_id"] == run.run_id
    assert payload["current_stage"] == "report"
    assert payload["backtest_reports_count"] == 1
    assert payload["awaiting_human_approval"] is True


def test_api_reports_reads_control_plane_artifacts(tmp_path, monkeypatch):
    store = StateStore(tmp_path / "state_store.sqlite")
    run = store.create_run(mode="evolve")
    report_path = tmp_path / "reports" / "latest.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("# CIO Report", encoding="utf-8")

    store.append_artifact(
        ArtifactRecord(
            run_id=run.run_id,
            kind="cio_report",
            ref_id="report-001",
            path=str(report_path),
        )
    )

    monkeypatch.setattr(server, "_get_state_store", lambda: store)

    payload = server.get_reports()

    assert len(payload) == 1
    assert payload[0]["id"] == "report-001"
    assert payload[0]["run_id"] == run.run_id
    assert payload[0]["path"] == str(report_path)


# ─────────────────────────────────────────────────────────
# From test_orchestrator_state_store.py
# ─────────────────────────────────────────────────────────

class _StubPoolOrch:
    def __init__(self):
        self.registered: list[dict] = []

    def get_passed_factors(self, island: str | None = None, limit: int = 20):
        return []

    def register_factor(self, report, verdict, risk_report, hypothesis: str = ""):
        self.registered.append(
            {
                "report": report,
                "verdict": verdict,
                "risk_report": risk_report,
                "hypothesis": hypothesis,
            }
        )


def _make_orch_note() -> FactorResearchNote:
    return FactorResearchNote(
        note_id="momentum_20260309_01",
        island="momentum",
        iteration=1,
        hypothesis="资金流持续推动短期趋势延续。",
        economic_intuition="趋势延续在高流动性资产中更稳定。",
        proposed_formula="$close",
        final_formula="$close",
        exploration_questions=[],
        risk_factors=[],
        market_context_date="2026-03-09",
        status="ready_for_backtest",
    )


def _make_orch_report(note: FactorResearchNote) -> BacktestReport:
    return BacktestReport(
        report_id=f"report-{note.note_id}",
        note_id=note.note_id,
        factor_id=note.note_id,
        island=note.island,
        formula=note.final_formula or note.proposed_formula,
        metrics=BacktestMetrics(
            sharpe=3.1,
            annualized_return=0.22,
            max_drawdown=0.12,
            ic_mean=0.04,
            ic_std=0.03,
            icir=0.65,
            turnover_rate=0.18,
        ),
        passed=True,
        status="success",
        execution_time_seconds=1.2,
        qlib_output_raw="BACKTEST_RESULT_JSON:{}",
        error_message=None,
    )


def test_orchestrator_writes_state_store_snapshot_and_report_artifact(tmp_path, monkeypatch):
    db_path = tmp_path / "state_store.sqlite"
    store = StateStore(db_path)
    run = store.create_run(mode="single")
    note = _make_orch_note()
    initial_state = AgentState(current_round=1, approved_notes=[note], backtest_reports=[])
    expected_report = _make_orch_report(note)
    pool = _StubPoolOrch()

    monkeypatch.setattr(orchestrator, "get_state_store", lambda: store)
    monkeypatch.setattr(orchestrator, "_current_run_id", run.run_id)
    monkeypatch.setattr(orchestrator, "REPORTS_DIR", tmp_path / "reports")

    with patch("src.execution.coder.Coder") as mock_coder_cls, patch(
        "src.core.orchestrator.get_factor_pool", return_value=pool
    ):
        mock_coder = mock_coder_cls.return_value
        mock_coder.run_backtest = AsyncMock(return_value=expected_report)

        stage4 = coder_node(initial_state)
        state_after_stage4 = initial_state.model_copy(update=stage4)

        stage5a = judgment_node(state_after_stage4)
        state_after_judgment = state_after_stage4.model_copy(update=stage5a)

        stage5b = portfolio_node(state_after_judgment)
        state_after_portfolio = state_after_judgment.model_copy(update=stage5b)

        stage5c = report_node(state_after_portfolio)
        final_state = state_after_portfolio.model_copy(update=stage5c)

    latest_run = store.get_latest_run()
    assert latest_run is not None
    assert latest_run.run_id == run.run_id
    assert latest_run.current_stage == orchestrator.NODE_REPORT
    assert latest_run.status == "awaiting_human_approval"

    snapshot = store.get_snapshot(run.run_id)
    assert snapshot is not None
    assert snapshot.backtest_reports_count == 1
    assert snapshot.verdicts_count == 1
    assert snapshot.awaiting_human_approval is True

    reports = store.list_reports(limit=10)
    assert len(reports) == 1
    assert reports[0].kind == "cio_report"
    assert reports[0].ref_id == final_state.cio_report.report_id
    assert reports[0].path.endswith(".md")
    assert (tmp_path / "reports" / run.run_id / f"{final_state.cio_report.report_id}.md").exists()
