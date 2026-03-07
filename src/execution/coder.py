import uuid
import json
from pathlib import Path
from src.schemas.research_note import FactorResearchNote
from src.schemas.backtest import BacktestReport, BacktestMetrics
from src.execution.docker_runner import DockerRunner

TEMPLATE_PATH = Path(__file__).parent / "templates" / "qlib_backtest.py.tpl"

class Coder:
    """
    确定性 Qlib 回测执行器。
    不调用任何 LLM。接收公式 → 生成脚本 → 执行 → 返回结构化结果。
    """
    def __init__(self):
        self.runner = DockerRunner()
        self.template = TEMPLATE_PATH.read_text(encoding="utf-8")

    async def run_backtest(self, note: FactorResearchNote) -> BacktestReport:
        formula = note.final_formula or note.proposed_formula
        factor_id = note.note_id  # 使用 note_id 作为 factor_id

        # 填充模板
        # 将由于花括号引起的 format 错误防御性处理，确保 formula 内部如果包含大括号不会报错
        # 由于我们模板用的是具名参数，安全起见也可以只替换我们关心的字段：
        script = self.template.replace("{formula}", formula.replace('\\', '\\\\').replace('"', '\\"'))\
                              .replace("{universe}", note.universe)\
                              .replace("{start_date}", note.backtest_start)\
                              .replace("{end_date}", note.backtest_end)\
                              .replace("{topk}", "50")

        # Docker 执行
        exec_result = await self.runner.run_python(
            script=script,
            timeout_seconds=600,
        )

        # 解析结果
        return self._parse_result(
            exec_result=exec_result,
            note=note,
            factor_id=factor_id,
            formula=formula,
        )

    def _parse_result(self, exec_result, note, factor_id, formula) -> BacktestReport:
        if not exec_result.success:
            return BacktestReport(
                report_id=str(uuid.uuid4()),
                note_id=note.note_id,
                factor_id=factor_id,
                island=note.island,
                formula=formula,
                metrics=BacktestMetrics(
                    sharpe=0, annualized_return=0, max_drawdown=0,
                    ic_mean=0, ic_std=0, icir=0, turnover_rate=0,
                ),
                passed=False,
                execution_time_seconds=exec_result.duration_seconds,
                qlib_output_raw=exec_result.stderr[:2000] if exec_result.stderr else "Unkown Error",
                error_message=f"执行失败: {(exec_result.stderr or exec_result.stdout)[:500]}",
            )

        # 从 stdout 提取 JSON
        raw = None
        for line in exec_result.stdout.split("\n"):
            if line.startswith("BACKTEST_RESULT_JSON:"):
                raw = json.loads(line.replace("BACKTEST_RESULT_JSON:", ""))
                break
        
        if raw is None:
            return BacktestReport(
                report_id=str(uuid.uuid4()),
                note_id=note.note_id,
                factor_id=factor_id,
                island=note.island,
                formula=formula,
                metrics=BacktestMetrics(
                    sharpe=0, annualized_return=0, max_drawdown=0,
                    ic_mean=0, ic_std=0, icir=0, turnover_rate=0,
                ),
                passed=False,
                execution_time_seconds=exec_result.duration_seconds,
                qlib_output_raw=exec_result.stdout[:2000] if exec_result.stdout else "Empty stdout",
                error_message="输出中未找到 BACKTEST_RESULT_JSON 标记",
            )

        error_msg = raw.get("error")

        metrics = BacktestMetrics(
            sharpe=raw["sharpe"],
            annualized_return=raw["annualized_return"],
            max_drawdown=raw["max_drawdown"],
            ic_mean=raw["ic_mean"],
            ic_std=raw["ic_std"],
            icir=raw["icir"],
            turnover_rate=raw["turnover_rate"],
        )

        from src.schemas.thresholds import THRESHOLDS
        passed = (
            metrics.sharpe >= THRESHOLDS.min_sharpe
            and metrics.ic_mean >= THRESHOLDS.min_ic_mean
            and metrics.icir >= THRESHOLDS.min_icir
            and metrics.turnover_rate <= THRESHOLDS.max_turnover_rate
            and error_msg is None
        )

        return BacktestReport(
            report_id=str(uuid.uuid4()),
            note_id=note.note_id,
            factor_id=factor_id,
            island=note.island,
            formula=formula,
            metrics=metrics,
            passed=passed,
            execution_time_seconds=exec_result.duration_seconds,
            qlib_output_raw=exec_result.stdout[:2000],
            error_message=error_msg,
        )
