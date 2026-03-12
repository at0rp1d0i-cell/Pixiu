import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.agents.cio_report_renderer import CIOReportRenderer
from src.agents.factor_pool_writer import FactorPoolWriter
from src.agents.judgment import Critic, PortfolioManager, ReportWriter, RiskAuditor
from src.execution.coder import Coder
from src.execution.docker_runner import ExecutionResult
from src.factor_pool.pool import FactorPool
from src.schemas.research_note import FactorResearchNote
from src.schemas.state import AgentState


def _make_note() -> FactorResearchNote:
    return FactorResearchNote(
        note_id="momentum_20260312_01",
        island="momentum",
        iteration=1,
        hypothesis="近20日价格动量在高流动性股票池中延续。",
        economic_intuition="资金持续流入会强化短期趋势。",
        proposed_formula="Ref($close, 20) / $close - 1",
        final_formula="Ref($close, 20) / $close - 1",
        exploration_questions=[],
        risk_factors=["市场风格切换"],
        market_context_date="2026-03-12",
        universe="csi300",
        backtest_start="2021-06-01",
        backtest_end="2023-12-31",
    )


def _make_exec_result() -> ExecutionResult:
    stdout = "BACKTEST_RESULT_JSON:" + json.dumps(
        {
            "sharpe": 3.1,
            "annualized_return": 0.22,
            "max_drawdown": 0.12,
            "ic_mean": 0.04,
            "ic_std": 0.03,
            "icir": 0.65,
            "turnover_rate": 0.18,
            "error": None,
        }
    )
    return ExecutionResult(
        success=True,
        stdout=stdout,
        stderr="",
        returncode=0,
        duration_seconds=1.2,
    )


def test_stage45_golden_path_runs_end_to_end(tmp_path):
    note = _make_note()
    pool = FactorPool(db_path=str(tmp_path / "pool"))
    exec_result = _make_exec_result()

    with patch("src.execution.coder.DockerRunner.run_python", new=AsyncMock(return_value=exec_result)):
        report = asyncio.run(Coder().run_backtest(note))

    assert report.run_id is not None
    assert report.factor_id == note.note_id
    assert report.passed is True
    assert report.status == "success"
    assert report.execution_meta is not None
    assert report.factor_spec is not None
    assert report.artifacts is not None
    assert Path(report.artifacts.stdout_path).exists()
    assert Path(report.artifacts.stderr_path).exists()
    assert Path(report.artifacts.script_path).exists()

    verdict = asyncio.run(Critic().evaluate(report))
    assert verdict.overall_passed is True
    assert verdict.decision == "promote"
    assert verdict.factor_id == report.factor_id

    risk_report = asyncio.run(RiskAuditor(pool).audit(report))
    assert risk_report.factor_id == report.factor_id

    pool.register_factor(report=report, verdict=verdict, risk_report=risk_report, hypothesis=note.hypothesis)
    passed_factors = pool.get_passed_factors(island=note.island, limit=10)
    assert len(passed_factors) == 1
    assert passed_factors[0]["formula"] == report.formula

    allocation = asyncio.run(
        PortfolioManager(factor_pool=pool).rebalance(
            AgentState(
                current_round=1,
                backtest_reports=[report],
                critic_verdicts=[verdict],
                risk_audit_reports=[risk_report],
            )
        )
    )
    assert allocation.total_factors == 1

    state = AgentState(
        current_round=1,
        backtest_reports=[report],
        critic_verdicts=[verdict],
        risk_audit_reports=[risk_report],
        portfolio_allocation=allocation,
    )
    cio_report = asyncio.run(ReportWriter().generate_cio_report(state))
    assert "CIO Review" in cio_report.full_report_markdown
    assert report.factor_id in cio_report.full_report_markdown
    assert "decision=promote" in cio_report.full_report_markdown


def test_teammate_writer_and_renderer_stay_compatible_with_current_contract(tmp_path):
    note = _make_note()
    pool = FactorPool(db_path=str(tmp_path / "pool"))
    exec_result = _make_exec_result()

    with patch("src.execution.coder.DockerRunner.run_python", new=AsyncMock(return_value=exec_result)):
        report = asyncio.run(Coder().run_backtest(note))

    verdict = asyncio.run(Critic().evaluate(report))

    writer = FactorPoolWriter(pool)
    factor_id = writer.write_record(report, verdict)
    assert factor_id.startswith(note.island)

    rows = pool._collection.get(ids=[factor_id], include=["metadatas", "documents"])
    assert rows["ids"] == [factor_id]
    assert rows["metadatas"][0]["decision"] == verdict.decision

    markdown = CIOReportRenderer.render(report, verdict, factor_id)
    assert "# CIO Review:" in markdown
    assert factor_id in markdown
    assert verdict.decision.upper() in markdown
