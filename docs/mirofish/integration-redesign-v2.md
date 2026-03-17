# Pixiu × MiroFish 集成重新设计（v2.0）

> 基于 MiroFish 技术真相调研更新 | 2026-03-17
> 前版本：`integration-feasibility-and-plan.md`（v1.1，offline-first 情绪管道定位）
> 本版本核心变化：将 MiroFish 从"情绪数据管道"重新定位为"社会仿真验证器 + 叙事种子生成器"

---

## 1. MiroFish 技术真相（调研结论）

### 1.1 核心定位

MiroFish 是**群体智能仿真引擎**（Swarm Intelligence Engine），不是金融情绪分析工具。

> "By extracting seed information from the real world, it automatically constructs a high-fidelity parallel digital world. Within this space, thousands of intelligent agents with independent personalities, long-term memory, and behavioral logic freely interact and undergo social evolution."

### 1.2 工作流

```
1. Graph Building
   输入: 种子文档（新闻/政策/报告/数据分析报告）
   → 实体/关系提取 → GraphRAG 构建（Zep 图记忆）

2. Environment Setup
   → 生成数千个有独立人格的 AI Agent
   → Persona 注入：职业、观点偏好、信息获取习惯

3. Simulation（OASIS 驱动）
   → 双平台仿真（Twitter 类 + Reddit 类）
   → 每轮：Agent 发帖、点赞、讨论
   → 记录 AgentAction（round_num, platform, agent_id, action_type, content）

4. Report Generation
   → ReportAgent（LangChain ReACT + Zep 工具）
   → 输出: 预测报告 Markdown + agent_log.jsonl

5. Deep Interaction
   → 与仿真世界中的任意 Agent 对话
```

### 1.3 技术栈

| 组件 | 实现 |
|------|------|
| 仿真引擎 | OASIS (CAMEL-AI) |
| 记忆存储 | Zep Cloud（图记忆） |
| 后端 | Python + Flask |
| 前端 | Node.js / React |
| LLM | OpenAI 兼容 API（支持 DeepSeek） |

### 1.4 当前输出格式

| 输出 | 格式 | 结构化程度 |
|------|------|----------|
| 预测报告 | Markdown | 非结构化，需解析 |
| Agent 动作日志 | JSONL (`agent_log.jsonl`) | 半结构化 |
| 图记忆 | Zep Graph API | 需 API 访问 |

---

## 2. 为什么旧定位（情绪管道）不够准确

旧的 v1 方案把 MiroFish 当"更好的情绪数据源"，面临两个根本问题：

1. **能力错配**：MiroFish 的核心是"模拟群体动力学演化过程"，而不是"标注情绪极性"。把仿真引擎当情绪标注器是大材小用。

2. **价值被低估**：MiroFish 真正独特的产出是**情景演化路径**和**意见分歧的动态过程**，而不是单点情绪得分。

---

## 3. 新定位：社会仿真验证器 + 叙事种子生成器

### 3.1 核心价值主张

MiroFish 回答一个 Pixiu 当前无法回答的问题：

> **"这个市场叙事（narrative）会在投资者社区中传播和主导吗？"**

A 股 alpha 大量藏在叙事层：政策口径、产业链故事、预期错位。而叙事的有效性，不只取决于它"是否正确"，还取决于"是否被足够多的市场参与者接受并行动"。

MiroFish 可以模拟这个传播过程：
- **输入**：一个事件 + 一个叙事假设
- **仿真**：数千个模拟市场参与者（散户/机构/媒体/分析师）的讨论和行动
- **输出**：这个叙事在仿真社区中的传播广度、持续时间、分歧程度

### 3.2 具体集成模式

