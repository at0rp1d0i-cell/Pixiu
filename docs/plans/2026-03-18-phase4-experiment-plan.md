# Phase 4B 受控实验计划

Status: active
Owner: coordinator
Last Reviewed: 2026-03-18

> 创建：2026-03-18
> 阶段：Phase 4A（数据上线）→ Phase 4B（受控实验）→ Phase 4C（MiroFish 接入 Go/No-Go）

---

## 背景

Phase 3 已完成全部模块化收口（orchestrator 包拆分、Stage I/O TypedDicts、405 smoke/unit 测试通过）。当前最大缺口是：

- `NARRATIVE_MINING` 子空间缺乏新闻/公告数据支撑
- regime 特征层缺乏融资余额、市场宽度、涨停池等特征量（这些特征将通过 `FACTOR_ALGEBRA` 和 `NARRATIVE_MINING` 的 prompt context 注入，不作为独立子空间追踪）
- `AlphaResearcher` 仍是纯 `llm.ainvoke()` 调用，不能直接使用 MCP 工具；RSS 数据当前只能先由 Stage 1 消费，再通过 `MarketContextMemo` 间接影响 Stage 2
- `FactorPoolRecord.subspace_origin` 已进入主路径写回，可直接作为实验统计维度使用
- SubspaceScheduler Thompson Sampling 处于 cold start 期，缺乏多轮 track record

**Phase 4A** 补齐两类数据源：

| 数据源 | 覆盖子空间 | 实现方式 |
|--------|-----------|---------|
| RSS MCP（公告/政策/财经新闻）| Stage 1 当前直连；Stage 2 `NARRATIVE_MINING` 目标态直连 | 新增 MCP server；当前由 `MarketAnalyst` 消费并通过 `MarketContextMemo` 间接影响 Stage 2，Researcher 工具化升级后再开放直连 |
| AKShare 扩展（融资余额、市场宽度、涨停池、行业轮动速度）| `FACTOR_ALGEBRA` / `NARRATIVE_MINING`（通过 prompt context 注入，不作为独立子空间追踪）| 扩展现有 AKShare MCP 工具集 |

**Phase 4B** 是数据上线后、MiroFish 正式集成前的受控实验窗口，目标是建立 baseline、验证新数据的实际价值，并为 Phase 4C 的 Go/No-Go 提供数据依据。

---

## 1. 实验目标

本次实验需回答两个核心问题：

**Q1 — 假设质量**：新数据是否提升了 Stage 3 通过率和最终 Sharpe 分布？

**Q2 — 子空间覆盖度**：哪个 island × subspace 组合在当前 regime 下产出最多有效信号？Thompson Sampling 调度器在观测期内是否开始表现出方向性偏好？

---

## 2. 实验设计

### 2.1 轮次安排

建议：50 轮完整观测窗口。

需要明确：

- 当前运行时实际停轮由 `MAX_ROUNDS` 环境变量控制，不应把 CLI `--rounds` 当作唯一真值
- `WARM_START_THRESHOLD=30` 表示需要累计约 30 个通过假设后，子空间调度器才真正进入自适应阶段

推荐分期：

- 前 10 轮：cold start / transition
- 第 11-50 轮：主要观测期
- 如果 Round 10 结束后 `sum(scheduler_state.total_passed.values()) < 30`，则顺延 cold start，直到达到 `WARM_START_THRESHOLD`

每轮完成后自动记录快照，不人工干预中间过程。预计每轮耗时 5–15 分钟（取决于 LLM 并发和 Stage 4 回测耗时）。

### 2.2 冷启动分期

由于当前 FactorPool 尚无历史积累，无法建立真正的历史 baseline：

| 分期 | 轮次 | 说明 |
|------|------|------|
| Cold start / transition | Round 1–10 | FailureConstraint Filter D 仍偏弱，Thompson Sampling 多数情况下尚未达到 `WARM_START_THRESHOLD=30` |
| 主要观测期 | Round 11–50 | 若累计通过数已达到阈值，则开始观测调度器的方向性偏好；否则延后进入 |

