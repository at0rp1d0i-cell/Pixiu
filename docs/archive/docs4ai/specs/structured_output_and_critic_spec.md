# 结构化输出 + Critic 增强 — 实施规格说明书

> 面向 Gemini 的执行文档
> 版本：1.0 | 日期：2026-03-04
> 前置条件：AKShare MCP Server 任务已完成

---

## 任务背景

当前系统的核心接缝问题：

```
Researcher 输出 → 自由文本字符串（factor_proposal: str）
                              ↓
Coder 从文字中猜"Qlib 公式在哪"
                              ↓
Critic 用正则 r"夏普比率[:：]\s*([-\d\.]+)" 从日志里抠数字
```

这条数据流有两处致命脆弱点：
1. Coder 收到的是非结构化文本，如果 Researcher 输出格式稍变，Coder 就会误解公式
2. Critic 的正则在回测日志格式变化时静默失败（sharpe=0.0），导致永远认为"未击败基线"

**本任务目标：** 在不破坏现有 LangGraph 图结构的前提下，把这两处接缝换成结构化数据。

---

## 交付物清单

1. `src/agents/schemas.py` — 新建，定义 `FactorHypothesis` Pydantic model
2. `src/agents/state.py` — 修改，新增结构化字段
3. `src/agents/researcher.py` — 修改，输出 `FactorHypothesis` 对象
4. `src/agents/critic.py` — 修改，结构化解析 + 多指标评估
5. `tests/test_structured_output.py` — 新建，验收测试

**不要动的文件：** `orchestrator.py`、`coder.py`、`validator.py`、`mcp_servers/`

---

## 任务 1：创建 `src/agents/schemas.py`

**完整文件内容：**

```python
"""
EvoQuant: 结构化数据模型
统一定义 Agent 间传递的数据结构，消除自由文本接缝。
"""
from typing import Literal
from pydantic import BaseModel, Field


class FactorHypothesis(BaseModel):
    """Researcher 输出的结构化因子假设。"""

    name: str = Field(
        description="因子英文名（snake_case），如 northbound_momentum_5d"
    )
    formula: str = Field(
        description="标准 Qlib 表达式，如 Mean($volume, 5) / Ref(Mean($volume, 5), 5)"
    )
    hypothesis: str = Field(
        description="因子的中文假设描述（1-3句话）"
    )
    market_observation: str = Field(
        default="",
        description="Researcher 调用 MCP 工具后观察到的关键市场数据（可为空）"
    )
    expected_direction: Literal["positive", "negative", "unknown"] = Field(
        default="unknown",
        description="预期因子方向：positive=因子越大收益越高，negative=反之"
    )
    rationale: str = Field(
        description="为什么这个因子在 A 股应该有 Alpha（1-3句话）"
    )


class BacktestMetrics(BaseModel):
    """Coder 回测完成后的结构化指标结果。"""

    sharpe: float = Field(default=0.0, description="年化夏普比率")
    annualized_return: float = Field(default=0.0, description="年化收益率（%）")
    max_drawdown: float = Field(default=0.0, description="最大回撤（%，负数）")
    ic: float = Field(default=0.0, description="因子 IC 均值")
    icir: float = Field(default=0.0, description="IC 信息比率（IC均值/IC标准差）")
    turnover: float = Field(default=0.0, description="日均换手率（%）")
    win_rate: float = Field(default=0.0, description="胜率（%）")
    parse_success: bool = Field(
        default=False,
        description="是否成功从回测日志解析到有效指标"
    )
    raw_log_tail: str = Field(
        default="",
        description="回测日志最后 500 字符（用于调试）"
    )
```

---

## 任务 2：修改 `src/agents/state.py`

**将文件全部内容替换为：**

```python
"""
EvoQuant: LangGraph State Definition
"""
from typing import TypedDict, Annotated, Sequence, Optional
from langchain_core.messages import BaseMessage
import operator

from .schemas import FactorHypothesis, BacktestMetrics


class AgentState(TypedDict):
    # LangChain 消息历史
    messages: Annotated[Sequence[BaseMessage], operator.add]

    # ── 结构化核心字段（新增）──────────────────────────────────
    factor_hypothesis: Optional[FactorHypothesis]  # Researcher 的结构化输出
    backtest_metrics: Optional[BacktestMetrics]    # Critic 解析的结构化指标

    # ── 兼容旧字段（保留，不删除）──────────────────────────────
    # Coder 仍然从 factor_proposal（str）生成代码，保持 Coder 不变
    factor_proposal: str       # 由 researcher_node 从 factor_hypothesis 自动生成
    code_snippet: str
    backtest_result: str       # Coder 的原始日志输出，Critic 从此解析

    # ── 状态追踪 ───────────────────────────────────────────────
    current_iteration: int
    max_iterations: int
    error_message: str
```

