"""
Stage 4→5 Golden Path 集成测试
按照 v2_stage45_golden_path.md 规格实现
"""
import pytest
import asyncio
from datetime import datetime
from src.schemas.research_note import FactorResearchNote
from src.execution.coder_v2 import Coder
from src.agents.critic_v2 import Critic
from src.agents.factor_pool_writer import FactorPoolWriter
from src.agents.cio_report_renderer import CIOReportRenderer
from src.factor_pool.pool import FactorPool
from src.schemas.thresholds import THRESHOLDS


@pytest.fixture
def sample_note():
    """创建测试用的 FactorResearchNote"""
    return FactorResearchNote(
        note_id="test_momentum_20260311_001",
        island="momentum",
        iteration=1,
        hypothesis="近20日动量因子在A股市场具有显著的预测能力",
        economic_intuition="动量效应源于投资者的羊群行为和信息传播的滞后性",
        proposed_formula="Ref($close, 20) / $close - 1",
        final_formula="Ref($close, 20) / $close - 1",
        universe="csi300",
        backtest_start="2021-06-01",
        backtest_end="2023-12-31",
        expected_ic_min=0.02,
        risk_factors=["市场regime切换", "极端行情下失效"],
        market_context_date="2026-03-11",
    )


@pytest.fixture
def factor_pool(tmp_path):
    """创建临时 FactorPool"""
    return FactorPool(db_path=str(tmp_path / "test_pool"))


