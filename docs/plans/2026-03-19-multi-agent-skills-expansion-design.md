# Multi-Agent Skills Expansion — Design Document

**Date:** 2026-03-19
**Status:** Approved — Ready for Implementation
**Scope:** Phase 4B 前置工程，不依赖实验数据，可与 exp_002 并行推进

---

## 1. 背景与动机

### 当前状态

Pixiu 的 `SkillLoader` 已有三类注入机制（Type A/B/C），但覆盖面极度不均衡：

| Agent | LLM 调用 | Skill 注入 | 问题 |
|-------|----------|-----------|------|
| MarketAnalyst (Stage 1) | ✅ ReAct LLM | ❌ 无 | 无法指导 MCP 数据的结构化解读 |
| Researcher (Stage 2) | ✅ LLM | ⚠️ 部分接通 | `market_regime_detection.md` 存在但未注入 |
| PreFilter (Stage 3) | ✅ LLM gate | ❌ 无 | LLM gate 没有领域规范指导 |
| ExplorationAgent (Stage 4) | ✅ LLM system prompt | ❌ 无 | `EXPLORATION_SYSTEM_PROMPT` 无 skill 注入 |
| Coder (Stage 4) | ❌ 确定性执行 | N/A | 模板渲染器，无 LLM 调用，不需要 skill 注入 |
| Critic / Judgment (Stage 5) | ❌ 确定性评分 | N/A | 纯函数，无 LLM 调用，不需要 skill 注入 |

> **注**：`SkillLoader` 已有 `load_for_coder()` / `load_for_critic()` 方法，但这两个模块无 LLM 调用，这些方法是死代码，不在本次扩展范围内。

### 问题的影响

- Stage 1 生成的 `MarketContextMemo` 质量参差，缺乏结构化指导 → Stage 2 上下文噪声大
- Stage 3 PreFilter 的 LLM 判断没有领域约束 → 过滤标准不一致
- Stage 2 的 `market_regime_detection.md` 白写了 → regime-aware 推理未发挥作用
- Stage 4 `ExplorationAgent` 的 system prompt 无 A 股约束 → 生成代码质量不稳定
- Island-specific 差异化推理缺失 → 4 个活跃 island 用同一套 prompt

---

## 2. 设计目标

1. **LLM 节点全覆盖**：Stage 1-4 中每个有 LLM 调用的节点都有对应 Skill 注入
2. **静态可靠**：Skills 仍为静态 markdown 文件，人工维护，不自动修改（方案 C 留待未来）
3. **通用接口**：`SkillLoader` 迁移到 `load_for_agent(agent_role, state, **kwargs)` 通用接口，避免每加一个 agent 就要加一个方法
4. **可验证**：每个新 skill 必须有对应的注入调用和单测覆盖

---

## 3. 详细设计

### 3.1 SkillLoader 接口重构（P1）

当前 `load_for_researcher()` / `load_for_coder()` / `load_for_critic()` 模式违反 OCP（每加一个 agent 要加一个方法，且签名不一致）。

**新接口**：

```python
def load_for_agent(
    self,
    agent_role: str,          # "researcher" | "market_analyst" | "prefilter" | "exploration"
    state: dict | None = None,
    **kwargs,                 # e.g. subspace=, island=
) -> str:
    """
    通用 skill 加载入口。注入顺序：
      1. Type A: knowledge/skills/constraints/*.md（硬约束，所有 agent 共享）
      2. Type B: knowledge/skills/{agent_role}/*.md（角色固定 skill）
      3. Type C: 按 state / kwargs 条件注入（regime、island 等）
    """
```

**兼容处理**：现有 `load_for_researcher(state, subspace)` 改为调用
`load_for_agent("researcher", state, subspace=subspace)`，保持调用处不变。

**注入规则注册表**（YAML 或 dict，声明式定义 Type C 规则）：