**关键设计：** 保留 `factor_proposal: str` 字段，这样 Coder 完全不需要改。
`researcher_node` 在填充 `factor_hypothesis` 的同时，也把公式序列化成字符串写入 `factor_proposal`。

---

## 任务 3：修改 `src/agents/researcher.py`

只需修改 `_research_node_async` 末尾的返回部分，以及添加结构化解析逻辑。

### 3.1 在文件顶部新增 import

在现有 import 块的末尾添加：

```python
from .schemas import FactorHypothesis
```

### 3.2 修改 System Prompt 中的输出规则部分

找到以下内容（大约在 `system_prompt` 字符串内的"输出规则"部分）：

**旧内容：**
```
**输出规则：**
1. 先调用 1-2 个最相关的实时数据工具，分析当前市场状态
2. 基于数据观察，提出一个 Qlib 表达式风格的新因子假设
3. 输出格式：
   - 【市场观察】：你从工具中观察到的关键数据
   - 【因子假设】：假设描述（中文）
   - 【Qlib 公式】：标准 Qlib 表达式（如 `Corr(Ref($close,1)/$close, Ref($volume,1)/$volume, 20)`）
   - 【预期逻辑】：为什么这个因子在 A 股应该有 Alpha
```

**替换为：**
```
**输出规则（严格遵守）：**
1. 先调用 1-2 个最相关的实时数据工具，分析当前市场状态
2. 基于数据观察，以严格的 JSON 格式输出因子假设（不要在 JSON 前后加任何多余文字）：

```json
{
  "name": "factor_name_in_snake_case",
  "formula": "Qlib表达式，如 Mean($volume,5)/Ref(Mean($volume,5),5)",
  "hypothesis": "因子的中文假设描述（1-3句话）",
  "market_observation": "你从工具中观察到的关键数据（如：今日北向净流入47亿）",
  "expected_direction": "positive",
  "rationale": "为什么这个因子在A股应该有Alpha（1-3句话）"
}
```

Qlib 公式合法算子参考：$open, $close, $high, $low, $volume, $vwap,
Ref(expr, n), Mean(expr, n), Std(expr, n), Corr(expr1, expr2, n),
Rank(expr), Log(expr), Abs(expr), Max(expr1, expr2), Min(expr1, expr2)
```

### 3.3 修改返回值部分

找到文件末尾的返回块：

**旧内容（最后约 10 行）：**
```python
    logger.info("[Researcher] 因子假设生成完毕")

    return {
        "factor_proposal": response.content,
        "messages": [response],
    }
```

**替换为：**
```python
    logger.info("[Researcher] 因子假设生成完毕")

    # 解析结构化输出
    factor_hypothesis, factor_proposal_str = _parse_factor_hypothesis(response.content)

    return {
        "factor_hypothesis": factor_hypothesis,
        "factor_proposal": factor_proposal_str,   # Coder 仍然读这个字段
        "messages": [response],
    }
```

### 3.4 在文件末尾（`if __name__` 之前）新增解析函数

```python
def _parse_factor_hypothesis(content: str):
    """从 LLM 输出中提取结构化 FactorHypothesis。

    优先解析 JSON；失败则降级为纯文本模式（保持兼容性）。
    返回 (FactorHypothesis | None, str)
    """
    import json, re

    # 尝试提取 JSON 块
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    if not json_match:
        # 也尝试不带 ``` 的裸 JSON
        json_match = re.search(r"(\{[^{}]*\"name\"[^{}]*\"formula\"[^{}]*\})", content, re.DOTALL)

    if json_match:
        try:
            data = json.loads(json_match.group(1))
            hypothesis = FactorHypothesis(**data)
            # 生成供 Coder 使用的字符串（公式是最关键的部分）
            proposal_str = (
                f"【因子名称】{hypothesis.name}\n"
                f"【Qlib 公式】{hypothesis.formula}\n"
                f"【假设描述】{hypothesis.hypothesis}\n"
                f"【市场观察】{hypothesis.market_observation}\n"
                f"【预期逻辑】{hypothesis.rationale}"
            )
            logger.info("[Researcher] 结构化解析成功：%s", hypothesis.name)
            return hypothesis, proposal_str
        except Exception as e:
            logger.warning("[Researcher] JSON 解析失败，降级为文本模式: %s", e)

    # 降级：返回原始文本，factor_hypothesis 为 None
    logger.warning("[Researcher] 未能提取结构化输出，使用原始文本")
    return None, content
