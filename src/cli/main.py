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
from datetime import UTC, datetime
from pathlib import Path
from typing import Awaitable, TypeVar

import typer
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

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


def _build_key_value_panel(
    title: str,
    rows: list[tuple[str, str]],
    *,
    border_style: str = "cyan",
) -> Panel:
    table = Table.grid(expand=True)
    table.add_column(style="bold cyan", ratio=1)
    table.add_column(ratio=3)
    for label, value in rows:
        table.add_row(label, value or "—")
    return Panel(table, title=title, border_style=border_style)


def _format_timestamp(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _short_id(value: str | None, *, prefix: int = 10, suffix: int = 6) -> str:
    if not value:
        return "—"
    if len(value) <= prefix + suffix + 3:
        return value
    return f"{value[:prefix]}...{value[-suffix:]}"


def _build_command_hint_panel() -> Panel:
    return Panel(
        "Use `pixiu approve` to continue, `pixiu redirect <island>` to redirect focus, "
        "or `pixiu stop` to stop after the current round.",
        title="Human Gate",
        border_style="yellow",
    )


def _build_run_launch_panel(
    *,
    mode: str,
    rounds: int,
    island: str | None,
    islands: list[str] | None,
    verbose: bool,
) -> Panel:
    target = island if mode == "single" else ", ".join(islands or ["scheduler default"])
    subtitle = (
        f"Mode: {mode}\n"
        f"Rounds: {rounds}\n"
        f"Target: {target}\n"
        f"Verbose: {'yes' if verbose else 'no'}"
    )
    return Panel(subtitle, title="Pixiu CLI", border_style="cyan")


def _render_status_view(run, snapshot, latest_report) -> Group:
    run_panel = _build_key_value_panel(
        "Run",
        [
            ("Run ID", run.run_id),
            ("Mode", run.mode),
            ("Status", run.status),
            ("Stage", run.current_stage),
            ("Round", str(run.current_round)),
            ("Started", _format_timestamp(run.started_at)),
            ("Finished", _format_timestamp(run.finished_at)),
            ("Last Error", run.last_error or "—"),
        ],
        border_style="cyan",
    )

    snapshot_panel = _build_key_value_panel(
        "Snapshot",
        [
            ("Awaiting Approval", "yes" if snapshot and snapshot.awaiting_human_approval else "no"),
            ("Approved Notes", str(snapshot.approved_notes_count if snapshot else 0)),
            ("Backtest Reports", str(snapshot.backtest_reports_count if snapshot else 0)),
            ("Verdicts", str(snapshot.verdicts_count if snapshot else 0)),
            ("Updated", _format_timestamp(snapshot.updated_at if snapshot else None)),
        ],
        border_style="green",
    )

    if latest_report is None:
        report_panel = Panel("No CIO report found.", title="Latest Report", border_style="magenta")
    else:
        report_panel = _build_key_value_panel(
            "Latest Report",
            [
                ("Report ID", latest_report.ref_id),
                ("Run ID", latest_report.run_id),
                ("Created", _format_timestamp(latest_report.created_at)),
                ("Path", latest_report.path),
            ],
            border_style="magenta",
        )

    renderables: list[object] = [
        Panel(
            Text("Pixiu Runtime Status", style="bold cyan"),
            subtitle=f"Latest run {_short_id(run.run_id)}",
            border_style="cyan",
        ),
        Columns([run_panel, snapshot_panel, report_panel], expand=True, equal=True),
    ]
    if snapshot and snapshot.awaiting_human_approval:
        renderables.append(_build_command_hint_panel())
    return Group(*renderables)


def _render_factor_table(results: list[dict], *, top: int, island: str | None) -> Group:
    title = f"Top {len(results)} factors"
    if island:
        title += f" in island={island}"

    table = Table(title=title, border_style="green")
    table.add_column("#", justify="right")
    table.add_column("Factor ID", no_wrap=True)
    table.add_column("Island")
    table.add_column("Sharpe", justify="right")
    table.add_column("IC", justify="right")
    table.add_column("ICIR", justify="right")
    table.add_column("Formula", overflow="fold")

    for index, factor in enumerate(results, start=1):
        table.add_row(
            str(index),
            _short_id(factor.get("factor_id")),
            factor.get("island", "—"),
            f"{factor.get('sharpe', 0):.2f}",
            f"{factor.get('ic_mean', factor.get('ic', 0)):.4f}",
            f"{factor.get('icir', 0):.2f}",
            factor.get("formula", "")[:72] or "—",
        )

    summary = Panel(
        f"Requested top={top} | Source=FactorPool | Filter={'all islands' if island is None else island}",
        title="Factor Leaderboard",
        border_style="green",
    )
    return Group(summary, table)


def _render_report_view(report_record, markdown_text: str) -> Group:
    metadata = _build_key_value_panel(
        "CIO Report",
        [
            ("Report ID", report_record.ref_id),
            ("Run ID", report_record.run_id),
            ("Created", _format_timestamp(report_record.created_at)),
            ("Path", report_record.path),
        ],
        border_style="magenta",
    )
    return Group(metadata, Markdown(markdown_text))


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

    if mode not in {"evolve", "single"}:
        raise typer.BadParameter("mode must be one of: evolve, single")

    if mode == "single" and islands:
        raise typer.BadParameter("--islands is only supported in evolve mode")

    island_list = [item.strip() for item in islands.split(",") if item.strip()] if islands else None

    if not sys.stdout.isatty():
        console.print(
            _build_run_launch_panel(
                mode=mode,
                rounds=rounds,
                island=island,
                islands=island_list,
                verbose=verbose,
            )
        )

    if mode == "single":
        _run_with_progress(run_single(island=island), total_rounds=1)
    else:
        _run_with_progress(run_evolve(rounds=rounds, islands=island_list), total_rounds=rounds)


@app.command()
def status():
    """查看当前系统状态（优先从 control-plane state_store 读取）。"""
    try:
        store = _get_state_store()
        run = store.get_latest_run()
        snapshot = store.get_snapshot(run.run_id) if run else None
        reports = store.list_reports(limit=1)
    except Exception as e:
        console.print(f"[red]读取状态失败: {e}[/red]")
        return

    if run is None:
        console.print(
            Panel("No run record found in the control plane.", title="Pixiu Runtime Status", border_style="yellow")
        )
        return

    console.print(_render_status_view(run, snapshot, reports[0] if reports else None))


@app.command()
def factors(
    top: int = typer.Option(10, "--top", "-n", min=1, help="显示前 N 个"),
    island: str = typer.Option(None, "--island", "-i", help="按 Island 过滤"),
):
    """查看因子排行榜（按 Sharpe 降序）。"""
    from src.factor_pool.pool import get_factor_pool

    pool = get_factor_pool()
    results = pool.get_top_factors(limit=max(top * 3, top))
    if island:
        results = [r for r in results if r.get("island") == island]
    results = results[:top]

    if not results:
        label = island or "all islands"
        console.print(
            Panel(
                f"No promoted factors found for filter={label}.",
                title="Factor Leaderboard",
                border_style="yellow",
            )
        )
        return

    console.print(_render_factor_table(results, top=top, island=island))


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
def report(
    latest: bool = typer.Option(False, "--latest", help="显式查看最新一份 CIO 报告"),
):
    """查看 CIO 报告（当前仅支持最新一份）。"""
    _ = latest
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
        console.print("[red]报告文件不存在[/red]")
        print(report_path)
        return

    console.print(_render_report_view(reports[0], report_path.read_text(encoding="utf-8")))


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
