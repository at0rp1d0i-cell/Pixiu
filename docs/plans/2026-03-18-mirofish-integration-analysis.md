# MiroFish 集成分析与建议

Status: active
Owner: coordinator
Last Reviewed: 2026-03-18

> 2026-03-18 | 基于 v2 技术调研（`docs/futures/mirofish-integration-redesign-v2.md`）
> 状态：决策参考文档，不是实现规格

---

## 1. 执行摘要

**MiroFish 的核心能力是社会仿真验证器，不是情绪标注工具。** 它回答一个 Pixiu 当前无法回答的问题："这个市场叙事会在投资者社区中传播并主导吗？" 这恰好是 NARRATIVE_MINING 子空间最缺的能力背书。

**建议：两步走，现在只做协议层。**

- **Step 1（现在，Phase 4A）**：定义 `NarrativePrediction` schema 和 `MiroFishAdapter` 接口签名，用 mock 快照写测试。零 LLM 调用，零新 API。
- **Step 2（Phase 4C，5-10 轮实验后）**：接入真实仿真，前提是 NARRATIVE_MINING 子空间有实验数据支撑。

**现在不需要申请任何新 API，不需要 MiroFish 实际运行。**

---

## 2. MiroFish 能力评估

MiroFish 的工作流是：输入种子文档（新闻/政策/研报）→ 构建实体关系图（Zep 图记忆）→ 生成数千个有独立人格的 AI Agent（散户/机构/媒体/分析师）→ OASIS 引擎驱动多轮社会仿真 → 产出预测报告。

关键输出有两类：Markdown 格式的预测报告（非结构化，需解析）和 `agent_log.jsonl`（半结构化，可统计）。技术栈与 Pixiu 兼容：Python 后端，支持 DeepSeek 作为 Agent LLM 后端（成本可控）。

v1 方案把 MiroFish 当"情绪标注器"是能力错配。它真正稀缺的产出是**叙事传播的动态路径**：哪些板块被反复提及、意见分歧有多大、传播速度多快。这些信息单靠 LLM 联想无法生成，必须通过仿真过程涌现。

---

## 3. 对 Pixiu 的价值定位

### 值得做

**NARRATIVE_MINING 叙事种子验证。** Stage 2 的 NARRATIVE_MINING 子空间当前产出的是"LLM 联想叙事"，可信度取决于模型本身的 A 股知识。MiroFish 仿真可以为筛选出的叙事补充社会传播维度的置信度——"这个叙事在模拟投资者社区中是否真的传播"。这把假设从"LLM 觉得合理"升级为"社会仿真验证过"。

**FailureConstraint 来源追踪。** 在 `FailureConstraint` 记录 `prediction_source`（`mirofish` vs `llm_only`），可以随着实验轮次积累比较两类假设的 Stage 3 通过率差异，建立 narrative alpha track record。这是系统自我校准的基础。

**Stage 1 上下文注入。** `MarketContextMemo` 新增 `narrative_predictions: List[NarrativePrediction]`，为 MarketAnalyst 提供当日社会仿真信号，影响 `suggested_islands` 生成方向。

### 不必做

- **实时在线服务**：MiroFish 每次仿真需要数千 Agent × N 轮 LLM 调用，成本和延迟均不可控。Pixiu 的研究节奏是天级别，离线批处理足够。
- **影响 Stage 4/5 执行层**：违反 Pixiu 架构原则（不扩大 execution power）。仿真信号只应停在 Stage 1/2 上下文层。
- **替代 RSS/Tavily 做基础新闻获取**：MiroFish 是推理引擎，不是信息采集工具，用它做新闻抓取是大材小用。
- **Stage 3 PreFilter 不消费 MiroFish 信号**：叙事仿真信号只停在 Stage 1/2 上下文层，不作为 Stage 3 通过/拒绝的判断依据。这是 Pixiu "中游严格收缩"原则的要求。

---

## 4. 两步走方案

### Step 1：协议层（Phase 4A，现在）

**目标**：定义合约，不实现仿真。代码可合并，测试可通过，MiroFish 不需要运行。

**交付物：**

`src/schemas/market_context.py` 新增 `NarrativePrediction`：

```python
class NarrativePrediction(BaseModel):
    trigger_event: str           # 触发事件描述
    snapshot_id: str             # sha256(seed_doc + config)，可复现
    available_at: datetime       # 快照生成时间，Point-in-Time 基准
    dominant_narrative: str      # 主导叙事（从发帖内容提取）
    affected_sectors: List[str]  # 被反复提及的板块
    opinion_divergence: float    # 意见分歧度（0=高度一致, 1=极度分裂）
    narrative_velocity: float    # 传播速度（每轮新参与 agent 占总 agent 比例（0.0-1.0））
    confidence: float            # 基于 agent 行为一致性
    sentiment: Literal["bullish", "bearish", "mixed"]
    simulated_rounds: int        # 仿真轮次
    agent_count: int             # 仿真 agent 总数（轻量<100 / 完整500+）
    source_version: str          # 仿真引擎/解析链版本（track record 可追溯）
    mirofish_report_excerpt: str # 报告关键段落
```

这里显式保留 `agent_count` 和 `source_version`，用于跨轻量/完整版仿真比较。
`narrative_velocity` 必须是比率而不是绝对人数，否则不同仿真规模间不可比。

