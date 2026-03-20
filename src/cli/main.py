"""
Pixiu v2 Terminal CLI
Typer + Rich 命令行界面：启动系统、审批因子、查看状态

命令：
  pixiu run     ← 启动进化循环或单次调试
  pixiu status  ← 查看当前状态
  pixiu factors ← 查看因子排行榜
  pixiu approve ← 批准当前 CIO 报告
  pixiu redirect← 切换 Island 焦点
  pixiu stop    ← 停止循环
  pixiu report  ← 查看最新 CIO 报告
"""
import asyncio
import logging
import os
import sys
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Awaitable, TypeVar

import typer
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

from src.cli.progress import (
    RunProgressTracker,
    build_run_progress_panel,
    load_run_state,
)

app = typer.Typer(
    name="pixiu",
    help="Pixiu v2 - 自主 AI 量化研究平台",
    no_args_is_help=True,
)
console = Console()
T = TypeVar("T")
_LIVE_LOG_FILE: Path | None = None


def _get_state_store():
    from src.control_plane.state_store import get_state_store

    return get_state_store()


def _get_logs_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "logs"


def _configure_tty_live_logging() -> Path:
    """Route noisy runtime logs to a file so Rich Live owns the terminal."""
    global _LIVE_LOG_FILE

    log_dir = _get_logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"pixiu_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    root_logger = logging.getLogger()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    for handler in list(root_logger.handlers):
        if type(handler) is logging.StreamHandler:
            root_logger.removeHandler(handler)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.INFO)

    os.environ.setdefault("PIXIU_MCP_LOG_LEVEL", "WARNING")
    _LIVE_LOG_FILE = log_path
    return log_path