```python
_CONDITIONAL_RULES = {
    "researcher": [
        # (condition_fn, skill_path)
        (lambda s, kw: s and (s.get("market_regime") or s.get("market_context")),
         "researcher/market_regime_detection.md"),
        (lambda s, kw: kw.get("island") in ISLAND_FILE_MAP,
         lambda s, kw: ISLAND_FILE_MAP[kw["island"]]),
    ],
    # 新增 agent 只需在这里加条目，不需要新方法
}
```

---

### 3.2 修复现有缺口：Researcher market_regime_detection.md 接通

`knowledge/skills/researcher/market_regime_detection.md` 已存在，但 `load_for_researcher()` 未注入。

迁移到新接口后，在 Type C 规则中加入：
```python
if state.get("market_regime") or state.get("market_context"):
    parts.append(self._load("researcher/market_regime_detection.md"))
```

---

### 3.3 新增 Stage 1 Skill：MarketAnalyst

**新文件**：`knowledge/skills/market_analyst/context_framing.md`

**定位**：Type B（永久注入），指导 MarketAnalyst 如何从 MCP 工具数据生成结构化的 `MarketContextMemo`

**核心内容**：
- 如何从价量数据提炼 regime 信号（趋势/震荡/高波动）
- 融资融券余额如何映射到 market_sentiment
- 新闻/公告如何归类为 policy_signal / sector_rotation / event_driven
- MarketContextMemo 各字段的填写标准和优先级

**调用点**：`src/agents/market_analyst.py` 的 `MARKET_ANALYST_SYSTEM_PROMPT` 构建处：
```python
skill_loader.load_for_agent("market_analyst")
```

---

### 3.4 新增 Stage 3 Skill：PreFilter

**新文件**：`knowledge/skills/prefilter/filter_guidance.md`

**定位**：Type A（硬约束注入），补充 LLM Gate（Filter C）的判断规范

**核心内容**：
- 什么样的假设必须拒绝（look-ahead bias 特征、无经济意义的公式结构）
- 什么样的假设应该放行（即使 IC 预估偏低，但机制解释清晰）
- Novelty 判断的标准（与已有因子的实质性差异 vs 参数微调）
- 常见误判模式（过度保守 / 过度宽松）

**调用点**：`src/agents/prefilter.py` 的 LLM Gate 的 system prompt 构建处：
```python
skill_loader.load_for_agent("prefilter")
```

---

### 3.5 新增 Stage 4 Skill：ExplorationAgent

**新文件**：`knowledge/skills/exploration/a_share_coding_constraints.md`

**定位**：Type B（永久注入），为 ExplorationAgent 补充 A 股回测代码规范

**核心内容**：
- 必须使用的 qlib API 模式（`qlib.init` 路径、`D.features` 用法）
- 禁止的代码模式（直接访问 `.csv`、引用未挂载数据）
- 数据可用范围声明（$close/$open/$high/$low/$volume/$factor/$vwap）
- 常见陷阱（未处理 NaN、日期索引不对齐、分组操作时 universe 泄漏）

**调用点**：`src/execution/exploration_agent.py` 的 `EXPLORATION_SYSTEM_PROMPT` 构建处：
```python
skill_loader.load_for_agent("exploration")
```

---

### 3.6 Island-Specific Skills（Researcher 扩展）

**范围收窄**：只为当前 4 个**默认活跃** island 创建 skill 文件（`DEFAULT_ACTIVE_ISLANDS = ["momentum", "northbound", "valuation", "volatility"]`）。`volume` 和 `sentiment` island 默认未激活，暂不创建，避免维护无效文件。

**新目录**：`knowledge/skills/researcher/islands/`

**新文件（4 个）**：
- `momentum.md` — 动量因子的 A 股特异性（T+1 时滞、追涨杀跌放大效应）
- `valuation.md` — 估值因子的 A 股适配（散户定价 vs 机构定价、壳资源溢价）
- `volatility.md` — 波动率因子的特征（涨跌停截断、日历效应）
- `northbound.md` — 北向资金数据特征与因子构建规范