`src/datasources/mirofish_adapter.py` 只定义接口签名，不实现仿真调用：

```python
class MiroFishAdapter:
    def parse_snapshot(self, snapshot_path: Path) -> NarrativePrediction: ...
    def load_daily_snapshots(self, date: date) -> List[NarrativePrediction]: ...
```

`tests/test_mirofish_adapter.py` 使用 mock 快照 JSON 文件做单元测试，验证 schema 解析和 PiT 过滤逻辑。

**成本**：纯代码，零 LLM 调用，零新 API key。

### Step 2：真实仿真接入（Phase 4C，实验后）

**Go 标准（需全部满足才启动）：**

1. 完成 Phase 4B 受控实验并拿到稳定观测窗口
2. NARRATIVE_MINING 子空间在 Stage 3 的通过率有足够样本量（绝对数 ≥ 20 个假设）
3. 轻量仿真（< 100 agents，< 10 rounds）的 DeepSeek 成本估算可接受
4. **标准 4（persona 可用性验证）**：选取 3 个历史上有明显市场反应的 A 股重大事件（如注册制改革、北向资金限购、某板块重大政策），用 MiroFish 轻量仿真（50 agents, 5 rounds）回测，人工判断仿真社区的反应方向（看涨/看跌/中性）与当时实际市场反应方向的一致性 >= 2/3。接受 Phase 4C 初期 persona 精度有限，通过 track record 积累进行事后校准。

**实现内容：**

- `MiroFishAdapter` 真实解析逻辑：`agent_log.jsonl` 主题词频统计（Layer 1）+ DeepSeek 结构化提取（Layer 2）
- `market_analyst.py` 加载当日 `NarrativePrediction` 快照，注入 `MarketContextMemo`
- `subspace_context.py` 的 `build_narrative_mining_context()` 消费 `NarrativePrediction`，为 NARRATIVE_MINING 子空间提供仿真背书
- `FailureConstraint` 新增 `prediction_source: str = "llm_only"`

**注意**：Step 2 的实验窗口后（Phase 4B 对应），再根据 track record 决策是否将 MiroFish 升级为 NARRATIVE_MINING 的主要来源。

---

## 5. 关键风险

**风险 A：A 股 persona 建模不准确（概率高，影响中）**
MiroFish 的默认 persona 生成是通用的，没有针对 A 股散户/游资/机构的特征建模。缓解：在种子文档中注入 A 股市场参与者特征描述，Phase 4C 接受低精度 persona，通过 track record 积累校准，而非假设一开始就准确。

**风险 B：仿真成本过高（概率中，影响高）**
完整仿真（500+ agents，40+ rounds）的 LLM 调用量庞大。缓解：分级策略——只对"重大事件"触发仿真，默认使用轻量仿真（< 100 agents，< 10 rounds）做快速验证，使用 DeepSeek 降低单次调用成本。Go 标准中明确要求成本估算通过后才启动 Step 2。

**风险 C：前视偏差（概率中，影响高）**
快照生成时间晚于回测起始日会引入未来信息。缓解：每个 `NarrativePrediction` 携带 `available_at` 时间戳，`MiroFishAdapter` 在加载时自动过滤 `available_at >= backtest_period_start` 的快照，这是硬过滤，不可绕过。

**风险 D：A 股涨跌停板对叙事→价格传导的时滞**
- 风险：A 股有涨跌停板+T+1 机制，叙事在舆论层传播很快，但实际资金流入可能因涨停锁死被推迟。仿真结果到价格传导之间有 A 股特有的结构性时滞，仿真可能系统性低估传播速度与价格反应之间的延迟。
- 缓解：在 NarrativePrediction 消费时，加注"仿真传播速度不等于价格响应速度"的上下文说明；后续 track record 分析时单独统计"叙事传播与价格反应时差"。

**风险 E：监管干预导致叙事突变**
- 风险：A 股监管层（证监会/交易所）会直接干预叙事传播，MiroFish 的仿真模型没有"监管干预"机制，可能系统性高估叙事持续性。
- 缓解：在种子文档中注入"A 股监管可能随时介入"的 persona 约束；Phase 4C 接入后观察监管事件期间的仿真误差。

---

## 6. 架构合规性检查

| Pixiu 核心原则 | MiroFish 集成对齐状态 |
|---|---|
| 扩大 hypothesis space，不扩大 execution power | MiroFish 只影响 Stage 1/2 上下文，Stage 4/5 不受影响 |
| Stage 4/5 deterministic golden path 不受影响 | 明确非目标：不改执行层任何逻辑 |
| Point-in-Time 合规 | `available_at` 字段强制管理，适配器层自动过滤违规快照 |
| 失败经验变成约束 | `prediction_source` 追踪来源，失败叙事进入 FailureConstraint |
| 上游极强探索，中游严格收缩 | MiroFish 增强 Stage 1/2 探索深度，Stage 3 prefilter 逻辑不变 |

集成路径与 `05_spec-execution-audit.md` 推荐执行顺序一致：MiroFish 协议层排在控制平面扩展和数据源扩展之后，属于"最后推进"项目（第 7 优先级）。**Step 1 成本极低，可以随控制平面工作一起完成；Step 2 必须等实验数据到位。**
