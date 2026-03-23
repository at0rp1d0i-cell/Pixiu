# Phase 4B 受控实验计划

Status: active
Owner: coordinator
Last Reviewed: 2026-03-23

> 创建：2026-03-18
> 阶段：Phase 4A（数据上线）→ Phase 4B（受控实验）→ Phase 4C（MiroFish 接入 Go/No-Go）

---

## 背景

这份文档继续保留在 `docs/plans/`，但口径已经更新为**当前可执行的 Phase 4B 实验手册**，而不是早期“直接上 50 轮”的设想稿。

当前 Phase 4B 的核心现实不是“数据源已经齐全，可以直接长跑”，而是：

- Stage 1 已明确采用 `blocking core + async enrichment`
- 实验模式下 `blocking core timeout / degraded` 属于红灯
- Stage 3 数学安全必须按 `fail-closed` 口径执行
- 实验入口已经收口为显式 harness，而不是手工拼接命令
- 错误实验会污染 `control_plane_state / experiment_runs / artifacts`，因此 reset discipline 也是实验设计的一部分

当前仍需关注的缺口有：

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

**Phase 4B** 仍然是数据上线后、MiroFish 正式集成前的受控实验窗口，但当前目标要分成两层：

1. 先恢复实验可信度
2. 再在可信入口上建立 baseline，并为 Phase 4C 的 Go/No-Go 提供数据依据

---

## 1. 实验目标

本次实验需回答三个核心问题：

**Q0 — 入口可信度**：系统是否能在当前 harness discipline 下稳定完成 `single -> evolve 2 rounds`，且不触发 Stage 1/doctor 红灯？

**Q1 — 假设质量**：新数据是否提升了 Stage 3 通过率和最终 Sharpe 分布？

**Q2 — 子空间覆盖度**：哪个 island × subspace 组合在当前 regime 下产出最多有效信号？Thompson Sampling 调度器在观测期内是否开始表现出方向性偏好？

---

## 2. 实验设计

### 2.1 执行分期

Phase 4B 不再默认从 50 轮起跑，而改为**三级推进**：

| 分期 | 目标 | 默认入口 | 是否必须 |
|------|------|---------|---------|
| Gate 0 | 环境与数据真相自检 | `scripts/doctor.py --mode core` + `scripts/experiment_preflight.py` | 必须 |
| Gate 1 | 最小可信实验 | `scripts/run_experiment_harness.py`（默认不加 `--long-run`） | 必须 |
| Gate 2 | 扩展观测窗口 | `scripts/run_experiment_harness.py --long-run` 或显式长轮次 evolve | 仅在 Gate 1 全绿后 |

当前默认观察窗口应该是：

- `single`
- `evolve 2 rounds`

只有这两个阶段连续通过，才允许进入更长的观察窗口。

### 2.2 长轮次窗口

长轮次仍然保留，但不再是默认起手动作。

推荐顺序：

1. `single`
2. `evolve 2 rounds`
3. 如稳定，再进入 `10-20` 轮中等窗口
4. 只有中等窗口稳定，才考虑 `20+` 轮扩展窗口

`WARM_START_THRESHOLD=30` 仍然成立，因此对 Thompson Sampling 的收敛判断不能建立在 2 轮或 10 轮短跑上。短跑阶段回答的是“入口和链路是否可信”，不是“调度器是否已经收敛”。

### 2.3 冷启动分期

由于当前 FactorPool 尚无历史积累，无法建立真正的历史 baseline：

| 分期 | 轮次 | 说明 |
|------|------|------|
| Gate 1 | `single + evolve 2 rounds` | 只验证链路可信，不对调度器做统计结论 |
| Early observation | 约 10 轮 | 观察 Stage 3 通过率、Stage 4 稳定性和基本写回 |
| Main observation | `20+` 轮 | 只有在累计通过数接近或超过 `WARM_START_THRESHOLD=30` 时，才开始讨论调度器方向性偏好 |