### 2.3 控制变量

实验期间以下参数**不得修改**：

- `MAX_ROUNDS`、`ACTIVE_ISLANDS`（island 集合不变）
- Stage 3 所有硬 gate 阈值（`THRESHOLDS` 单例，`src/schemas/thresholds.py`）
- LLM 模型配置（`RESEARCHER_*` 环境变量）
- 不合并任何影响 Stage 2 prompt 或 Stage 3 过滤逻辑的代码变更

---

## 3. 度量指标体系

### 3.1 假设质量指标（每轮记录）

| 指标 | 数据来源 | 基准目标 |
|------|---------|---------|
| Stage 3 通过率 | `approved_notes` 数 / (`approved_notes` + `filtered_count`) | 观测期 > 30% |
| 通过假设的平均 IS Sharpe | `BacktestReport.metrics.sharpe`（通过者均值）| IS Sharpe 均值（基准 > 3.0，当前系统 min_sharpe=2.67，目标为超越基准）|
| 通过假设的 IC 均值 | `BacktestReport.metrics.ic_mean`（通过者均值）| > 0.03 |
| Critic 通过率 | `CriticVerdict.overall_passed == True` 数 / 总 verdicts | > 40% |
| FactorPool 有效因子累计数 | `FactorPoolRecord`（`passed == True`）总计 | 观测期持续增长 |

字段映射：
- `AgentState.approved_notes: List[FactorResearchNote]`
- `AgentState.filtered_count: int`
- `AgentState.backtest_reports: List[BacktestReport]`
- `AgentState.critic_verdicts: List[CriticVerdict]`

> **注意**：`AgentState.approved_notes` 是单轮数据。`loop_control_node` 在每轮结束时会清空该字段，因此不能依赖最终 state 做跨轮统计——必须从每轮 JSON 快照（`logs/rounds/`）中捕获各轮快照，而不能读取实验结束后的 state。

### 3.2 子空间覆盖度指标（每轮记录）

| 指标 | 数据来源 | 说明 |
|------|---------|------|
| 各子空间本轮生成数 | `AgentState.subspace_generated: Dict[str, int]` | 哪个子空间在当前轮最活跃 |
| 各子空间 Stage 3 通过率 | `FactorResearchNote.exploration_subspace` 与 `approved_notes` 交叉统计 | 哪个子空间质量最高 |
| Thompson Sampling 权重演化 | `AgentState.scheduler_state`（`SubspaceScheduler` 持久化状态）| 调度器是否向优势子空间收敛 |
| Island 间通过率对比 | 按 `AgentState.current_island` 分组统计 `approved_notes` | 哪个 island 当前最有效 |

### 3.3 新数据利用率指标（Phase 4 特有）

| 指标 | 数据来源 | 说明 |
|------|---------|------|
| Stage 1 RSS 摘要注入命中次数 | `MarketContextMemo.raw_summary` + Stage 1 日志 | RSS 数据是否已进入当前运行时主链 |
| FACTOR_ALGEBRA / NARRATIVE_MINING 在有/无新 AKShare regime 数据时的表现差异 | 对比引用 regime 特征关键词的假设与未引用者的 Stage 3 通过率 | 新 regime 特征量是否实质提升假设质量 |
| 含 narrative 关键词的假设占比 | `FactorResearchNote.hypothesis` 文本分析（关键词：政策/公告/预期/叙事）| 叙事信号是否实质影响假设生成 |
| `FactorPoolRecord.subspace_origin` 分布 | `FactorPool.get_passed_factors()` 返回的 metadata | 有效因子来自哪个子空间 |

---

## 4. 需要新增的结构化日志

当前各 Stage 缺乏足够的结构化日志供实验分析。在不修改核心逻辑的前提下，在以下位置添加 `logger.info` 调用：

**`src/agents/researcher.py`（Stage 2）**

```python
# 每个子空间生成完成后
logger.info(
    "[Stage 2][%s/%s] 生成假设: %d 个",
    island_name, subspace_name, count
)
```

