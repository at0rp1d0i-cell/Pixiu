# EvoQuant v2 Stage 4：执行层规格

> 版本：2.0
> 创建：2026-03-07
> 前置依赖：`v2_interface_contracts.md`
> 实施优先级：**P0 — 最先实施，替换当前 Claude Code 方案**
> 文件位置：`src/execution/`（新目录，替换 `src/sandbox/`）

---

## 0. 迁移说明

**删除以下 v1 文件：**
- `src/sandbox/` 整个目录（Claude Code 适配器）
- `src/agents/coder.py` 中所有 Claude Code 相关代码

**新建以下文件：**
```
src/execution/
├── __init__.py
├── exploration_agent.py    # 4a：EDA 脚本生成 + 执行
├── coder.py                # 4b：确定性模板执行器
├── docker_runner.py        # Docker subprocess 封装
└── templates/
    └── qlib_backtest.py.tpl  # Qlib 回测脚本模板
```

---

## 1. Stage 4a：ExplorationAgent

### 职责
接收 `FactorResearchNote.exploration_questions`，生成 EDA Python 脚本，在 Docker 沙箱执行，返回 `ExplorationResult`。

**不负责生成最终因子公式——只产生分析见解，服务于 AlphaResearcher 的公式精化。**

### 实现

```python
# src/execution/exploration_agent.py
from langchain_openai import ChatOpenAI
from src.schemas.research_note import FactorResearchNote, ExplorationQuestion
from src.schemas.exploration import ExplorationRequest, ExplorationResult
from src.execution.docker_runner import DockerRunner
import uuid

EXPLORATION_SYSTEM_PROMPT = """你是一个量化数据分析师，专门用 Python 探索 A 股市场数据。
你的工作是回答研究员的探索性问题，帮助他们验证假设。

可用数据：
- Qlib 数据库（路径：/data/qlib_bin/）
- 字段：$close, $open, $high, $low, $volume, $factor（复权因子）
- 股票池：沪深300 (csi300)
- 时间范围：2021-01-01 至 2025-03-31

你的输出必须是可以直接执行的 Python 脚本，最后一行打印一个 JSON 对象：
print(json.dumps({"findings": "...", "key_statistics": {...}, "refined_formula_suggestion": "...或null"}))

脚本要求：
1. 使用 qlib.data 加载数据，导入 qlib 前先 qlib.init(provider_uri="/data/qlib_bin/")
2. 所有统计必须用真实数据计算，不能虚构数字
3. 脚本执行时间不超过 60 秒
4. 如果有公式建议，必须是合法的 Qlib 表达式（只用已知算子）
"""

class ExplorationAgent:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=os.getenv("RESEARCHER_MODEL", "deepseek-chat"),
            base_url=os.getenv("RESEARCHER_BASE_URL"),
            api_key=os.getenv("RESEARCHER_API_KEY"),
            temperature=0.3,  # 低温度，代码生成要精确
        )
        self.runner = DockerRunner()

    async def explore(
        self,
        note: FactorResearchNote,
        question: ExplorationQuestion,
    ) -> ExplorationResult:
        request_id = str(uuid.uuid4())

        # Step 1: 生成 EDA 脚本
        prompt = self._build_prompt(note, question)
        response = await self.llm.ainvoke(prompt)
        script = self._extract_script(response.content)

        # Step 2: Docker 沙箱执行
        exec_result = await self.runner.run_python(
            script=script,
            timeout_seconds=120,
        )

        # Step 3: 解析结果
        if exec_result.success:
            import json
            output = json.loads(exec_result.stdout.strip().split("\n")[-1])
            return ExplorationResult(
                request_id=request_id,
                note_id=note.note_id,
                success=True,
                script_used=script,
                findings=output.get("findings", ""),
                key_statistics=output.get("key_statistics", {}),
                refined_formula_suggestion=output.get("refined_formula_suggestion"),
            )
        else:
            return ExplorationResult(
                request_id=request_id,
                note_id=note.note_id,
                success=False,
                script_used=script,
                findings="",
                key_statistics={},
                error_message=exec_result.stderr[:500],
            )

    def _build_prompt(self, note: FactorResearchNote, q: ExplorationQuestion) -> str:
        return f"""研究背景：{note.hypothesis}
初步公式方向：{note.proposed_formula}

探索问题：{q.question}
建议分析方式：{q.suggested_analysis}
需要的数据字段：{', '.join(q.required_fields)}

请生成一个 Python EDA 脚本回答这个问题。"""

    def _extract_script(self, content: str) -> str:
        """从 LLM 输出中提取 Python 代码块"""
        import re
        match = re.search(r"```python\n(.*?)```", content, re.DOTALL)
        if match:
            return match.group(1)
        # 如果没有代码块，尝试整体作为脚本
        return content
```

