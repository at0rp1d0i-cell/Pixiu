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
import os
import sys

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

app = typer.Typer(
    name="pixiu",
    help="Pixiu v2 - 自主 AI 量化研究平台",
    no_args_is_help=True,
)
console = Console()


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

    console.print(Panel(
        f"[bold cyan]Pixiu v2 启动[/bold cyan]\n"
        f"模式：[yellow]{mode}[/yellow]  |  轮次：[yellow]{rounds}[/yellow]  |  Island：[yellow]{island}[/yellow]",
        title="🦅 Pixiu Quantitative Research",
        border_style="cyan",
    ))

    if mode == "single":
        asyncio.run(run_single(island=island))
    else:
        island_list = islands.split(",") if islands else None
        asyncio.run(run_evolve(rounds=rounds, islands=island_list))


@app.command()
def status():
    """查看当前系统状态（从持久化 AgentState 读取）。"""
    from src.factor_pool.pool import get_factor_pool

    pool = get_factor_pool()
    stats = pool.get_stats()

    table = Table(title="Pixiu 运行状态", border_style="cyan")
    table.add_column("项目", style="bold")
    table.add_column("值", style="green")

    table.add_row("总实验因子数", str(stats.get("total_factors", 0)))
    table.add_row("突破基线因子数", str(stats.get("beats_baseline_count", 0)))
    table.add_row("全局最优 Sharpe", f"{stats.get('global_best_sharpe', 0):.2f}")
    table.add_row("全局平均 Sharpe", f"{stats.get('global_avg_sharpe', 0):.2f}")

    console.print(table)

    # Island 排行榜
    leaderboard = pool.get_island_leaderboard()
    if leaderboard:
        lb_table = Table(title="Island 排行榜", border_style="green")
        lb_table.add_column("排名")
        lb_table.add_column("Island")
        lb_table.add_column("因子数")
        lb_table.add_column("Best Sharpe")
        lb_table.add_column("Avg Sharpe")
        lb_table.add_column("最优因子")
        for i, item in enumerate(leaderboard, 1):
            lb_table.add_row(
                str(i),
                f"{item['island_display_name']} ({item['island']})",
                str(item["factor_count"]),
                f"{item['best_sharpe']:.2f}",
                f"{item['avg_sharpe']:.2f}",
                item.get("best_factor_name", "—"),
            )
        console.print(lb_table)


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
    _inject_human_decision("approve")
    console.print("[bold green]✅ 已批准，系统继续运行[/bold green]")


@app.command()
def redirect(
    island: str = typer.Argument(..., help="切换到的 Island（如 momentum, volatility 等）"),
):
    """将下轮研究重点切换到指定 Island。"""
    _inject_human_decision(f"redirect:{island}")
    console.print(f"[bold blue]➡️  已重定向至 [yellow]{island}[/yellow] Island[/bold blue]")


@app.command()
def stop():
    """停止进化循环（当前轮完成后退出）。"""
    _inject_human_decision("stop")
    console.print("[bold red]⏹  系统将在当前轮次完成后停止[/bold red]")


@app.command()
def report():
    """查看最新 CIO 报告（Markdown 格式）。"""
    from src.factor_pool.pool import get_factor_pool

    # 尝试从 FactorPool 或持久化读取最新报告
    console.print("[yellow]（CIO 报告查看功能依赖 Orchestrator 运行，暂时从 FactorPool 摘要生成）[/yellow]")

    pool = get_factor_pool()
    leaderboard = pool.get_island_leaderboard()
    stats = pool.get_stats()

    report_md = f"""# Pixiu v2 当前因子库摘要报告

## 全局统计
- 总实验因子：{stats.get('total_factors', 0)}
- 突破基线因子：{stats.get('beats_baseline_count', 0)}
- 全局最优 Sharpe：{stats.get('global_best_sharpe', 0):.2f}

## Island 排行榜
| Island | 因子数 | Best Sharpe | 最优因子公式 |
|--------|--------|-------------|------------|
"""
    for item in leaderboard:
        report_md += f"| {item['island']} | {item['factor_count']} | {item['best_sharpe']:.2f} | {item.get('best_factor_formula', '—')[:50]} |\n"

    console.print(Markdown(report_md))


def _inject_human_decision(decision: str):
    """将 human_decision 注入 LangGraph checkpoint。"""
    try:
        from src.core.orchestrator import get_graph, get_latest_config
        graph = get_graph()
        config = get_latest_config()
        if not config:
            console.print("[red]⚠️  无正在运行的实验（找不到 LangGraph config）[/red]")
            return
        graph.update_state(
            config,
            {"human_decision": decision, "awaiting_human_approval": False},
            as_node="human_gate",
        )
    except Exception as e:
        console.print(f"[red]注入失败: {e}[/red]")


def main():
    """CLI 入口（供 pyproject.toml [project.scripts] 注册）。"""
    app()


if __name__ == "__main__":
    main()