### 2.4 控制变量

实验期间以下参数**不得修改**：

- `MAX_ROUNDS`、`ACTIVE_ISLANDS`（island 集合不变）
- Stage 3 所有硬 gate 阈值（`THRESHOLDS` 单例，`src/schemas/thresholds.py`）
- LLM 模型配置（`RESEARCHER_*` 环境变量）
- Stage 1 `blocking core + async enrichment` 边界
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

> **注意**：`AgentState.approved_notes` 是单轮数据。`loop_control_node` 在每轮结束时会清空该字段，因此不能依赖最终 state 做跨轮统计——必须从每轮 JSON 快照（`data/experiment_runs/{run_id}/round_*.json`）中捕获各轮快照，而不能读取实验结束后的 state。

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

## 4. 当前实验工件真相

当前 Phase 4B 优先依赖**结构化工件**，而不是追加大量临时日志：

- `scripts/doctor.py`
  - 回答 blocking/core optional/enrichment/data-plane 的健康状态
- `scripts/experiment_preflight.py`
  - 回答 profile/env/doctor 是否允许进入实验
- `scripts/run_experiment_harness.py`
  - 固化 `doctor(core) -> single -> evolve 2 rounds -> optional long run`
- `data/experiment_runs/{run_id}/round_*.json`
  - 记录每轮结构化诊断摘要
- `data/artifacts/`
  - 保存运行期产物

日志仍然有价值，但当前优先级低于 round JSON、preflight 输出和 harness 摘要。

---

## 5. 实验中止条件

出现以下任一情况，立即暂停实验并诊断，不强行继续：

| 条件 | 阈值 | 可能原因 |
|------|------|---------|
| `doctor(core)` blocking fail | 任意一次 | 数据/环境/API 真相不成立，不应启动实验 |
| Stage 1 blocking core timeout / degraded | 任意一次 | 当前轮市场上下文不可用，实验统计会被污染 |
| Stage 3 通过率连续为 0 | 连续 3 轮 | 数据源断连、LLM 输出格式异常、Stage 2 prompt 退化 |
| FactorPool 无新增有效因子 | 连续 5 轮 | Stage 4 执行错误、Critic 评分系统性偏低 |
| 未捕获异常率过高 | 任意阶段 > 50% | 新 MCP 工具兼容性问题、schema 不对齐 |
| `scheduler_state` 写入失败 | 连续 3 轮 | 控制平面 state_store 问题，Thompson Sampling 无法积累 |

诊断入口：`AgentState.last_error` + `AgentState.error_stage`。

---

## 6. 实验后决策框架

实验决策不再只在“50 轮完成后”做，而是分层决策：

- Gate 1 之后：判断入口是否可信
- 中等窗口后：判断是否值得进入扩展窗口
- 扩展窗口后：判断 MiroFish Go/No-Go

注意：`WARM_START_THRESHOLD=30`，Thompson Sampling 在积累约 30 个通过假设前处于近似均匀探索阶段。50 轮实验中不应默认“第 10 轮后自动收敛”，因此判断应基于实际达到阈值后的观测窗口。