```
MiroFish（离线批处理，每日或事件触发）

  输入: 当日重要事件/政策 + 预测需求
       "模拟 A 股投资者社区对 {事件} 的反应，
        重点关注: 哪些板块会被讨论? 情绪持续多久? 分歧有多大?"

  仿真过程: 数千 agent 在模拟平台上讨论

  输出 → MiroFishAdapter 解析 →

NarrativePrediction（新 schema）:
  {
    trigger_event: str          # 触发事件描述
    snapshot_id: str            # 版本化快照 ID（可复现性）
    available_at: str           # 快照生成时间（point-in-time 基准）
    dominant_narrative: str     # 主导叙事（从发帖内容提取）
    affected_sectors: List[str] # 被反复提及的板块
    opinion_divergence: float   # 意见分歧度（0=高度一致, 1=极度分裂）
    narrative_velocity: float   # 叙事传播速度（每轮新参与 agent 数）
    confidence: float           # 基于 agent 行为一致性
    sentiment: str              # "bullish"|"bearish"|"mixed"
    simulated_rounds: int       # 仿真轮次（时间代理变量）
    mirofish_report_excerpt: str # 报告关键段落
  }
```

### 3.3 在 Pixiu Pipeline 中的消费位置

```
Stage 1 (MarketAnalyst):
  MarketContextMemo 新增字段:
    narrative_predictions: List[NarrativePrediction] = []

  → MarketAnalyst 从离线快照文件夹加载当日 NarrativePrediction
  → 注入 raw_summary 和 suggested_islands 生成时的上下文

Stage 2 (NARRATIVE_MINING 子空间):
  build_narrative_mining_context() 注入 NarrativePrediction:
    "MiroFish 仿真显示以下叙事在市场参与者中具有高传播性:
     - {dominant_narrative} (分歧度: {opinion_divergence:.2f})
     - 受影响板块: {affected_sectors}
     建议优先基于这些叙事构建假设，它们有社会仿真背书"

  效果: NARRATIVE_MINING 子空间生成的 FactorResearchNote 不再只是
       "LLM 联想叙事"，而是"有社会传播验证的叙事假设"

FailureConstraint（追踪 narrative alpha）:
  FailureConstraint 新增字段:
    prediction_source: str = "llm_only"  # "mirofish" | "llm_only"

  → 当 note 来自 MiroFish 叙事时，constraint 记录来源
  → 可以统计 MiroFish 来源假设 vs 纯 LLM 假设的通过率差异
  → 建立 narrative alpha track record
```

---

## 4. 与旧方案对比

| 维度 | v1（情绪管道） | v2（社会仿真验证器） |
|------|--------------|------------------|
| MiroFish 角色 | 数据生产者 | 假设验证器 + 种子生成器 |
| 输出类型 | 情绪得分/标签 | 叙事传播路径 + 置信度 |
| Pixiu 消费位置 | Stage 1 原始数据 | Stage 1 上下文 + Stage 2 NARRATIVE_MINING |
| A 股 alpha 来源 | 情绪因子（已拥挤） | 叙事 alpha（差异化） |
| 可量化性 | 高（情绪得分直接入因子） | 中（需要 track record 积累） |
| 差异化程度 | 低（很多系统都在做情绪因子） | 高（社会仿真验证叙事是独特能力） |

---

## 5. 技术集成关键问题与解答

### Q1: MiroFish 输出非结构化，怎么解析？

**方案**：两层解析

- Layer 1（确定性）：从 `agent_log.jsonl` 统计 CREATE_POST 的主题词频，提取 `dominant_narrative` 和 `affected_sectors`
- Layer 2（LLM 辅助）：用 DeepSeek 对报告 Markdown 做一次结构化提取，输出 `NarrativePrediction` JSON

总调用成本：MiroFish 仿真本身（高成本）+ 一次 DeepSeek 提取（低成本）。

### Q2: 如何保证 Point-in-Time 合规？

每次 MiroFish 仿真结束后：
1. 生成 `snapshot_{date}_{event_hash}.json`（包含 `available_at` 时间戳）
2. `MiroFishAdapter` 读取时检查 `snapshot.available_at < backtest_period_start`
3. 违反 PiT 的快照自动过滤

### Q3: MiroFish 仿真的可复现性如何保证？