**`src/agents/prefilter.py`（Stage 3）**

```python
# 过滤链执行完成后
logger.info(
    "[Stage 3][%s] 通过: %d / 总计: %d (通过率: %.1f%%)",
    island_name, passed, total, passed / total * 100 if total else 0
)
```

**`src/core/orchestrator/nodes/stage5.py`（Stage 5）**

```python
# CriticVerdict 批量写入后
logger.info(
    "[Stage 5][%s] Critic 通过: %d / %d, 平均 Sharpe: %.2f",
    island_name, passed, total, avg_sharpe
)
```

**`src/core/orchestrator/nodes/`（loop_control 节点）**

```python
# 每轮结束，loop_control 节点触发前
logger.info(
    "[Loop Control] Round %d 完成: subspace_generated=%s, filtered=%d, "
    "approved=%d, verdicts_passed=%d",
    current_round, subspace_generated, filtered_count,
    len(approved_notes), verdicts_passed
)
```

日志过滤规则（监控时使用）：

```bash
grep -E "\[Stage 2\]|\[Stage 3\]|\[Stage 5\]|\[Loop Control\]" logs/phase4b_experiment.log
```

---

## 5. 实验中止条件

出现以下任一情况，立即暂停实验并诊断，不强行继续：

| 条件 | 阈值 | 可能原因 |
|------|------|---------|
| Stage 3 通过率连续为 0 | 连续 3 轮 | 数据源断连、LLM 输出格式异常、Stage 2 prompt 退化 |
| FactorPool 无新增有效因子 | 连续 5 轮 | Stage 4 执行错误、Critic 评分系统性偏低 |
| 未捕获异常率过高 | 任意阶段 > 50% | 新 MCP 工具兼容性问题、schema 不对齐 |
| `scheduler_state` 写入失败 | 连续 3 轮 | 控制平面 state_store 问题，Thompson Sampling 无法积累 |

诊断入口：`AgentState.last_error` + `AgentState.error_stage`。

---

## 6. 实验后决策框架

实验 50 轮完成后，基于采集数据做出以下决策：

注意：`WARM_START_THRESHOLD=30`，Thompson Sampling 在积累约 30 个通过假设前处于近似均匀探索阶段。50 轮实验中不应默认“第 10 轮后自动收敛”，因此判断应基于实际达到阈值后的观测窗口。

| 决策问题 | 判断标准 | 结论为是 → | 结论为否 → |
|---------|---------|-----------|-----------|
| 新数据有实质价值吗？ | `NARRATIVE_MINING` 子空间或注入新 AKShare regime 数据的 `FACTOR_ALGEBRA` 子空间的 Stage 3 通过率 > 其余子空间均值 | 继续扩展对应数据源 | 先诊断子空间 prompt，可能是信号到假设的转化链问题 |
| Thompson Sampling 开始显著偏向吗？ | 某子空间 Thompson Sampling 权重 > 0.4，且该状态出现在达到 `WARM_START_THRESHOLD` 之后 | 说明有明显优势子空间，可重点投入该方向 | 继续均匀探索或降低阈值后重测 |
| NARRATIVE_MINING 值得接入 MiroFish 吗？ | `NARRATIVE_MINING` 子空间通过率 > 25% 且通过假设平均 Sharpe 均值 > 3.0（高于系统硬 gate 2.67，表明新数据产出质量更优假设）| 进入 Phase 4C：接入 MiroFish NarrativePrediction schema | 先优化 NARRATIVE_MINING 子空间 prompt，延迟 MiroFish 接入 |
| FactorPool 质量是否稳定？ | 观测期（Round 11–50）有效因子数单调递增 | 系统整体健康，可进入下一阶段 | 排查 FailureConstraint Filter D 是否误拦截 |

---

## 实验可追溯性设计

实验必须做到完全透明、全程可追溯。每轮产出的关键数据必须持久化，不能依赖日志解析。

