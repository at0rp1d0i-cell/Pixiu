import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.unit

from src.control_plane.state_store import StateStore
from src.core import orchestrator
from src.core.orchestrator import coder_node, judgment_node, portfolio_node, report_node
from src.schemas.backtest import BacktestMetrics, BacktestReport
from src.schemas.research_note import FactorResearchNote
from src.schemas.state import AgentState


class _StubPool:
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


def _make_note() -> FactorResearchNote:
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


def _make_report(note: FactorResearchNote) -> BacktestReport:
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
    note = _make_note()
    initial_state = AgentState(current_round=1, approved_notes=[note], backtest_reports=[])
    expected_report = _make_report(note)
    pool = _StubPool()

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