```

---

## 任务 4：重写 `src/agents/critic.py`

**将文件全部内容替换为：**

```python
"""
EvoQuant: Critic Agent（结构化增强版）
Role: 从回测日志解析多维度指标，评估因子质量，决定路由。
评估标准：Sharpe > 基线 AND IC > 0.02 AND ICIR > 0.3 AND 换手率 < 50%
"""
import logging
import re
from .state import AgentState
from .schemas import BacktestMetrics

logger = logging.getLogger(__name__)

# ── 基线与阈值 ──────────────────────────────────────────────────
BASELINE_SHARPE = 2.67   # Phase 1 Alpha158+LightGBM 基线
MIN_IC = 0.02            # IC 均值最低门槛（低于此 = 无效因子）
MIN_ICIR = 0.3           # ICIR 稳定性门槛
MAX_TURNOVER = 50.0      # 日均换手率上限（%），超过手续费会吃掉收益


def _parse_metrics(log: str) -> BacktestMetrics:
    """从回测日志中提取结构化指标。

    优先尝试解析 JSON 格式输出；回退到正则解析自由文本。
    """
    import json

    if not log:
        return BacktestMetrics()

    # ── 优先路径：解析 JSON ──────────────────────────────────────
    json_match = re.search(r"BACKTEST_METRICS_JSON:\s*(\{.*?\})", log, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return BacktestMetrics(
                sharpe=float(data.get("sharpe", 0.0)),
                annualized_return=float(data.get("annualized_return", 0.0)),
                max_drawdown=float(data.get("max_drawdown", 0.0)),
                ic=float(data.get("ic", 0.0)),
                icir=float(data.get("icir", 0.0)),
                turnover=float(data.get("turnover", 0.0)),
                win_rate=float(data.get("win_rate", 0.0)),
                parse_success=True,
                raw_log_tail=log[-500:],
            )
        except Exception:
            pass  # 降级到正则

    # ── 降级路径：正则解析 ──────────────────────────────────────
    def _find(pattern, default=0.0):
        m = re.search(pattern, log)
        try:
            return float(m.group(1)) if m else default
        except (ValueError, AttributeError):
            return default

    sharpe   = _find(r"夏普比率[:：]\s*([-\d\.]+)")
    ann_ret  = _find(r"年化收益率?[:：]\s*([-\d\.]+)")
    max_dd   = _find(r"最大回撤[:：]\s*([-\d\.]+)")
    ic       = _find(r"\bIC均值?[:：]\s*([-\d\.]+)")
    icir     = _find(r"\bICIR[:：]\s*([-\d\.]+)")
    turnover = _find(r"换手率[:：]\s*([-\d\.]+)")

    parse_success = sharpe != 0.0  # 至少解析到 Sharpe 才算成功

    return BacktestMetrics(
        sharpe=sharpe,
        annualized_return=ann_ret,
        max_drawdown=max_dd,
        ic=ic,
        icir=icir,
        turnover=turnover,
        parse_success=parse_success,
        raw_log_tail=log[-500:],
    )


def _evaluate(metrics: BacktestMetrics, has_error: bool) -> tuple[str, str]:
    """
    多维度评估，返回 (route, reason)。
    route: "end"（成功）| "loop"（继续迭代）
    reason: 给 Researcher 下一轮参考的中文反馈
    """
    if has_error:
        return "loop", "代码执行报错，请检查 Qlib 表达式语法和数据列名。"

    if not metrics.parse_success:
        return "loop", "未能从回测日志解析到有效指标，请确认 Coder 输出格式正确。"

    reasons = []

    # ── 核心指标检查 ─────────────────────────────────────────────
    if metrics.sharpe <= BASELINE_SHARPE:
        reasons.append(f"Sharpe {metrics.sharpe:.2f} 未超越基线 {BASELINE_SHARPE}")

    if metrics.ic != 0.0 and metrics.ic < MIN_IC:
        reasons.append(f"IC均值 {metrics.ic:.4f} 低于门槛 {MIN_IC}（因子预测能力不足）")

    if metrics.icir != 0.0 and metrics.icir < MIN_ICIR:
        reasons.append(f"ICIR {metrics.icir:.2f} 低于门槛 {MIN_ICIR}（因子不够稳定）")

    if metrics.turnover != 0.0 and metrics.turnover > MAX_TURNOVER:
        reasons.append(f"日均换手率 {metrics.turnover:.1f}% 过高（手续费将吃掉大部分收益）")

    if reasons:
        feedback = "；".join(reasons) + "。请考虑：(1) 换一个方向的因子，(2) 降低因子换手（加长均线周期），(3) 检查因子是否存在前视偏差。"
        return "loop", feedback

    # ── 全部通过 ─────────────────────────────────────────────────
    return "end", (
        f"因子通过全部评估！Sharpe={metrics.sharpe:.2f}, "
        f"IC={metrics.ic:.4f}, ICIR={metrics.icir:.2f}, "
        f"换手率={metrics.turnover:.1f}%"
    )


def critic_node(state: AgentState) -> dict:
    logger.info("[Critic] 开始多维度因子评估...")

    log = state.get("backtest_result", "")
    error = state.get("error_message", "")
    current_iter = state.get("current_iteration", 0) + 1

    metrics = _parse_metrics(log)
    route, reason = _evaluate(metrics, bool(error))

    # 日志输出
    if route == "end":
        logger.info("[Critic] ✅ %s", reason)
    else:
        logger.info("[Critic] 🔄 第 %d/%d 轮未达标：%s",
                    current_iter, state.get("max_iterations", 3), reason)

    return {
        "current_iteration": current_iter,
        "backtest_metrics": metrics,
        # 把评估原因写入 error_message，Researcher 下一轮可以读到
        "error_message": reason if route == "loop" else "",
    }


def route_eval(state: AgentState) -> str:
    """LangGraph 路由函数。"""
    current_iter = state.get("current_iteration", 0)
    max_iter = state.get("max_iterations", 3)

    if current_iter >= max_iter:
        logger.info("[Critic] ⚠️ 达到最大迭代次数 %d，强制终止。", current_iter)
        return "end"

    metrics = state.get("backtest_metrics")
    error = state.get("error_message", "")

    # 如果 backtest_metrics 存在，用已解析的结果路由
    if metrics and isinstance(metrics, BacktestMetrics):
        if error:  # critic_node 把失败原因写入 error_message
            return "loop"
        route, _ = _evaluate(metrics, False)
        return route

    # 兼容旧路径：backtest_metrics 为空时降级到正则
    backtest = state.get("backtest_result", "")
    if backtest:
        m = re.search(r"夏普比率[:：]\s*([-\d\.]+)", backtest)
        if m and float(m.group(1)) > BASELINE_SHARPE:
            return "end"

    return "loop"
```

---

## 任务 5：创建 `tests/test_structured_output.py`

```python
"""验收测试：结构化输出与 Critic 增强。"""
import json
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.schemas import FactorHypothesis, BacktestMetrics
from src.agents.critic import _parse_metrics, _evaluate, critic_node


# ── Schema 测试 ────────────────────────────────────────────────
class TestFactorHypothesis:
    def test_valid_construction(self):
        h = FactorHypothesis(
            name="northbound_mom_5d",
            formula="Mean($volume, 5) / Ref(Mean($volume, 5), 5)",
            hypothesis="北向资金5日动量因子",
            rationale="外资趋势性行为在A股有预测力",
        )
        assert h.name == "northbound_mom_5d"
        assert h.expected_direction == "unknown"  # 默认值

    def test_missing_required_field(self):
        with pytest.raises(Exception):
            FactorHypothesis(name="test")  # 缺少 formula、hypothesis、rationale


# ── Critic 解析测试 ──────────────────────────────────────────────
class TestMetricsParsing:
    def test_parse_json_format(self):
        log = """
训练完成。
BACKTEST_METRICS_JSON: {"sharpe": 3.12, "ic": 0.045, "icir": 0.58, "turnover": 22.3,
"annualized_return": 18.5, "max_drawdown": -12.1, "win_rate": 54.2}
策略运行完毕。
"""
        metrics = _parse_metrics(log)
        assert metrics.parse_success is True
        assert metrics.sharpe == pytest.approx(3.12)
        assert metrics.ic == pytest.approx(0.045)
        assert metrics.icir == pytest.approx(0.58)

    def test_parse_regex_fallback(self):
        log = "夏普比率：2.91\nIC均值：0.038\nICIR：0.52\n换手率：18.5%"
        metrics = _parse_metrics(log)
        assert metrics.parse_success is True
        assert metrics.sharpe == pytest.approx(2.91)

    def test_parse_empty_log(self):
        metrics = _parse_metrics("")
        assert metrics.parse_success is False
        assert metrics.sharpe == 0.0

    def test_parse_no_sharpe(self):
        metrics = _parse_metrics("策略运行完毕，无有效输出。")
        assert metrics.parse_success is False


# ── Critic 评估逻辑测试 ──────────────────────────────────────────
class TestEvaluation:
    def test_all_pass(self):
        m = BacktestMetrics(sharpe=3.1, ic=0.05, icir=0.6, turnover=20.0, parse_success=True)
        route, reason = _evaluate(m, False)
        assert route == "end"
        assert "通过" in reason

    def test_sharpe_too_low(self):
        m = BacktestMetrics(sharpe=2.0, ic=0.05, icir=0.6, turnover=20.0, parse_success=True)
        route, _ = _evaluate(m, False)
        assert route == "loop"

    def test_high_turnover(self):
        m = BacktestMetrics(sharpe=3.5, ic=0.05, icir=0.6, turnover=80.0, parse_success=True)
        route, reason = _evaluate(m, False)
        assert route == "loop"
        assert "换手率" in reason

    def test_low_ic(self):
        m = BacktestMetrics(sharpe=3.5, ic=0.005, icir=0.6, turnover=20.0, parse_success=True)
        route, reason = _evaluate(m, False)
        assert route == "loop"
        assert "IC" in reason

    def test_error_always_loops(self):
        m = BacktestMetrics(sharpe=99.0, parse_success=True)
        route, _ = _evaluate(m, has_error=True)
        assert route == "loop"

    def test_parse_failure_loops(self):
        m = BacktestMetrics(parse_success=False)
        route, _ = _evaluate(m, False)
        assert route == "loop"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

---

## 任务 6：Coder 侧配合（最小改动）

Coder 不需要大改，但回测脚本需要输出 `BACKTEST_METRICS_JSON` 行，让 Critic 能走 JSON 路径（更准确）。

在 Coder 的 System Prompt 中（`src/agents/coder.py` 第 40-60 行附近），在"输出要求"部分追加以下一条规则：

**找到 Coder 的 system prompt 字符串（包含"夏普比率"的那段），在其末尾追加：**

```
6. 在脚本最后，必须输出一行结构化指标（严格按此格式，不要换行）：
BACKTEST_METRICS_JSON: {"sharpe": <值>, "ic": <值>, "icir": <值>, "turnover": <值>, "annualized_return": <值>, "max_drawdown": <值>}
若某项指标无法计算，用 0.0 填充。
```

---

## 验收清单

```bash
# Step 1: 运行结构化输出测试
cd EvoQuant
python3 -m pytest tests/test_structured_output.py -v

# 预期：全部 PASSED（共 11 个测试）

# Step 2: 验证 schemas 可以正常导入
python3 -c "from src.agents.schemas import FactorHypothesis, BacktestMetrics; print('OK')"

# Step 3: 验证 state.py 兼容性（AgentState 仍包含旧字段）
python3 -c "
from src.agents.state import AgentState
import typing
hints = typing.get_type_hints(AgentState)
assert 'factor_proposal' in hints, 'factor_proposal missing!'
assert 'factor_hypothesis' in hints, 'factor_hypothesis missing!'
assert 'backtest_metrics' in hints, 'backtest_metrics missing!'
print('State 字段验证通过')
"

# Step 4: 端到端跑一次完整循环（观察日志格式变化）
python3 EvoQuant/src/core/orchestrator.py
# 确认日志中出现：
#   [Researcher] 结构化解析成功：<factor_name>
#   [Critic] 开始多维度因子评估...
```

---

## 注意事项

1. **向后兼容** — `factor_proposal: str` 字段必须保留，Coder 不改
2. **降级保护** — Researcher 解析 JSON 失败时，`factor_hypothesis` 为 `None`，`factor_proposal` 为原始文本，系统继续运行
3. **route_eval 双路径** — 路由函数同时支持新的 `BacktestMetrics` 对象和旧的正则匹配，确保 Coder 未输出 JSON 时系统不崩溃
4. **IC/ICIR 容忍零值** — 如果 IC=0.0（未解析到），只检查 Sharpe；不因缺失指标而误判
5. **不要修改** `orchestrator.py` 中的图结构——节点名称和边都不变
