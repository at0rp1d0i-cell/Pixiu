"""
Stage 4b: Coder - 确定性 Qlib 回测执行器
按照 v2_stage45_golden_path.md 规格实现
"""
import uuid
import json
import os
from pathlib import Path
from datetime import datetime, date
from src.schemas.research_note import FactorResearchNote
from src.schemas.backtest import (
    BacktestReport, BacktestMetrics, ExecutionMeta,
    FactorSpecSnapshot, ArtifactRefs
)
from src.execution.docker_runner import DockerRunner
import logging

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).parent / "templates" / "qlib_backtest.py.tpl"
ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "data" / "artifacts"

class Coder:
    """
    确定性 Qlib 回测执行器（v2 Golden Path）

    职责：
    1. 接收 FactorResearchNote.final_formula
    2. 填充标准回测模板
    3. 在 Docker 沙箱执行
    4. 解析为结构化 BacktestReport

    不调用任何 LLM，不做任何推理。
    """
    def __init__(self):
        self.runner = DockerRunner()
        self.template = TEMPLATE_PATH.read_text(encoding="utf-8")
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    async def run_backtest(self, note: FactorResearchNote) -> BacktestReport:
        """执行回测的唯一入口"""
        run_id = str(uuid.uuid4())
        report_id = str(uuid.uuid4())

        # Step 1: Compile - 准备执行包
        try:
            execution_bundle = self._compile(note, run_id)
        except Exception as e:
            logger.error(f"[Coder] Compile 失败: {e}")
            return self._create_failure_report(
                report_id=report_id,
                run_id=run_id,
                note=note,
                failure_stage="compile",
                failure_reason=str(e),
            )

        # Step 2: Run - Docker 执行
        try:
            exec_result = await self.runner.run_python(
                script=execution_bundle["script"],
                timeout_seconds=600,
            )
        except Exception as e:
            logger.error(f"[Coder] Run 失败: {e}")
            return self._create_failure_report(
                report_id=report_id,
                run_id=run_id,
                note=note,
                failure_stage="run",
                failure_reason=str(e),
            )

        # Step 3: 落盘原始产物
        artifacts = self._save_artifacts(run_id, execution_bundle, exec_result)

        # Step 4: Parse - 解析为 BacktestReport
        return self._parse_result(
            report_id=report_id,
            run_id=run_id,
            note=note,
            exec_result=exec_result,
            artifacts=artifacts,
        )

    def _compile(self, note: FactorResearchNote, run_id: str) -> dict:
        """Step 1: 编译执行包（确定性）"""
        formula = note.final_formula or note.proposed_formula

        if not formula:
            raise ValueError("final_formula 和 proposed_formula 均为空")

        # 填充模板（防御性处理特殊字符）
        script = self.template.replace("{formula}", formula) \
                              .replace("{universe}", note.universe) \
                              .replace("{start_date}", note.backtest_start) \
                              .replace("{end_date}", note.backtest_end) \
                              .replace("{topk}", "50")

        return {
            "run_id": run_id,
            "note_id": note.note_id,
            "formula": formula,
            "script": script,
            "config": {
                "universe": note.universe,
                "start_date": note.backtest_start,
                "end_date": note.backtest_end,
                "topk": 50,
            }
        }

    def _save_artifacts(self, run_id: str, bundle: dict, exec_result) -> ArtifactRefs:
        """Step 3: 落盘原始产物"""
        run_dir = ARTIFACTS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # 保存脚本
        script_path = run_dir / "script.py"
        script_path.write_text(bundle["script"], encoding="utf-8")

        # 保存 stdout
        stdout_path = run_dir / "stdout.txt"
        stdout_path.write_text(exec_result.stdout, encoding="utf-8")

        # 保存 stderr
        stderr_path = run_dir / "stderr.txt"
        stderr_path.write_text(exec_result.stderr, encoding="utf-8")

        return ArtifactRefs(
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            script_path=str(script_path),
        )

    def _parse_result(
        self,
        report_id: str,
        run_id: str,
        note: FactorResearchNote,
        exec_result,
        artifacts: ArtifactRefs,
    ) -> BacktestReport:
        """Step 4: 解析为 BacktestReport"""

        # 执行失败
        if not exec_result.success:
            return self._create_failure_report(
                report_id=report_id,
                run_id=run_id,
                note=note,
                failure_stage="run",
                failure_reason=exec_result.stderr[:500] if exec_result.stderr else "Unknown error",
                artifacts=artifacts,
                runtime_seconds=exec_result.duration_seconds,
            )

        # 解析 JSON 输出
        raw_metrics = None
        for line in exec_result.stdout.split("\n"):
            if line.startswith("BACKTEST_RESULT_JSON:"):
                try:
                    raw_metrics = json.loads(line.replace("BACKTEST_RESULT_JSON:", ""))
                    break
                except json.JSONDecodeError as e:
                    logger.error(f"[Coder] JSON 解析失败: {e}")

        if raw_metrics is None:
            return self._create_failure_report(
                report_id=report_id,
                run_id=run_id,
                note=note,
                failure_stage="parse",
                failure_reason="输出中未找到 BACKTEST_RESULT_JSON 标记",
                artifacts=artifacts,
                runtime_seconds=exec_result.duration_seconds,
            )

        # 检查执行错误
        if raw_metrics.get("error"):
            return self._create_failure_report(
                report_id=report_id,
                run_id=run_id,
                note=note,
                failure_stage="run",
                failure_reason=raw_metrics["error"],
                artifacts=artifacts,
                runtime_seconds=exec_result.duration_seconds,
            )

        # 构建成功的 BacktestReport
        metrics = BacktestMetrics(
            sharpe=raw_metrics.get("sharpe"),
            annual_return=raw_metrics.get("annualized_return"),
            max_drawdown=raw_metrics.get("max_drawdown"),
            ic_mean=raw_metrics.get("ic_mean"),
            ic_std=raw_metrics.get("ic_std"),
            icir=raw_metrics.get("icir"),
            turnover=raw_metrics.get("turnover_rate"),
            coverage=None,  # 当前模板未计算
        )

        execution_meta = ExecutionMeta(
            universe=note.universe,
            start_date=date.fromisoformat(note.backtest_start),
            end_date=date.fromisoformat(note.backtest_end),
            runtime_seconds=exec_result.duration_seconds,
            timestamp_utc=datetime.utcnow(),
        )

        factor_spec = FactorSpecSnapshot(
            formula=note.final_formula or note.proposed_formula,
            hypothesis=note.hypothesis,
            economic_rationale=note.economic_intuition,
        )

        return BacktestReport(
            report_id=report_id,
            run_id=run_id,
            note_id=note.note_id,
            island_id=note.island,
            status="success",
            execution_meta=execution_meta,
            factor_spec=factor_spec,
            metrics=metrics,
            artifacts=artifacts,
        )

    def _create_failure_report(
        self,
        report_id: str,
        run_id: str,
        note: FactorResearchNote,
        failure_stage: str,
        failure_reason: str,
        artifacts: ArtifactRefs = None,
        runtime_seconds: float = 0.0,
    ) -> BacktestReport:
        """创建失败报告"""

        if artifacts is None:
            # 创建空的 artifacts
            run_dir = ARTIFACTS_DIR / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            artifacts = ArtifactRefs(
                stdout_path=str(run_dir / "stdout.txt"),
                stderr_path=str(run_dir / "stderr.txt"),
                script_path=str(run_dir / "script.py"),
            )

        return BacktestReport(
            report_id=report_id,
            run_id=run_id,
            note_id=note.note_id,
            island_id=note.island,
            status="failed",
            failure_stage=failure_stage,
            failure_reason=failure_reason,
            execution_meta=ExecutionMeta(
                universe=note.universe,
                start_date=date.fromisoformat(note.backtest_start),
                end_date=date.fromisoformat(note.backtest_end),
                runtime_seconds=runtime_seconds,
                timestamp_utc=datetime.utcnow(),
            ),
            factor_spec=FactorSpecSnapshot(
                formula=note.final_formula or note.proposed_formula or "",
                hypothesis=note.hypothesis,
                economic_rationale=note.economic_intuition,
            ),
            metrics=BacktestMetrics(),
            artifacts=artifacts,
        )