- 固化 `snapshot_id` = `sha256(seed_doc + prediction_requirement + config)`
- 同一 `snapshot_id` 总是读取同一快照文件
- Pixiu 不在运行时触发 MiroFish 重新仿真，只消费已有快照

### Q4: A 股投资者的角色建模是否准确？

这是最大的不确定性。MiroFish 的默认 persona 生成是通用的，没有专门针对 A 股散户/机构特征建模。

**缓解**：
- 在 MiroFish 的种子文档中注入 A 股市场参与者特征描述
- 在 persona 生成 prompt 中指定：散户（60%）、游资（20%）、机构（15%）、媒体（5%）的行为模式
- Phase 1 接受低精度 persona，通过 track record 积累判断有效性

### Q5: 成本控制

MiroFish 每次仿真需要大量 LLM 调用（数千 agent × N 轮）。控制策略：
- 每日只对"重大事件"触发仿真（有阈值筛选）
- 轻量仿真（< 100 agents, < 10 rounds）用于快速验证
- 完整仿真（500+ agents, 40+ rounds）用于重要事件的深度分析
- 使用成本较低的 DeepSeek 作为 agent 的 LLM 后端

---

## 6. 分阶段实施路径

### Gate-0（已满足）
- [x] Phase 2 完成（Stage 2 Hypothesis Expansion Engine）
- [x] 331 smoke/unit tests 通过
- [x] Stage 4/5 deterministic golden path 未被影响

### Phase 3.5：MiroFish 协议层（Week 1）

交付物：
- `src/schemas/market_context.py` — `NarrativePrediction` schema
- `src/datasources/mirofish_adapter.py` — 快照加载 + 解析接口
- `tests/test_mirofish_adapter.py` — 单元测试（用 mock 快照）

**不需要 MiroFish 实际运行**，只需要定义协议。

### Phase 3.6：适配器实现（Week 2）

交付物：
- `MiroFishAdapter.parse_snapshot(snapshot_path) -> NarrativePrediction`
- `MiroFishAdapter.load_daily_snapshots(date) -> List[NarrativePrediction]`
- `agent_log.jsonl` 解析逻辑（主题词频提取）

### Phase 3.7：Pixiu 集成（Week 3）

交付物：
- `market_analyst.py` — 加载当日 NarrativePrediction
- `subspace_context.py` — `build_narrative_mining_context` 注入 MiroFish 预测
- `failure_constraint.py` — `prediction_source` 字段

### Phase 3.8：Track Record（Week 4+）

交付物：
- MiroFish 来源假设 vs 纯 LLM 假设的通过率统计
- 命中率报告生成
- 决策：是否将 MiroFish 升级为 NARRATIVE_MINING 的主要来源

---

## 7. 风险清单

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| A 股 persona 建模不准确 | 高 | 中 | 通过 track record 校准，Phase 3.8 再评估 |
| MiroFish 仿真成本过高 | 中 | 高 | 分级仿真策略（轻量/完整），阈值触发 |
| 叙事→价格传导机制不稳定 | 高 | 中 | FailureConstraint 追踪失败叙事，不依赖单一信源 |
| 输出解析精度不足 | 中 | 低 | 两层解析（统计+LLM），接受 MVP 低精度 |
| 前视偏差 | 中 | 高 | snapshot available_at 严格管理，自动过滤 |

---

## 8. 与 CLAUDE.md 架构原则的对齐

| 原则 | 对齐状态 |
|------|---------|
| 扩大 hypothesis space，不扩大 execution power | ✅ MiroFish 只影响 Stage 1/2，不改 Stage 4/5 |
| 不把 Pixiu 定义成投顾团队 | ✅ MiroFish 产出 research objects，不产出投资建议 |
| 失败经验变成约束 | ✅ prediction_source 追踪，失败叙事变 FailureConstraint |
| Stage 4/5 deterministic golden path | ✅ 明确非目标：不改执行层 |
| 上游极强探索，中游严格收缩 | ✅ MiroFish 增强 Stage 1/2 探索，Stage 3 不变 |