@app.command()
def run(
    mode: str = typer.Option("evolve", "--mode", "-m", help="evolve | single"),
    rounds: int = typer.Option(20, "--rounds", "-r", help="进化轮次（仅 evolve 模式）"),
    island: str = typer.Option("momentum", "--island", "-i", help="指定 Island（仅 single 模式）"),
    islands: str = typer.Option(None, "--islands", help="逗号分隔的 Island 列表（evolve 模式）"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细日志"),
):
    """启动 Pixiu 研究循环。"""
    import logging
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    from src.core.orchestrator import run_evolve, run_single

    if not sys.stdout.isatty():
        console.print(Panel(
            f"[bold cyan]Pixiu v2 启动[/bold cyan]\n"
            f"模式：[yellow]{mode}[/yellow]  |  轮次：[yellow]{rounds}[/yellow]  |  Island：[yellow]{island}[/yellow]",
            title="🦅 Pixiu Quantitative Research",
            border_style="cyan",
        ))

    if mode == "single":
        _run_with_progress(run_single(island=island), total_rounds=1)
    else:
        island_list = islands.split(",") if islands else None
        _run_with_progress(run_evolve(rounds=rounds, islands=island_list), total_rounds=rounds)


@app.command()
def status():
    """查看当前系统状态（优先从 control-plane state_store 读取）。"""
    try:
        store = _get_state_store()
        run = store.get_latest_run()
        snapshot = store.get_snapshot(run.run_id) if run else None
    except Exception as e:
        console.print(f"[red]读取状态失败: {e}[/red]")
        return

    if run is None:
        console.print("[yellow]暂无运行中的实验记录[/yellow]")
        return

    table = Table(title="Pixiu 运行状态", border_style="cyan")
    table.add_column("项目", style="bold")
    table.add_column("值", style="green")

    table.add_row("Run ID", run.run_id)
    table.add_row("模式", run.mode)
    table.add_row("状态", run.status)
    table.add_row("当前阶段", run.current_stage)
    table.add_row("当前轮次", str(run.current_round))
    table.add_row("等待审批", "是" if snapshot and snapshot.awaiting_human_approval else "否")
    table.add_row("已批准 Notes", str(snapshot.approved_notes_count if snapshot else 0))
    table.add_row("回测报告数", str(snapshot.backtest_reports_count if snapshot else 0))
    table.add_row("Verdict 数", str(snapshot.verdicts_count if snapshot else 0))
    table.add_row("最后错误", run.last_error or "—")

    console.print(table)


@app.command()
def factors(
    top: int = typer.Option(10, "--top", "-n", help="显示前 N 个"),
    island: str = typer.Option(None, "--island", "-i", help="按 Island 过滤"),
):
    """查看因子排行榜（按 Sharpe 降序）。"""
    from src.factor_pool.pool import get_factor_pool

    pool = get_factor_pool()
    results = pool.get_top_factors(limit=top * 3)  # 多取再过滤
    if island:
        results = [r for r in results if r.get("island") == island]
    results = results[:top]

    if not results:
        console.print("[yellow]暂无已注册因子[/yellow]")
        return

    table = Table(title=f"Top {top} 因子排行榜", border_style="green")
    table.add_column("Island")
    table.add_column("Sharpe", justify="right")
    table.add_column("IC", justify="right")
    table.add_column("ICIR", justify="right")
    table.add_column("通过", justify="center")
    table.add_column("公式（前 60 字符）")

    for f in results:
        passed_emoji = "✅" if f.get("passed") else "❌"
        table.add_row(
            f.get("island", "—"),
            f"{f.get('sharpe', 0):.2f}",
            f"{f.get('ic_mean', f.get('ic', 0)):.4f}",
            f"{f.get('icir', 0):.2f}",
            passed_emoji,
            f.get("formula", "")[:60],
        )
    console.print(table)


@app.command()
def approve():
    """批准当前 CIO 报告，系统继续运行。"""
    if _inject_human_decision("approve"):
        console.print("[bold green]✅ 已批准，系统继续运行[/bold green]")


@app.command()
def redirect(
    island: str = typer.Argument(..., help="切换到的 Island（如 momentum, volatility 等）"),
):
    """将下轮研究重点切换到指定 Island。"""
    if _inject_human_decision(f"redirect:{island}"):
        console.print(f"[bold blue]➡️  已重定向至 [yellow]{island}[/yellow] Island[/bold blue]")


@app.command()
def stop():
    """停止进化循环（当前轮完成后退出）。"""
    if _inject_human_decision("stop"):
        console.print("[bold red]⏹  系统将在当前轮次完成后停止[/bold red]")


@app.command()
def report():
    """查看最新 CIO 报告（Markdown 格式）。"""
    try:
        reports = _get_state_store().list_reports(limit=1)
    except Exception as e:
        console.print(f"[red]读取报告失败: {e}[/red]")
        return

    if not reports:
        console.print("[yellow]暂无 CIO 报告[/yellow]")
        return

    report_path = Path(reports[0].path)
    if not report_path.exists():
        console.print(f"[red]报告文件不存在: {report_path}[/red]")
        return

    console.print(Markdown(report_path.read_text(encoding="utf-8")))


def _inject_human_decision(decision: str) -> bool:
    """向 control plane 追加 human_decision，供 human_gate 消费。"""
    try:
        store = _get_state_store()
        run = store.get_latest_run()
        if run is None:
            console.print("[red]⚠️  无正在运行的实验[/red]")
            return False

        snapshot = store.get_snapshot(run.run_id)
        if snapshot is None or not snapshot.awaiting_human_approval:
            console.print("[red]⚠️  当前没有等待审批的实验[/red]")
            return False

        from src.schemas.control_plane import HumanDecisionRecord

        store.append_human_decision(
            HumanDecisionRecord(run_id=run.run_id, action=decision)
        )
        return True
    except Exception as e:
        console.print(f"[red]注入失败: {e}[/red]")
        return False


def _run_with_progress(coro: Awaitable[T], total_rounds: int | None = None) -> T:
    """Run an async Pixiu command with optional Rich live progress."""
    if not sys.stdout.isatty():
        return asyncio.run(coro)

    async def _runner() -> T:
        log_path = _configure_tty_live_logging()
        task = asyncio.create_task(coro)
        tracker = RunProgressTracker()

        with Live(console=console, refresh_per_second=4, transient=True) as live:
            while True:
                with suppress(Exception):
                    store = _get_state_store()
                    run, snapshot = load_run_state(store)
                    if run is not None:
                        view = tracker.observe(
                            run,
                            snapshot,
                            total_rounds=total_rounds,
                        )
                        live.update(build_run_progress_panel(view), refresh=True)

                done, _ = await asyncio.wait({task}, timeout=0.5)
                if task in done:
                    result = await task
                    with suppress(Exception):
                        store = _get_state_store()
                        run, snapshot = load_run_state(store)
                        if run is not None:
                            view = tracker.observe(
                                run,
                                snapshot,
                                total_rounds=total_rounds,
                            )
                            live.update(build_run_progress_panel(view), refresh=True)
                    console.print(f"[dim]Run log saved to {log_path}[/dim]")
                    return result

    return asyncio.run(_runner())


def main():
    """CLI 入口（供 pyproject.toml [project.scripts] 注册）。"""
    app()


if __name__ == "__main__":
    main()
