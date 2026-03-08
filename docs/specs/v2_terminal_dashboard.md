# Pixiu v2 Terminal CLI + Web Dashboard 规格

> 版本：2.0
> 创建：2026-03-07
> 前置依赖：`v2_orchestrator.md`
> 文件位置：`src/cli/`（新目录）、`frontend/`（已有目录）

---

## 1. 产品形态

Pixiu v2 提供两种交互界面，服务不同场景：

| 界面 | 场景 | 技术栈 |
|---|---|---|
| Terminal CLI | 启动系统、审批因子、Debug | Python + Rich / Typer |
| Web Dashboard | 后台运行时监控、因子池浏览 | React + Vite（已有目录）|

两者独立，不互相依赖。CLI 是主入口，Dashboard 是辅助可视化。

---

## 2. Terminal CLI

### 命令设计

```bash
# 启动进化循环（后台运行）
evoquant run --mode evolve --rounds 20 --islands momentum,northbound

# 单次调试（指定 Island，前台运行，详细日志）
evoquant run --mode single --island momentum --verbose

# 查看当前状态
evoquant status

# 查看因子排行榜
evoquant factors --top 10 --island momentum

# 审批操作（当系统等待 CIO 时）
evoquant approve              # 批准当前报告，继续运行
evoquant redirect momentum    # 将下轮重点切换到 momentum Island
evoquant stop                 # 停止进化循环

# 查看最新 CIO 报告
evoquant report --latest
```

### CLI 实现框架

```python
# src/cli/main.py
import typer
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
import asyncio

app = typer.Typer(help="Pixiu v2 - 自主 AI 量化研究平台")
console = Console()

@app.command()
def run(
    mode: str = typer.Option("evolve", help="evolve | single"),
    rounds: int = typer.Option(20, help="进化轮次（仅 evolve 模式）"),
    island: str = typer.Option(None, help="指定 Island（仅 single 模式）"),
    islands: str = typer.Option(None, help="逗号分隔的 Island 列表"),
    verbose: bool = typer.Option(False, help="详细日志输出"),
):
    """启动研究循环"""
    from src.core.orchestrator import run_evolve, run_single

    console.print(Panel(
        "[bold green]Pixiu v2 启动[/bold green]\n"
        f"模式：{mode} | 轮次：{rounds}",
        title="EvoQuant"
    ))

    if mode == "single":
        asyncio.run(run_single(island=island or "momentum"))
    else:
        island_list = islands.split(",") if islands else None
        asyncio.run(run_evolve(rounds=rounds, islands=island_list))

@app.command()
def status():
    """查看当前系统状态"""
    from src.core.state_manager import load_latest_state
    state = load_latest_state()
    if not state:
        console.print("[yellow]当前没有运行中的实验[/yellow]")
        return

    table = Table(title="当前状态")
    table.add_column("项目")
    table.add_column("值")
    table.add_row("当前轮次", str(state.current_round))
    table.add_row("当前 Island", state.current_island)
    table.add_row("已测因子数", str(len(state.backtest_reports)))
    table.add_row("已通过因子数", str(sum(1 for v in state.critic_verdicts if v.overall_passed)))
    table.add_row("等待审批", "是" if state.awaiting_human_approval else "否")
    console.print(table)

@app.command()
def factors(
    top: int = typer.Option(10),
    island: str = typer.Option(None),
):
    """查看因子排行榜"""
    from src.factor_pool.pool import FactorPool
    pool = FactorPool()
    results = pool.get_top_factors(limit=top)
    if island:
        results = [r for r in results if r.get("island") == island]

    table = Table(title=f"Top {top} 因子")
    table.add_column("ID")
    table.add_column("Island")
    table.add_column("Sharpe")
    table.add_column("IC")
    table.add_column("ICIR")
    table.add_column("公式（前60字符）")
    for f in results:
        table.add_row(
            f.get("factor_id", "")[:20],
            f.get("island", ""),
            f"{f.get('sharpe', 0):.2f}",
            f"{f.get('ic_mean', 0):.4f}",
            f"{f.get('icir', 0):.2f}",
            f.get("formula", "")[:60],
        )
    console.print(table)

@app.command()
def approve():
    """批准当前 CIO 报告，继续运行"""
    _inject_human_decision("approve")
    console.print("[green]✓ 已批准，系统继续运行[/green]")

@app.command()
def redirect(island: str = typer.Argument(..., help="切换到的 Island")):
    """将下轮重点切换到指定 Island"""
    _inject_human_decision(f"redirect:{island}")
    console.print(f"[blue]→ 已重定向至 {island} Island[/blue]")

@app.command()
def stop():
    """停止进化循环"""
    _inject_human_decision("stop")
    console.print("[red]■ 系统将在当前轮次完成后停止[/red]")

def _inject_human_decision(decision: str):
    """将 human_decision 注入 LangGraph checkpoint"""
    from src.core.orchestrator import get_graph, get_latest_config
    graph = get_graph()
    config = get_latest_config()
    graph.update_state(
        config,
        {"human_decision": decision, "awaiting_human_approval": False},
        as_node="human_gate",
    )
```

