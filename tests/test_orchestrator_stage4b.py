from unittest.mock import AsyncMock, patch

from src.core.orchestrator import coder_node
from src.schemas.backtest import BacktestMetrics, BacktestReport
from src.schemas.research_note import FactorResearchNote
from src.schemas.state import AgentState


def _make_note(note_id: str) -> FactorResearchNote:
    return FactorResearchNote(
        note_id=note_id,
        island="momentum",
        iteration=1,
        hypothesis="h",
        economic_intuition="e",
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
            sharpe=1.0,
            annualized_return=0.1,
            max_drawdown=0.2,
            ic_mean=0.01,
            ic_std=0.02,
            icir=0.5,
            turnover_rate=0.3,
        ),
        passed=True,
        execution_time_seconds=1.0,
        qlib_output_raw="BACKTEST_RESULT_JSON:{}",
        error_message=None,
    )


def test_orchestrator_stage4b_uses_execution_coder_path():
    note = _make_note("momentum_20260309_01")
    state = AgentState(approved_notes=[note], backtest_reports=[])
    expected_report = _make_report(note)

    with patch("src.execution.coder.Coder") as mock_coder_cls:
        mock_coder = mock_coder_cls.return_value
        mock_coder.run_backtest = AsyncMock(return_value=expected_report)

        result = coder_node(state)

    mock_coder_cls.assert_called_once()
    mock_coder.run_backtest.assert_awaited_once_with(note)
    assert result["backtest_reports"] == [expected_report]
    assert result["approved_notes"][0].status == "completed"