| 决策问题 | 判断标准 | 结论为是 → | 结论为否 → |
|---------|---------|-----------|-----------|
| 入口已经可信了吗？ | `doctor(core)` 通过，`single -> evolve 2 rounds` 无红灯，且 round 工件可追溯 | 进入中等窗口 | 继续修 Stage 1 / Stage 3 / env truth / doctor，不上长轮次 |
| 新数据有实质价值吗？ | `NARRATIVE_MINING` 子空间或注入新 AKShare regime 数据的 `FACTOR_ALGEBRA` 子空间的 Stage 3 通过率 > 其余子空间均值 | 继续扩展对应数据源 | 先诊断子空间 prompt，可能是信号到假设的转化链问题 |
| Thompson Sampling 开始显著偏向吗？ | 某子空间 Thompson Sampling 权重 > 0.4，且该状态出现在达到 `WARM_START_THRESHOLD` 之后 | 说明有明显优势子空间，可重点投入该方向 | 继续均匀探索或降低阈值后重测 |
| NARRATIVE_MINING 值得接入 MiroFish 吗？ | `NARRATIVE_MINING` 子空间通过率 > 25% 且通过假设平均 Sharpe 均值 > 3.0（高于系统硬 gate 2.67，表明新数据产出质量更优假设）| 进入 Phase 4C：接入 MiroFish NarrativePrediction schema | 先优化 NARRATIVE_MINING 子空间 prompt，延迟 MiroFish 接入 |
| FactorPool 质量是否稳定？ | 观测期（Round 11–50）有效因子数单调递增 | 系统整体健康，可进入下一阶段 | 排查 FailureConstraint Filter D 是否误拦截 |

---

## 实验可追溯性设计

实验必须做到完全透明、全程可追溯。每轮产出的关键数据必须持久化，不能依赖日志解析。

### 每轮快照（必须实现）
`loop_control_node` 重置 state 前，在 `data/experiment_runs/{run_id}/` 目录写入 JSON 快照：
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

### 实验前基线快照
在第 1 轮开始前，记录初始 FactorPool 状态（因子数、子空间分布）作为基线。

---

## 7. 实验执行 SOP

```bash
# Step 0：必要时先看 reset 计划
uv run python scripts/reset_experiment_state.py --dry-run

# Step 1：如需清理失败运行痕迹，再执行 reset
# 注意：默认不删除 data/factor_pool_db/
uv run python scripts/reset_experiment_state.py

# Step 2：确认默认测试入口通过
uv run pytest -q tests -m "smoke or unit"

# Step 3：先跑 doctor(core)
uv run python scripts/doctor.py --mode core

# Step 4：跑 preflight，确认 profile/env/doctor 真相
uv run python scripts/experiment_preflight.py --json

# Step 5：跑最小可信实验
uv run python scripts/run_experiment_harness.py --json

# Step 6：只有 Step 5 全绿，才允许长轮次
uv run python scripts/run_experiment_harness.py --long-run --json
```

执行约束：

- 任何一步出现 blocking fail，都停止，不直接上长轮次
- `reset` 是按需动作，不是每次实验默认前置
- `factor_pool_db` 默认保留，因为通过因子是知识资产
- 长轮次只在 `single + evolve 2 rounds` 已可信时启动

---

## 8. 预期产出

| 产出物 | 说明 | 用途 |
|--------|------|------|
| preflight JSON | `scripts/experiment_preflight.py --json` 输出 | 判断当前 profile/env/doctor 是否可信 |
| harness JSON | `scripts/run_experiment_harness.py --json` 输出 | 判断最小实验是否真正通过 |
| round snapshots | `data/experiment_runs/{run_id}/round_*.json` | 结构化分析各轮 Stage 结果 |
| FactorPool 快照 | `data/factor_pool_db/` | 保留通过因子与知识资产 |
| 中等/长窗口统计摘要 | 基于 round JSON 聚合 | 判断是否值得继续扩展窗口 |
| MiroFish Go/No-Go 备忘录 | 基于第 6 节决策框架填写 | Phase 4C 启动依据 |

---

## 附：Phase 4 整体路线图

```
Phase 4A（当前）
  ├── 新增 RSS MCP server（公告/政策/财经新闻）
  └── 扩展 AKShare MCP 工具集（融资余额/宽度/涨停池/轮动速度）

Phase 4B（本计划）
  ├── Gate 0：doctor/preflight/harness 入口可信化
  ├── Gate 1：single + evolve 2 rounds
  └── Gate 2：中等/长窗口观测，建立 baseline，验证新数据价值

Phase 4C（Go/No-Go 后）
  ├── MiroFish NarrativePrediction schema + MiroFishAdapter
  └── 控制平面扩展（稳定读模型、审计 trail）
```