---

## 2. Stage 4b：Coder（确定性模板执行器）

### 核心设计思想
**Coder 不是智能体，是确定性函数。**

它的全部工作：
1. 接收一个 Qlib 公式字符串（来自 `FactorResearchNote.final_formula`）
2. 将公式填入标准回测模板
3. 用 `subprocess` 在 Docker 容器内执行
4. 解析 stdout 返回 `BacktestReport`

**不调用任何 LLM，不做任何推理。**

### Qlib 回测模板

```python
# src/execution/templates/qlib_backtest.py.tpl
# 此模板在运行时由 Coder 用字符串格式化填充

import qlib
import json
import sys
from qlib.constant import REG_CN
from qlib.data import D
from qlib.contrib.evaluate import risk_analysis
from qlib.contrib.strategy import TopkDropoutStrategy
from qlib.backtest import backtest, executor
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

# ── 由 Coder 填充的参数 ──────────────────────────────────────
FORMULA = "{formula}"
UNIVERSE = "{universe}"       # "csi300" 或 "csi500"
START_DATE = "{start_date}"   # "2021-06-01"
END_DATE = "{end_date}"       # "2025-03-31"
TOPK = {topk}                 # 持仓数量，默认 50
# ─────────────────────────────────────────────────────────────

try:
    qlib.init(provider_uri="/data/qlib_bin/", region=REG_CN)

    # 计算因子值
    instruments = D.instruments(market=UNIVERSE)
    fields = [FORMULA]
    field_names = ["factor"]
    df = D.features(instruments, fields, field_names,
                    start_time=START_DATE, end_time=END_DATE)
    df = df.dropna()

    # 按日排名（截面）
    df["rank"] = df.groupby("datetime")["factor"].rank(ascending=False)

    # IC 计算
    df["ret_1d"] = df.groupby("instrument")["factor"].shift(-1)  # 用真实收益率替代
    # 加载真实收益率
    ret_fields = ["$close/Ref($close,1)-1"]
    ret_df = D.features(instruments, ret_fields, ["ret"],
                        start_time=START_DATE, end_time=END_DATE)
    df = df.join(ret_df, how="left")

    ic_series = df.groupby("datetime").apply(
        lambda x: x["factor"].corr(x["ret"])
    ).dropna()

    ic_mean = float(ic_series.mean())
    ic_std = float(ic_series.std())
    icir = float(ic_mean / ic_std) if ic_std > 0 else 0.0

    # 简化回测：Top K 等权
    daily_returns = []
    for dt, group in df.groupby("datetime"):
        top = group.nsmallest(TOPK, "rank")["ret"]
        daily_returns.append(top.mean())

    daily_ret = pd.Series(daily_returns).dropna()
    annualized_return = float(daily_ret.mean() * 252)
    annualized_std = float(daily_ret.std() * (252 ** 0.5))
    sharpe = float(annualized_return / annualized_std) if annualized_std > 0 else 0.0
    max_drawdown = float((daily_ret.cumsum() - daily_ret.cumsum().cummax()).min())

    # 换手率（相邻两日 Top K 集合的变化率）
    dates = sorted(df["datetime"].unique())
    turnovers = []
    prev_set = set()
    for dt in dates:
        curr_set = set(df[df["datetime"] == dt].nsmallest(TOPK, "rank").index.get_level_values("instrument"))
        if prev_set:
            changed = len(curr_set.symmetric_difference(prev_set)) / (2 * TOPK)
            turnovers.append(changed)
        prev_set = curr_set
    turnover_rate = float(np.mean(turnovers)) if turnovers else 0.0

    result = {
        "sharpe": round(sharpe, 4),
        "annualized_return": round(annualized_return, 4),
        "max_drawdown": round(max_drawdown, 4),
        "ic_mean": round(ic_mean, 4),
        "ic_std": round(ic_std, 4),
        "icir": round(icir, 4),
        "turnover_rate": round(turnover_rate, 4),
        "error": None,
    }

except Exception as e:
    result = {
        "sharpe": 0.0,
        "annualized_return": 0.0,
        "max_drawdown": 0.0,
        "ic_mean": 0.0,
        "ic_std": 0.0,
        "icir": 0.0,
        "turnover_rate": 0.0,
        "error": str(e),
    }

print("BACKTEST_RESULT_JSON:" + json.dumps(result))
```

### Coder 实现