### 每轮快照（必须实现）
`loop_control_node` 重置 state 前，在 `logs/rounds/` 目录写入 JSON 快照：
```json
{
  "round": 3,
  "timestamp": "2026-03-18T10:30:00",
  "subspace_generated": {"factor_algebra": 3, "narrative_mining": 2, ...},
  "filtered_count": 8,
  "approved_count": 4,
  "approved_notes": [{"id": "...", "exploration_subspace": "narrative_mining", ...}],
  "verdicts_passed": 2,
  "verdicts_total": 4,
  "sharpe_values": [3.2, 2.9],
  "scheduler_state": {...}
}
```

### 日志 tag 修正
注意：现有代码使用 `[Loop Control]`（含空格），不是 `[LoopCtrl]`。
grep 命令应使用：`grep -E "\[Stage 3\]|\[Stage 5\]|\[Loop Control\]"`

### 实验前基线快照
在第 1 轮开始前，记录初始 FactorPool 状态（因子数、子空间分布）作为基线。

---

## 7. 实验执行 SOP

```bash
# Step 1：确认环境和测试全部通过
uv run pytest -q tests -m "smoke or unit"
# 预期：405 passed

# Step 2：确认 Phase 4A 前置项已验收
# - RSS 源验证脚本通过
# - RSS server / Stage 1 消费测试通过
# - AKShare 扩展工具测试通过

# Step 3：建立日志目录
mkdir -p logs

# Step 4：后台启动实验
# 注意：关闭人工审批门
# 实验期间设置环境变量 REPORT_EVERY_N_ROUNDS=999（大于总轮次），避免触发 CIOReport 生成和人工审批中断
# 当前实际停轮由 MAX_ROUNDS 控制；--rounds 仅用于 CLI 参数对齐
MAX_ROUNDS=50 REPORT_EVERY_N_ROUNDS=999 uv run pixiu run --mode evolve --rounds 50 \
  > logs/phase4b_experiment.log 2>&1 &

# Step 5：实时监控关键 Stage 日志
tail -f logs/phase4b_experiment.log | grep -E "\[Stage 2\]|\[Stage 3\]|\[Stage 5\]|\[Loop Control\]"

# Step 6：实验结束后查看 FactorPool
uv run pixiu factors --top 20

# Step 7：手动统计 subspace_origin 分布
# 在 Python REPL 中：
pool = get_factor_pool()
# 前提：Stage 5 已把 note 传入 pool.register_factor(..., note=note)
factors = pool.get_passed_factors()  # 返回 list[dict]
from collections import Counter
subspace_dist = Counter((f.get("subspace_origin") or "unknown") for f in factors)
print(f"通过因子总数: {len(factors)}")
print(f"子空间分布: {dict(subspace_dist)}")
```

---

## 8. 预期产出

| 产出物 | 说明 | 用途 |
|--------|------|------|
| 50 轮完整日志 | `logs/phase4b_experiment.log` | 事后分析原始数据 |
| FactorPool 快照 | ChromaDB 持久化（`data/factor_pool_db/`）| 每个因子含 `subspace_origin` 可追溯 |
| Thompson Sampling 权重历史 | 从 `AgentState.scheduler_state` 每轮提取 | 可视化子空间竞争演化过程 |
| island × subspace Stage 3 通过率矩阵 | 从日志聚合 | 发现当前 regime 下的有效信号组合 |
| MiroFish 接入 Go/No-Go 备忘录 | 基于第 6 节决策框架填写 | Phase 4C 启动依据 |

---

## 附：Phase 4 整体路线图

```
Phase 4A（当前）
  ├── 新增 RSS MCP server（公告/政策/财经新闻）
  └── 扩展 AKShare MCP 工具集（融资余额/宽度/涨停池/轮动速度）

Phase 4B（本计划）
  └── 50 轮受控实验，建立 baseline，验证新数据价值

Phase 4C（Go/No-Go 后）
  ├── MiroFish NarrativePrediction schema + MiroFishAdapter
  └── 控制平面扩展（稳定读模型、审计 trail）
```
