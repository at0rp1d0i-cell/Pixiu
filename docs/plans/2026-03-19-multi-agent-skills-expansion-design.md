# Multi-Agent Skills Expansion — Design Document

**Date:** 2026-03-19
**Status:** Draft — Pending coworker review
**Scope:** Phase 4B 前置工程，不依赖实验数据，可与 exp_002 并行推进

---

## 1. 背景与动机

### 当前状态

Pixiu 的 `SkillLoader` 已有三类注入机制（Type A/B/C），但覆盖面极度不均衡：

| Agent | Skill 注入 | 问题 |
|-------|-----------|------|
| Researcher (Stage 2) | ✅ 已接通（本 session 修复） | `market_regime_detection.md` 存在但未注入 |
| MarketAnalyst (Stage 1) | ❌ 无 | 无法指导 MCP 数据的结构化解读 |
| PreFilter (Stage 3) | ❌ 无 | LLM gate 没有领域规范指导 |
| Coder (Stage 4) | ⚠️ 有方法但未确认调用 | `load_for_coder()` 存在但未核实是否被调用 |
| Critic / Judgment (Stage 5) | ⚠️ 有方法但未确认调用 | `load_for_critic()` 存在但未核实，`portfolio/construction_principles.md` 未注入 |

### 问题的影响

- Stage 1 生成的 `MarketContextMemo` 质量参差，缺乏结构化指导 → Stage 2 上下文噪声大
- Stage 3 PreFilter 的 LLM 判断没有领域约束 → 过滤标准不一致
- Stage 2 的 `market_regime_detection.md` 白写了 → regime-aware 推理未发挥作用
- Island-specific 差异化推理缺失 → 6 个 island 用同一套 prompt

---

## 2. 设计目标

1. **全链路 Skill 覆盖**：Stage 1-5 的每个有 LLM 调用的节点都有对应 Skill 注入
2. **静态可靠**：Skills 仍为静态 markdown 文件，人工维护，不自动修改（方案 C 留待未来）
3. **最小侵入**：主要在 `knowledge/skills/` 层新增文件 + `SkillLoader` 扩展方法，不改 schema
4. **可验证**：每个新 skill 必须有对应的注入调用和单测覆盖

---

## 3. 详细设计

### 3.1 修复现有缺口

#### 3.1.1 Researcher — market_regime_detection.md 接通

`knowledge/skills/researcher/market_regime_detection.md` 已存在，但 `load_for_researcher()` 未注入。

修改：在 `SkillLoader.load_for_researcher()` 中加入 Type C 条件注入：
```python
# 有 regime 信息时注入 regime 检测规范
if state.get("market_regime") or state.get("market_context"):
    parts.append(self._load("researcher/market_regime_detection.md"))
```

#### 3.1.2 Coder — 确认并接通 load_for_coder()

检查 `src/execution/coder.py` 或 `exploration_agent.py` 是否调用了 `SkillLoader.load_for_coder()`。若未调用，在 coder 的 system prompt 构建处补入。

#### 3.1.3 Critic — 确认并扩展 load_for_critic()

检查 `src/agents/judgment/` 下是否调用了 `SkillLoader.load_for_critic()`。若未调用，接通。同时将 `portfolio/construction_principles.md` 加入 Critic 的注入列表。

---

### 3.2 新增 Stage 1 Skill：MarketAnalyst

**新文件**：`knowledge/skills/market_analyst/context_framing.md`

**定位**：Type B（永久注入），指导 MarketAnalyst 如何从 MCP 工具数据生成结构化的 `MarketContextMemo`

**核心内容**：
- 如何从价量数据提炼 regime 信号（趋势/震荡/高波动）
- 融资融券余额如何映射到 market_sentiment
- 新闻/公告如何归类为 policy_signal / sector_rotation / event_driven
- MarketContextMemo 各字段的填写标准和优先级

**SkillLoader 扩展**：新增 `load_for_market_analyst()` 方法。

**调用点**：`src/agents/market_analyst.py` 的 `MARKET_ANALYST_SYSTEM_PROMPT` 构建处。

---

### 3.3 新增 Stage 3 Skill：PreFilter

**新文件**：`knowledge/skills/prefilter/filter_guidance.md`

**定位**：Type A（硬约束注入），补充 LLM Gate（Filter C）的判断规范

**核心内容**：
- 什么样的假设必须拒绝（look-ahead bias 特征、无经济意义的公式结构）
- 什么样的假设应该放行（即使 IC 预估偏低，但机制解释清晰）
- Novelty 判断的标准（与已有因子的实质性差异 vs 参数微调）
- 常见误判模式（过度保守 / 过度宽松）

