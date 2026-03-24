import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from src.execution.docker_runner import DockerRunner
from src.schemas.backtest import (
    ArtifactRefs,
    BacktestMetrics,
    BacktestReport,
    ExecutionMeta,
    FactorSpecSnapshot,
)
from src.schemas.research_note import FactorResearchNote
from src.schemas.thresholds import THRESHOLDS

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).parent / "templates" / "qlib_backtest.py.tpl"
ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "data" / "artifacts"


def resolve_artifacts_dir() -> Path:
    configured = os.getenv("PIXIU_ARTIFACTS_DIR")
    return Path(configured) if configured else ARTIFACTS_DIR


class Coder:
    """
    Deterministic Stage 4 executor.

    Input: FactorResearchNote.final_formula
    Output: BacktestReport
    """

    def __init__(self):
        self.runner = DockerRunner()
        try:
            self.template = TEMPLATE_PATH.read_text(encoding="utf-8")
        except FileNotFoundError as e:
            raise RuntimeError(f"Qlib backtest template not found: {TEMPLATE_PATH}") from e
        self.template_version = TEMPLATE_PATH.name
        self._artifacts_dir = resolve_artifacts_dir()
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)

    async def run_backtest(self, note: FactorResearchNote) -> BacktestReport:
        formula = note.final_formula or note.proposed_formula
        if not formula:
            return self._failure_report(
                report_id=str(uuid.uuid4()),
                run_id=str(uuid.uuid4()),
                note=note,
                formula="",
                factor_id=note.note_id,
                failure_stage="compile",
                failure_reason="missing_formula",
                error_message="final_formula 和 proposed_formula 均为空",
            )

        run_id = str(uuid.uuid4())
        report_id = str(uuid.uuid4())
        factor_id = note.note_id

        try:
            script = self._compile(note, formula)
        except Exception as exc:
            return self._failure_report(
                report_id=report_id,
                run_id=run_id,
                note=note,
                formula=formula,
                factor_id=factor_id,
                failure_stage="compile",
                failure_reason="template_render_failed",
                error_message=str(exc),
            )

        exec_result = await self.runner.run_python(script=script, timeout_seconds=600)
        artifacts = self._save_artifacts(run_id, script, exec_result.stdout, exec_result.stderr)

        return self._parse_result(
            exec_result=exec_result,
            note=note,
            factor_id=factor_id,
            formula=formula,
            report_id=report_id,
            run_id=run_id,
            artifacts=artifacts,
        )

    def _compile(self, note: FactorResearchNote, formula: str) -> str:
        escaped_formula = formula.replace("\\", "\\\\").replace('"', '\\"')
        return (
            self.template.replace("{formula}", escaped_formula)
            .replace("{universe}", note.universe)
            .replace("{start_date}", note.backtest_start)
            .replace("{end_date}", note.backtest_end)
            .replace("{topk}", str(THRESHOLDS.backtest_topk))
        )

    def _save_artifacts(
        self,
        run_id: str,
        script: str,
        stdout: str,
        stderr: str,
    ) -> ArtifactRefs:
        try:
            run_dir = self._artifacts_dir / run_id
            run_dir.mkdir(parents=True, exist_ok=True)

            script_path = run_dir / "script.py"
            stdout_path = run_dir / "stdout.txt"
            stderr_path = run_dir / "stderr.txt"

            script_path.write_text(script, encoding="utf-8")
            stdout_path.write_text(stdout or "", encoding="utf-8")
            stderr_path.write_text(stderr or "", encoding="utf-8")

            return ArtifactRefs(
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
                script_path=str(script_path),
            )
        except OSError as exc:
            logger.warning("[Coder] _save_artifacts failed for run_id=%s: %s", run_id, exc)
            return ArtifactRefs()

    def _parse_result(
        self,
        exec_result,
        note: FactorResearchNote,
        factor_id: str,
        formula: str,
        report_id: str | None = None,
        run_id: str | None = None,
        artifacts: ArtifactRefs | None = None,
    ) -> BacktestReport:
        report_id = report_id or str(uuid.uuid4())
        run_id = run_id or str(uuid.uuid4())
        artifacts = artifacts or ArtifactRefs()

        if not exec_result.success:
            return self._failure_report(
                report_id=report_id,
                run_id=run_id,
                note=note,
                formula=formula,
                factor_id=factor_id,
                failure_stage="run",
                failure_reason="execution_failed",
                error_message=f"执行失败: {(exec_result.stderr or exec_result.stdout)[:500]}",
                execution_time_seconds=exec_result.duration_seconds,
                qlib_output_raw=exec_result.stderr[:2000] if exec_result.stderr else (exec_result.stdout or ""),
                artifacts=artifacts,
            )

        raw = None
        for line in exec_result.stdout.splitlines():
            if not line.startswith("BACKTEST_RESULT_JSON:"):
                continue
            try:
                raw = json.loads(line.replace("BACKTEST_RESULT_JSON:", "", 1))
                break
            except json.JSONDecodeError as exc:
                return self._failure_report(
                    report_id=report_id,
                    run_id=run_id,
                    note=note,
                    formula=formula,
                    factor_id=factor_id,
                    failure_stage="parse",
                    failure_reason="invalid_backtest_result_json",
                    error_message=f"输出 JSON 解析失败: {exc}",
                    execution_time_seconds=exec_result.duration_seconds,
                    qlib_output_raw=exec_result.stdout[:2000],
                    artifacts=artifacts,
                )

        if raw is None:
            return self._failure_report(
                report_id=report_id,
                run_id=run_id,
                note=note,
                formula=formula,
                factor_id=factor_id,
                failure_stage="parse",
                failure_reason="missing_backtest_result_json",
                error_message="输出中未找到 BACKTEST_RESULT_JSON 标记",
                execution_time_seconds=exec_result.duration_seconds,
                qlib_output_raw=exec_result.stdout[:2000],
                artifacts=artifacts,
            )

        error_message = raw.get("error")
        metrics = BacktestMetrics(
            sharpe=raw.get("sharpe", 0.0),
            annualized_return=raw.get("annualized_return", 0.0),
            max_drawdown=raw.get("max_drawdown", 0.0),
            ic_mean=raw.get("ic_mean", 0.0),
            ic_std=raw.get("ic_std", 0.0),
            icir=raw.get("icir", 0.0),
            turnover_rate=raw.get("turnover_rate", 0.0),
            coverage=raw.get("coverage", 1.0 if error_message is None else 0.0),
        )

        passed = (
            metrics.sharpe >= THRESHOLDS.min_sharpe
            and metrics.ic_mean >= THRESHOLDS.min_ic_mean
            and metrics.icir >= THRESHOLDS.min_icir
            and metrics.turnover_rate <= THRESHOLDS.max_turnover_rate
            and (metrics.coverage or 0.0) >= THRESHOLDS.min_coverage
            and error_message is None
        )

        return BacktestReport(
            report_id=report_id,
            run_id=run_id,
            note_id=note.note_id,
            factor_id=factor_id,
            island=note.island,
            island_id=note.island,
            formula=formula,
            metrics=metrics,
            passed=passed,
            execution_succeeded=not error_message,
            status="success" if not error_message else "failed",
            failure_stage=None if not error_message else "run",
            failure_reason=None if not error_message else "backtest_error",
            execution_time_seconds=exec_result.duration_seconds,
            qlib_output_raw=exec_result.stdout[:2000],
            error_message=error_message,
            execution_meta=self._execution_meta(note, exec_result.duration_seconds),
            factor_spec=self._factor_spec(note, formula),
            artifacts=artifacts,
        )

    def _failure_report(
        self,
        report_id: str,
        run_id: str,
        note: FactorResearchNote,
        formula: str,
        factor_id: str,
        failure_stage: str,
        failure_reason: str,
        error_message: str,
        execution_time_seconds: float = 0.0,
        qlib_output_raw: str = "",
        artifacts: ArtifactRefs | None = None,
    ) -> BacktestReport:
        return BacktestReport(
            report_id=report_id,
            run_id=run_id,
            note_id=note.note_id,
            factor_id=factor_id,
            island=note.island,
            island_id=note.island,
            formula=formula,
            metrics=BacktestMetrics(
                sharpe=0.0,
                annualized_return=0.0,
                max_drawdown=0.0,
                ic_mean=0.0,
                ic_std=0.0,
                icir=0.0,
                turnover_rate=0.0,
                coverage=0.0,
            ),
            passed=False,
            execution_succeeded=False,
            status="failed",
            failure_stage=failure_stage,
            failure_reason=failure_reason,
            execution_time_seconds=execution_time_seconds,
            qlib_output_raw=qlib_output_raw,
            error_message=error_message,
            execution_meta=self._execution_meta(note, execution_time_seconds),
            factor_spec=self._factor_spec(note, formula),
            artifacts=artifacts or ArtifactRefs(),
        )

    def _execution_meta(self, note: FactorResearchNote, runtime_seconds: float) -> ExecutionMeta:
        return ExecutionMeta(
            universe=note.universe,
            benchmark=note.universe,
            start_date=note.backtest_start,
            end_date=note.backtest_end,
            runtime_seconds=runtime_seconds,
            timestamp_utc=datetime.now(UTC),
            template_version=self.template_version,
        )

    def _factor_spec(self, note: FactorResearchNote, formula: str) -> FactorSpecSnapshot:
        return FactorSpecSnapshot(
            formula=formula,
            hypothesis=note.hypothesis,
            economic_rationale=note.economic_intuition,
        )