**与 islands.py 的 description 字段区分**：`islands.py` 中的 `description` 是 island 的探索方向定义（what to explore），island skill 是 A 股市场约束知识（how to reason about it）。两者互补，不重叠。

**注入方式**（在 Type C 规则中）：
```python
ISLAND_FILE_MAP = {
    "momentum":   "researcher/islands/momentum.md",
    "valuation":  "researcher/islands/valuation.md",
    "volatility": "researcher/islands/volatility.md",
    "northbound": "researcher/islands/northbound.md",
}

if kw.get("island") in ISLAND_FILE_MAP:
    parts.append(self._load(ISLAND_FILE_MAP[kw["island"]]))
```

**调用点**：`researcher.py` 的 `generate_batch()` 中传入当前 `island` 参数。

---

## 4. 文件变更清单

### 新增文件（7 个）

```
knowledge/skills/market_analyst/context_framing.md        # Stage 1 skill
knowledge/skills/prefilter/filter_guidance.md             # Stage 3 skill
knowledge/skills/exploration/a_share_coding_constraints.md # Stage 4 skill
knowledge/skills/researcher/islands/momentum.md
knowledge/skills/researcher/islands/valuation.md
knowledge/skills/researcher/islands/volatility.md
knowledge/skills/researcher/islands/northbound.md
```

### 修改文件（5 个）

```
src/skills/loader.py          # 重构为通用接口 load_for_agent()，保持向后兼容
src/agents/market_analyst.py  # 接入 load_for_agent("market_analyst")
src/agents/prefilter.py       # 接入 load_for_agent("prefilter")
src/agents/researcher.py      # 传入 island 参数
src/execution/exploration_agent.py  # 接入 load_for_agent("exploration")
```

### 测试文件（需新增或修改）

```
tests/unit/test_skill_loader.py   # 新增 load_for_agent() 通用接口测试
tests/smoke/test_skills_smoke.py  # 每个 agent_role 的 smoke test（非空断言）
```

### 不需要修改（确认）

```
src/execution/coder.py        # 确定性执行器，无 LLM 调用，不需要 skill 注入
src/agents/judgment/          # 确定性评分模块，无 LLM 调用，不需要 skill 注入
```

---

## 5. Stage 2 MCP 工具访问（重要设计决策）

### 当前问题

Researcher（Stage 2）目前**无法主动调用 MCP 工具**。它只能被动接收 Stage 1 传来的 `MarketContextMemo` 作为上下文，无法在假设生成过程中按需查询实时数据。

这是 CLAUDE.md 中明确的当前优先级："让 Researcher 能主动消费 RSS / MCP 数据源"。

### 影响

- NARRATIVE_MINING 子空间无法访问新闻/公告数据，只能依赖 Stage 1 的摘要
- CROSS_MARKET 子空间无法查询实时行情印证假设
- 假设质量依赖 Stage 1 的信息完整性，存在信息传导损耗

### 设计选项

**选项 A：ReAct 模式（完整工具调用）**
将 `AlphaResearcher` 改造为带工具调用能力的 ReAct agent（类似 MarketAnalyst）。
- 优点：Researcher 可以按需查询数据，假设生成有实时信息支撑
- 缺点：增加延迟（每轮多次 MCP 调用）、LLM 调用次数增加、工具调用失败影响主链路
- 实现复杂度：中等

**选项 B：预置数据注入**
在 Stage 1 扩充 MarketContextMemo 的数据覆盖，将 Researcher 可能需要的数据预置进来（如近期新闻摘要、行业涨跌幅、资金流向）。Stage 2 仍为无工具的纯推理 agent。
- 优点：主链路不增加复杂度，Stage 1 已有 MCP 能力可扩展
- 缺点：Stage 1 需要"猜测" Researcher 会需要什么数据。现有 4 个子空间 × 4 个活跃 island = 16 种数据需求场景，Stage 1 无法预知，要么全量拉取（延迟/成本爆炸）要么遗漏关键数据（NARRATIVE_MINING 和 CROSS_MARKET 最严重）