**SkillLoader 扩展**：新增 `load_for_prefilter()` 方法。

**调用点**：`src/agents/prefilter.py` 的 LLM Gate 的 system prompt 构建处。

---

### 3.4 Island-Specific Skills（Researcher 扩展）

**新目录**：`knowledge/skills/researcher/islands/`

**新文件**（6 个）：
- `momentum.md` — 动量因子的 A 股特异性（T+1 时滞、追涨杀跌放大效应）
- `valuation.md` — 估值因子的 A 股适配（散户定价vs机构定价、壳资源溢价）
- `volatility.md` — 波动率因子的特征（涨跌停截断、日历效应）
- `volume.md` — 成交量/换手率因子的信号解读（流动性溢价、主力行为）
- `northbound.md` — 北向资金数据特征与因子构建规范
- `sentiment.md` — 情绪类因子（如有）

**注入方式**：在 `load_for_researcher()` 中新增按 island 条件注入：
```python
if island is not None:
    island_file_map = {
        "momentum": "researcher/islands/momentum.md",
        "valuation": "researcher/islands/valuation.md",
        # ... etc
    }
    island_path = island_file_map.get(island)
    if island_path:
        parts.append(self._load(island_path))
```

**调用点**：`researcher.py` 的 `generate_batch()` 中需传入当前 `island` 参数。

---

## 4. 文件变更清单

### 新增文件（9 个）
```
knowledge/skills/market_analyst/context_framing.md       # Stage 1 skill
knowledge/skills/prefilter/filter_guidance.md            # Stage 3 skill
knowledge/skills/researcher/islands/momentum.md
knowledge/skills/researcher/islands/valuation.md
knowledge/skills/researcher/islands/volatility.md
knowledge/skills/researcher/islands/volume.md
knowledge/skills/researcher/islands/northbound.md
knowledge/skills/researcher/islands/sentiment.md
```

### 修改文件（4 个）
```
src/skills/loader.py          # 新增方法 + 修复现有注入
src/agents/market_analyst.py  # 接入 load_for_market_analyst()
src/agents/prefilter.py       # 接入 load_for_prefilter()
src/agents/researcher.py      # 传入 island 参数给 SkillLoader
```

### 可能需要修改（2 个，确认后决定）
```
src/execution/coder.py 或 exploration_agent.py  # 确认 load_for_coder() 调用
src/agents/judgment/                             # 确认 load_for_critic() 调用
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

**选项 B：预置数据注入（推荐）**
在 Stage 1 扩充 MarketContextMemo 的数据覆盖，将 Researcher 可能需要的数据预置进来（如近期新闻摘要、行业涨跌幅、资金流向）。Stage 2 仍为无工具的纯推理 agent。
- 优点：主链路不增加复杂度，Stage 1 已有 MCP 能力可扩展
- 缺点：Stage 1 需要"猜测"Researcher 会需要什么数据，存在信息浪费或遗漏

**选项 C：子空间级别按需工具调用**
只对特定子空间（NARRATIVE_MINING、CROSS_MARKET）开启有限工具调用，其余子空间仍用纯推理。
- 优点：控制复杂度，只在最需要实时数据的子空间开放
- 缺点：架构分支增加，不同子空间行为不一致

### 本设计文档的立场

Stage 2 MCP 工具访问是独立的设计决策，**不阻塞 Skills 扩展（方案 B）**。建议：
1. 先执行 Skills 扩展（本文档）
2. 单独写一份"Stage 2 工具化"设计文档，评估 A/B/C 选项
3. exp_002 观察实验结果后再决定是否引入工具调用

---

## 6. 不在本设计范围内

- **Stage 2 MCP 工具调用**：见第 5 节，独立设计文档
- **方案 C（可进化 Skills）**：风险评估见附录，留待 exp_003+ 阶段
- **Skill 性能追踪**：不在本 phase，需要实验数据积累后再设计
- **Skills 版本管理**：当前用 git 隐式版本管理已足够
- **跨 Agent Skills 共享**：`a_share_constraints.md` 已经被多个 agent 使用，架构已支持，不需要额外设计

---

## 6. 验收标准

1. `uv run pytest -q tests -m "smoke or unit"` 全部通过
2. 所有 `load_for_*()` 方法均有对应的 smoke test 覆盖
3. Stage 1-5 的每个 LLM 调用点都能在 debug 日志中看到 SkillLoader 加载记录
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