### 流式输出（运行时）

系统运行时，CLI 输出关键里程碑（不是所有日志）：

```
[2026-03-07 09:12:01] ● 第 1 轮开始
[2026-03-07 09:12:03] ✓ 市场上下文：北向净流入 12.3亿，制度=trending_up
[2026-03-07 09:12:08] ✓ 并行生成假设：4 个 Island，共 4 个候选
[2026-03-07 09:12:09] → 前置过滤：4 → 3（淘汰 1 个）
[2026-03-07 09:12:12] ⋯ 探索性分析：momentum Island 正在验证换手率假设...
[2026-03-07 09:12:45] ✓ 探索完成，公式精化：Mean($volume/...) → ...
[2026-03-07 09:12:46] ⋯ 回测执行中（3 个因子，预计 15-30 分钟）...
[2026-03-07 09:28:31] ✓ 回测完成：1 个通过（Sharpe=2.89），2 个失败
[2026-03-07 09:28:33] ✓ 风险审计通过：无过拟合风险
[2026-03-07 09:28:35] ✓ 组合更新：momentum 权重 0.35
[2026-03-07 09:28:40] ⚠ 第 5 轮报告已生成，等待 CIO 审批（运行 `evoquant approve` 继续）
```

---

## 3. Web Dashboard

### 页面结构（React）

```
/                    ← 总览（当前状态、最新 Sharpe 趋势）
/factors             ← 因子排行榜（可按 Island / Sharpe / IC 筛选）
/factors/:id         ← 单因子详情（公式、回测曲线、风险指标）
/islands             ← Island 状态（各 Island 进化进度、调度权重）
/reports             ← CIO 报告列表（Markdown 渲染，含审批操作）
/reports/:id/approve ← 审批界面（批准 / 重定向 / 停止）
```

### 数据接口（后端 FastAPI）

```python
# src/api/server.py

from fastapi import FastAPI
from src.factor_pool.pool import FactorPool
from src.core.state_manager import load_latest_state

api = FastAPI()

@api.get("/api/status")
def get_status():
    state = load_latest_state()
    return state.dict() if state else {"status": "idle"}

@api.get("/api/factors")
def get_factors(island: str = None, limit: int = 20):
    pool = FactorPool()
    return pool.get_top_factors(limit=limit)

@api.get("/api/islands")
def get_islands():
    from src.factor_pool.scheduler import IslandScheduler
    # 返回各 Island 的统计数据
    ...

@api.get("/api/reports")
def get_reports():
    # 从持久化存储读取 CIOReport 列表
    ...

@api.post("/api/approve")
def post_approve(decision: dict):
    # 注入 human_decision 到 LangGraph
    _inject_human_decision(decision["action"])
    return {"ok": True}
```

### 启动方式

```bash
# Terminal（前台）
evoquant run --mode evolve --rounds 20

# Dashboard（后台，独立进程）
uvicorn src.api.server:api --port 8080 &
cd frontend && npm run dev  # Vite dev server（开发）
# 或
cd frontend && npm run build && npm run preview  # 生产预览
```

---

## 4. 实施优先级

Phase 3 的产品层，**不阻塞 Phase 2B 的核心研究循环**。

推荐实施顺序：
1. CLI 基础命令（`run`、`status`、`factors`）—— 立即可用，替换当前手动运行方式
2. CLI 审批命令（`approve`、`redirect`、`stop`）—— 与 LangGraph `interrupt()` 联动
3. FastAPI 后端（`/api/status`、`/api/factors`）—— 为 Dashboard 提供数据
4. React Dashboard —— 最后实施，基于已有 `frontend/` 目录

---

## 5. 依赖

```bash
# CLI
pip install typer rich

# Dashboard 后端
pip install fastapi uvicorn

# Dashboard 前端（已有 package.json）
cd frontend && npm install
```