**选项 C：子空间级别按需工具调用**
只对特定子空间（NARRATIVE_MINING、CROSS_MARKET）开启有限工具调用，其余子空间仍用纯推理。
- 优点：控制复杂度，只在最需要实时数据的子空间开放
- 缺点：架构分支增加，不同子空间行为不一致，测试覆盖复杂

**选项 D：Lazy-fetch 回调模式**
Stage 1 生成 MarketContextMemo 时，同时传入一个只读数据拉取闭包（`DataFetcher`）。Researcher 保持纯推理 agent（无 ReAct 循环、无工具绑定），但在生成过程中可同步调用 `fetcher.get(key, params)` 按需拉取特定数据点（如 `fetcher.get("sector_return", {"sector": "科技", "days": 5})`）。
- 优点：无 ReAct 复杂度，Researcher 保持纯推理；解决选项 B 的"Stage 1 猜测"问题
- 缺点：需要设计 DataFetcher 接口 + 注册可用查询；LangGraph 节点间传递 callable 需要谨慎处理序列化
- 实现复杂度：中低（DataFetcher 是薄封装，主体逻辑在 Stage 1 MCP 调用上）

### 本设计文档的立场

Stage 2 MCP 工具访问是独立的设计决策，**不阻塞 Skills 扩展**。建议：
1. 先执行 Skills 扩展（本文档）
2. exp_002 完成后，根据 NARRATIVE_MINING / CROSS_MARKET 子空间的假设质量决定是否引入工具调用
3. 优先评估选项 D（最低复杂度增量），其次选项 C（按子空间隔离风险）

---

## 6. 不在本设计范围内

- **Stage 2 MCP 工具调用**：见第 5 节，独立设计文档
- **方案 C（可进化 Skills）**：风险评估见附录，留待 exp_003+ 阶段
- **Skill 性能追踪**：不在本 phase，需要实验数据积累后再设计
- **Skills 版本管理**：当前用 git 隐式版本管理已足够
- **跨 Agent Skills 共享**：`a_share_constraints.md` 已经被多个 agent 使用，架构已支持，不需要额外设计
- **load_for_coder() / load_for_critic() 死代码清理**：列入技术债，单独清理

---

## 7. 验收标准

1. `uv run pytest -q tests -m "smoke or unit"` 全部通过（含原有 `load_for_researcher()` 相关测试向后兼容）
2. `tests/smoke/test_skills_smoke.py` 中每个 agent_role 均有测试，断言 `load_for_agent(role)` 返回非空字符串
3. 每个 island skill 文件路径均在 `ISLAND_FILE_MAP` 中有对应 key，且文件实际存在（可用 `test_skill_loader.py` 参数化断言）
4. 新 skill 文件内容通过人工 review（不是机器验证）

---

## 附录：方案 C 风险评估

自动进化 Skills 的核心风险：

1. **正反馈坍缩**：高 Sharpe 因子的写法被强化进 skill → 所有子空间收敛到同一因子族 → diversity 消失 → 系统从 exploration 退化为 exploitation
2. **过拟合传播**：样本内有效的模式被写入 skill → 后续所有假设继承该偏差 → in-sample bias 系统性扩大
3. **可复现性破坏**：两次相同实验因 skill 内容不同产生不同结果，审计失效
4. **对齐漂移**：skill 逐渐"教"模型绕过约束（如"这类公式可以绕过 Filter C"）

**缓解方案（未来设计）**：
- Skill 变更需人工审批（human-in-the-loop）
- Skill 变更的 A/B 测试窗口（新旧 skill 并行若干轮）
- Skill 内容的 diff review 机制（变更需 CIO 审批）