class TestStage45GoldenPath:
    """Stage 4→5 确定性闭环集成测试"""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        True,  # 默认跳过，需要 Docker 环境
        reason="需要 Docker 环境和 Qlib 数据"
    )
    async def test_full_pipeline_success(self, sample_note, factor_pool):
        """
        测试完整的成功路径：
        FactorResearchNote → Coder → BacktestReport → Critic → FactorPool → CIOReport
        """
        # Step 1: Coder 执行回测
        coder = Coder()
        report = await coder.run_backtest(sample_note)

        # 验证 BacktestReport 结构
        assert report.report_id is not None
        assert report.run_id is not None
        assert report.note_id == sample_note.note_id
        assert report.island_id == sample_note.island
        assert report.status in ["success", "failed", "partial"]
        assert report.execution_meta is not None
        assert report.factor_spec is not None
        assert report.metrics is not None
        assert report.artifacts is not None

        # Step 2: Critic 判定
        critic = Critic()
        verdict = critic.evaluate(report)

        # 验证 CriticVerdict 结构
        assert verdict.verdict_id is not None
        assert verdict.report_id == report.report_id
        assert verdict.note_id == sample_note.note_id
        assert verdict.decision in ["promote", "archive", "reject", "retry"]
        assert 0.0 <= verdict.score <= 1.0
        assert isinstance(verdict.passed_checks, list)
        assert isinstance(verdict.failed_checks, list)
        assert isinstance(verdict.reason_codes, list)
        assert verdict.summary is not None

        # Step 3: FactorPool 写回
        writer = FactorPoolWriter(factor_pool)
        factor_id = writer.write_record(report, verdict)

        assert factor_id is not None
        assert factor_id.startswith(sample_note.island)

        # Step 4: CIOReport 渲染
        renderer = CIOReportRenderer()
        cio_report = renderer.render(report, verdict, factor_id)

        assert "# CIO Review:" in cio_report
        assert sample_note.note_id in cio_report
        assert sample_note.island in cio_report
        assert verdict.decision.upper() in cio_report

    def test_critic_deterministic(self):
        """测试 Critic 的确定性：相同输入产生相同输出"""
        from src.schemas.backtest import (
            BacktestReport, BacktestMetrics, ExecutionMeta,
            FactorSpecSnapshot, ArtifactRefs
        )
        from datetime import date

        # 创建固定的 BacktestReport
        report = BacktestReport(
            report_id="test_report_001",
            run_id="test_run_001",
            note_id="test_note_001",
            island_id="momentum",
            status="success",
            execution_meta=ExecutionMeta(
                universe="csi300",
                start_date=date(2021, 6, 1),
                end_date=date(2023, 12, 31),
                runtime_seconds=120.5,
                timestamp_utc=datetime(2026, 3, 11, 10, 0, 0),
            ),
            factor_spec=FactorSpecSnapshot(
                formula="Ref($close, 20) / $close - 1",
                hypothesis="测试假设",
                economic_rationale="测试逻辑",
            ),
            metrics=BacktestMetrics(
                sharpe=1.5,
                annual_return=0.25,
                max_drawdown=-0.15,
                ic_mean=0.03,
                ic_std=0.05,
                icir=0.6,
                turnover=0.3,
                coverage=0.85,
            ),
            artifacts=ArtifactRefs(
                stdout_path="/tmp/stdout.txt",
                stderr_path="/tmp/stderr.txt",
                script_path="/tmp/script.py",
            ),
        )

        # 多次判定
        critic = Critic()
        verdict1 = critic.evaluate(report)
        verdict2 = critic.evaluate(report)
        verdict3 = critic.evaluate(report)

        # 验证确定性（除了 verdict_id 外，其他字段应该相同）
        assert verdict1.decision == verdict2.decision == verdict3.decision
        assert verdict1.score == verdict2.score == verdict3.score
        assert verdict1.passed_checks == verdict2.passed_checks == verdict3.passed_checks
        assert verdict1.failed_checks == verdict2.failed_checks == verdict3.failed_checks
        assert verdict1.reason_codes == verdict2.reason_codes == verdict3.reason_codes
        assert verdict1.summary == verdict2.summary == verdict3.summary

    def test_critic_threshold_boundaries(self):
        """测试 Critic 的阈值边界行为"""
        from src.schemas.backtest import (
            BacktestReport, BacktestMetrics, ExecutionMeta,
            FactorSpecSnapshot, ArtifactRefs
        )
        from datetime import date

        def create_report(sharpe, ic_mean, icir, turnover):
            return BacktestReport(
                report_id="test_report",
                run_id="test_run",
                note_id="test_note",
                island_id="momentum",
                status="success",
                execution_meta=ExecutionMeta(
                    universe="csi300",
                    start_date=date(2021, 6, 1),
                    end_date=date(2023, 12, 31),
                    runtime_seconds=120.0,
                    timestamp_utc=datetime.utcnow(),
                ),
                factor_spec=FactorSpecSnapshot(
                    formula="test",
                    hypothesis="test",
                    economic_rationale="test",
                ),
                metrics=BacktestMetrics(
                    sharpe=sharpe,
                    ic_mean=ic_mean,
                    icir=icir,
                    turnover=turnover,
                ),
                artifacts=ArtifactRefs(
                    stdout_path="/tmp/stdout.txt",
                    stderr_path="/tmp/stderr.txt",
                    script_path="/tmp/script.py",
                ),
            )

        critic = Critic()

        # 测试：所有指标刚好达标 → promote
        report_pass = create_report(
            sharpe=THRESHOLDS.min_sharpe,
            ic_mean=THRESHOLDS.min_ic_mean,
            icir=THRESHOLDS.min_icir,
            turnover=THRESHOLDS.max_turnover,
        )
        verdict_pass = critic.evaluate(report_pass)
        assert verdict_pass.decision == "promote"
        assert len(verdict_pass.failed_checks) == 0

        # 测试：Sharpe 略低于阈值 → reject 或 archive
        report_fail = create_report(
            sharpe=THRESHOLDS.min_sharpe - 0.01,
            ic_mean=THRESHOLDS.min_ic_mean,
            icir=THRESHOLDS.min_icir,
            turnover=THRESHOLDS.max_turnover,
        )
        verdict_fail = critic.evaluate(report_fail)
        assert verdict_fail.decision in ["reject", "archive"]
        assert "sharpe" in verdict_fail.failed_checks

    def test_failure_stage_classification(self):
        """测试错误分类的正确性"""
        from src.schemas.backtest import (
            BacktestReport, BacktestMetrics, ExecutionMeta,
            FactorSpecSnapshot, ArtifactRefs
        )
        from datetime import date

        def create_failure_report(failure_stage):
            return BacktestReport(
                report_id="test_report",
                run_id="test_run",
                note_id="test_note",
                island_id="momentum",
                status="failed",
                failure_stage=failure_stage,
                failure_reason="测试失败",
                execution_meta=ExecutionMeta(
                    universe="csi300",
                    start_date=date(2021, 6, 1),
                    end_date=date(2023, 12, 31),
                    runtime_seconds=0.0,
                    timestamp_utc=datetime.utcnow(),
                ),
                factor_spec=FactorSpecSnapshot(
                    formula="test",
                    hypothesis="test",
                    economic_rationale="test",
                ),
                metrics=BacktestMetrics(),
                artifacts=ArtifactRefs(
                    stdout_path="/tmp/stdout.txt",
                    stderr_path="/tmp/stderr.txt",
                    script_path="/tmp/script.py",
                ),
            )

        critic = Critic()

        # 测试各种失败阶段
        for stage in ["compile", "run", "parse", "judge"]:
            report = create_failure_report(stage)
            verdict = critic.evaluate(report)
            assert verdict.decision == "retry"
            assert len(verdict.reason_codes) > 0

    def test_cio_report_rendering(self):
        """测试 CIOReport 模板渲染"""
        from src.schemas.backtest import (
            BacktestReport, BacktestMetrics, ExecutionMeta,
            FactorSpecSnapshot, ArtifactRefs
        )
        from src.schemas.judgment import CriticVerdict
        from datetime import date

        report = BacktestReport(
            report_id="test_report_001",
            run_id="test_run_001",
            note_id="test_note_001",
            island_id="momentum",
            status="success",
            execution_meta=ExecutionMeta(
                universe="csi300",
                start_date=date(2021, 6, 1),
                end_date=date(2023, 12, 31),
                runtime_seconds=120.5,
                timestamp_utc=datetime(2026, 3, 11, 10, 0, 0),
            ),
            factor_spec=FactorSpecSnapshot(
                formula="Ref($close, 20) / $close - 1",
                hypothesis="测试假设",
                economic_rationale="测试逻辑",
            ),
            metrics=BacktestMetrics(
                sharpe=1.5,
                annual_return=0.25,
                max_drawdown=-0.15,
                ic_mean=0.03,
                icir=0.6,
                turnover=0.3,
            ),
            artifacts=ArtifactRefs(
                stdout_path="/tmp/stdout.txt",
                stderr_path="/tmp/stderr.txt",
                script_path="/tmp/script.py",
            ),
        )

        verdict = CriticVerdict(
            verdict_id="test_verdict_001",
            report_id="test_report_001",
            note_id="test_note_001",
            decision="promote",
            score=0.85,
            passed_checks=["sharpe", "ic_mean", "icir"],
            failed_checks=[],
            summary="因子通过所有检查",
            reason_codes=[],
        )

        renderer = CIOReportRenderer()
        cio_report = renderer.render(report, verdict, "momentum_test_001")

        # 验证报告包含关键信息
        assert "# CIO Review:" in cio_report
        assert "momentum_test_001" in cio_report
        assert "## Factor Summary" in cio_report
        assert "## Backtest Context" in cio_report
        assert "## Core Metrics" in cio_report
        assert "## Verdict" in cio_report
        assert "## Artifact References" in cio_report
        assert "PROMOTE" in cio_report
        assert "0.850" in cio_report