```python
# src/execution/coder.py
import uuid
from src.schemas.research_note import FactorResearchNote
from src.schemas.backtest import BacktestReport, BacktestMetrics
from src.execution.docker_runner import DockerRunner
from pathlib import Path
import json

TEMPLATE_PATH = Path(__file__).parent / "templates" / "qlib_backtest.py.tpl"

class Coder:
    """
    确定性 Qlib 回测执行器。
    不调用任何 LLM。接收公式 → 生成脚本 → 执行 → 返回结构化结果。
    """
    def __init__(self):
        self.runner = DockerRunner()
        self.template = TEMPLATE_PATH.read_text()

    async def run_backtest(self, note: FactorResearchNote) -> BacktestReport:
        formula = note.final_formula or note.proposed_formula
        factor_id = note.note_id  # 使用 note_id 作为 factor_id

        # 填充模板
        script = self.template.format(
            formula=formula,
            universe=note.universe,
            start_date=note.backtest_start,
            end_date=note.backtest_end,
            topk=50,
        )

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
                qlib_output_raw=exec_result.stderr[:2000],
                error_message=f"执行失败: {exec_result.stderr[:500]}",
            )

        # 从 stdout 提取 JSON
        for line in exec_result.stdout.split("\n"):
            if line.startswith("BACKTEST_RESULT_JSON:"):
                raw = json.loads(line.replace("BACKTEST_RESULT_JSON:", ""))
                break
        else:
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
                qlib_output_raw=exec_result.stdout[:2000],
                error_message="输出中未找到 BACKTEST_RESULT_JSON 标记",
            )

        if raw.get("error"):
            error_msg = raw["error"]
        else:
            error_msg = None

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
```

---

## 3. DockerRunner（共享执行基础设施）

```python
# src/execution/docker_runner.py
import asyncio
import tempfile
import os
from dataclasses import dataclass
from pathlib import Path
import time

@dataclass
class ExecutionResult:
    success: bool
    stdout: str
    stderr: str
    returncode: int
    duration_seconds: float

class DockerRunner:
    """
    在 evoquant-coder Docker 容器中执行 Python 脚本。
    使用 subprocess，不依赖任何 LLM。
    """
    IMAGE = "evoquant-coder:latest"
    QLIB_DATA_PATH = "/home/torpedo/Workspace/ML/EvoQuant/data/qlib_bin"

    async def run_python(
        self,
        script: str,
        timeout_seconds: int = 600,
    ) -> ExecutionResult:
        # 写入临时文件
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False
        ) as f:
            f.write(script)
            script_path = f.name

        start = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "run", "--rm",
                "--network=none",               # 无网络访问
                "-v", f"{self.QLIB_DATA_PATH}:/data/qlib_bin:ro",  # 只读数据
                "-v", f"{script_path}:/tmp/script.py:ro",
                "--memory=2g",                  # 内存限制
                "--cpus=2",                     # CPU 限制
                self.IMAGE,
                "python", "/tmp/script.py",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout_seconds,
                )
                return ExecutionResult(
                    success=(proc.returncode == 0),
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    returncode=proc.returncode,
                    duration_seconds=time.time() - start,
                )
            except asyncio.TimeoutError:
                proc.kill()
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr=f"执行超时（>{timeout_seconds}s）",
                    returncode=-1,
                    duration_seconds=timeout_seconds,
                )
        finally:
            os.unlink(script_path)
```

---

## 4. 测试要求

新建 `tests/test_execution.py`，覆盖：

```python
# 必须通过的测试
def test_coder_valid_formula():
    """合法 Qlib 公式应返回 BacktestReport(passed=True 或 False，无 error)"""

def test_coder_invalid_formula():
    """语法错误公式应返回 BacktestReport(passed=False, error_message 非空)"""

def test_coder_output_parsing():
    """BACKTEST_RESULT_JSON 解析逻辑单元测试（不需要 Docker）"""

def test_exploration_agent_script_extraction():
    """LLM 输出代码块提取逻辑单元测试"""

def test_docker_runner_timeout():
    """超时处理：运行 sleep(9999) 应在 timeout 后终止"""

def test_docker_runner_network_blocked():
    """容器内网络访问应被拒绝"""
```

---

## 5. 常见问题

**Q：为什么不用 Claude Code？**
A：Claude Code 是交互式 CLI，不是 SDK。用它做程序化调用本质上是 hack：行为不可预测，结果靠字符串解析，升级不可控。`DockerRunner + 模板` 是确定性的，可测试，zero-LLM-call。

**Q：回测脚本里的 IC 计算是否正确？**
A：模板里的 IC 计算使用因子值与次日收益率的 Pearson 相关性（截面）。如果数据质量较好，这是标准 IC 的近似。如果需要更精确的 RankIC，修改模板中对应行即可。

**Q：ExplorationAgent 生成的脚本是否安全？**
A：脚本在 `--network=none` 的 Docker 容器内执行，无法访问网络或宿主机文件系统（只读挂载 qlib_bin）。即使 LLM 生成了危险代码，沙箱会阻止实际危害。
