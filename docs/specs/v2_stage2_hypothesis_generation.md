# Pixiu v2 Stage 2：并行假设生成层规格

> 版本：2.0
> 创建：2026-03-07
> 前置依赖：`v2_interface_contracts.md`、`v2_stage1_market_context.md`
> 文件位置：`src/agents/alpha_researcher.py`（重写）、`src/agents/synthesis_agent.py`（新建）

---

## 1. AlphaResearcher（重写）

### 与 v1 的关键差异

| 对比项 | v1 Researcher | v2 AlphaResearcher |
|---|---|---|
| 并发 | 单个，串行 | 每个 Island 一个，asyncio 并行 |
| 输出 | 松散 `FactorHypothesis` dict | 强类型 `FactorResearchNote` |
| 探索性 | 无 | 支持 `exploration_questions` |
| 上下文 | Skills 文件注入 | `MarketContextMemo` + Skills 注入 |
| 失败反馈 | 写入 error_message | 包含 `Critic` 的 `suggested_fix` |

### System Prompt

```python
ALPHA_RESEARCHER_SYSTEM_PROMPT = """你是 EvoQuant 的 Alpha 研究员，专注于 {island} 方向的量化因子研究。

你的任务：基于市场上下文和历史经验，提出一个有经济逻辑支撑的新 Alpha 因子假设。

{skills_content}

输出规则：
1. 必须输出合法 JSON，符合 FactorResearchNote schema
2. proposed_formula 必须是合法的 Qlib 表达式
3. 如果你需要在提公式之前验证某个数据模式，在 exploration_questions 中提出（最多 2 个问题）
4. 如果你已经有充分把握，直接给出 final_formula，exploration_questions 设为空列表
5. hypothesis 必须包含清晰的经济直觉（50-200字），不是对公式的描述

禁止：
- 使用 Ref($close, -N) 等未来数据
- 使用未注册的字段名（见下方字段约束）
- 输出 JSON 以外的任何内容

可用字段（当前阶段）：
  基础价量字段（始终可用）：$close, $open, $high, $low, $volume, $factor
  扩展基本面字段（仅在 FUNDAMENTAL_FIELDS_ENABLED=true 时可用）：
    $pe_ttm, $pb, $roe, $revenue_yoy, $profit_yoy, $turnover_rate, $float_mv

输出格式：返回一个 JSON 对象，包含字段：
  - notes: 一个包含 2-3 个 FactorResearchNote 的数组
  - generation_rationale: 字符串，说明为何选择这几个研究方向

每个 Note 的经济逻辑必须彼此差异化，禁止提交同一个公式的微小变体。
"""

ALPHA_RESEARCHER_USER_TEMPLATE = """
今日市场上下文：
{market_context_summary}

{island} 的历史经验：
- 历史最优公式：{best_formula}（Sharpe={best_sharpe}）
- 常见失败模式：{failure_modes}
- 建议方向：{suggested_directions}

{feedback_section}

请提出 2-3 个差异化的 FactorResearchNote，输出 AlphaResearcherBatch JSON。
每个假设应捕捉 {island} 方向下不同的市场机制，而非同一思路的变体。
"""
```

### 实现

```python
# src/agents/alpha_researcher.py

class AlphaResearcher:
    def __init__(self, island: str, skill_loader: SkillLoader):
        self.island = island
        self.skill_loader = skill_loader
        self.llm = ChatOpenAI(
            model=os.getenv("RESEARCHER_MODEL", "deepseek-chat"),
            base_url=os.getenv("RESEARCHER_BASE_URL"),
            api_key=os.getenv("RESEARCHER_API_KEY"),
            temperature=0.7,  # 适度创造性
        )

    async def generate(
        self,
        context: MarketContextMemo,
        iteration: int,
        last_verdict: CriticVerdict | None = None,
    ) -> AlphaResearcherBatch:
        # 动态 Skills 注入（从 v1 保留此机制）
        skills = self.skill_loader.get_skills(
            iteration=iteration,
            has_feedback=(last_verdict is not None),
        )

        system_prompt = ALPHA_RESEARCHER_SYSTEM_PROMPT.format(
            island=self.island,
            skills_content=skills,
        )

        # 找到当前 Island 的历史 insight
        island_insight = next(
            (i for i in context.historical_insights if i.island == self.island),
            None,
        )

        feedback_section = ""
        if last_verdict and not last_verdict.overall_passed:
            feedback_section = f"""
上轮失败反馈：
- 失败原因：{last_verdict.failure_explanation}
- 改进建议：{last_verdict.suggested_fix}
请在新假设中针对这个问题做出调整。
"""

        user_message = ALPHA_RESEARCHER_USER_TEMPLATE.format(
            market_context_summary=context.raw_summary,
            island=self.island,
            best_formula=island_insight.best_factor_formula if island_insight else "无",
            best_sharpe=island_insight.best_sharpe if island_insight else 0.0,
            failure_modes=", ".join(island_insight.common_failure_modes) if island_insight else "无",
            suggested_directions="\n".join(f"  - {d}" for d in (island_insight.suggested_directions if island_insight else [])),
            feedback_section=feedback_section,
        )

        response = await self.llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ])

        return self._parse_batch(response.content, iteration)

    def _parse_batch(self, content: str, iteration: int) -> AlphaResearcherBatch:
        import json, re, uuid
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match:
            raise ValueError(f"AlphaResearcher 输出不含 JSON：{content[:200]}")

        data = json.loads(match.group())
        notes_data = data.get("notes", [data])  # 兼容降级：若 LLM 只输出单个 note

        notes = []
        for i, note_data in enumerate(notes_data):
            note_data.setdefault("note_id", f"{self.island}_{today_str()}_{uuid.uuid4().hex[:8]}")
            note_data.setdefault("island", self.island)
            note_data.setdefault("iteration", iteration)
            note_data.setdefault("exploration_questions", [])
            note_data.setdefault("risk_factors", [])
            note_data.setdefault("market_context_date", today_str())
            notes.append(FactorResearchNote(**note_data))

        return AlphaResearcherBatch(
            island=self.island,
            notes=notes,
            generation_rationale=data.get("generation_rationale", ""),
        )
```

---

## 2. SynthesisAgent（新增）

### 职责

扫描本轮所有 Island 生成的 `FactorResearchNote`，检测跨 Island 的潜在关联性，避免重复探索，并偶尔提出组合假设。

**触发条件**：只在活跃 Island ≥ 2 时运行。若只有 1 个 Island，跳过此步骤。

```python
# src/agents/synthesis_agent.py

SYNTHESIS_PROMPT = """你是 EvoQuant 的合成分析师。
你收到了来自不同研究方向的多份因子假设，请检测是否存在跨方向的关联。

关注点：
1. 两个假设是否在捕捉相同的市场现象（方向可能不同）？
2. 是否有一个假设可以作为另一个的"改进版"？
3. 是否有值得探索的组合因子（两个因子相乘 / 条件叠加）？

如果没有特别的关联，输出空列表 []。
不要强行找关联——只输出真正有价值的发现。

输出格式：JSON 数组，每个元素为 SynthesisInsight schema。
"""

class SynthesisAgent:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=os.getenv("RESEARCHER_MODEL", "deepseek-chat"),
            base_url=os.getenv("RESEARCHER_BASE_URL"),
            api_key=os.getenv("RESEARCHER_API_KEY"),
            temperature=0.2,
        )

    async def synthesize(
        self,
        notes: list[FactorResearchNote],
    ) -> list[SynthesisInsight]:
        if len(notes) < 2:
            return []

        notes_summary = "\n".join([
            f"[{n.island}] {n.note_id}: {n.hypothesis[:100]} | 公式：{n.proposed_formula}"
            for n in notes
        ])

        response = await self.llm.ainvoke([
            SystemMessage(content=SYNTHESIS_PROMPT),
            HumanMessage(content=f"当前各方向假设：\n{notes_summary}"),
        ])

        return self._parse_insights(response.content, notes)

    def _parse_insights(self, content: str, notes: list) -> list[SynthesisInsight]:
        import json, re
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if not match:
            return []
        try:
            raw = json.loads(match.group())
            return [SynthesisInsight(**item) for item in raw]
        except Exception:
            return []
```

---

## 3. 并行执行模式

`hypothesis_gen_node` 使用 `asyncio.gather` 真正并行：

```python
async def hypothesis_gen_node(state: AgentState) -> AgentState:
    active_islands = scheduler.get_active_islands()

    # 并行生成：所有 Island 同时开始
    tasks = [
        AlphaResearcher(island=island, skill_loader=skill_loader).generate(
            context=state.market_context,
            iteration=state.iteration,
            last_verdict=_get_last_verdict(state, island),
        )
        for island in active_islands
    ]

    batches: list[AlphaResearcherBatch | Exception] = await asyncio.gather(
        *tasks, return_exceptions=True
    )

    # 展开：每个 Island 的 batch 包含 2-3 个 notes，汇总为一个大列表
    all_notes: list[FactorResearchNote] = []
    for batch in batches:
        if isinstance(batch, Exception):
            logger.warning(f"AlphaResearcher 失败（跳过）: {batch}")
        else:
            all_notes.extend(batch.notes)

    # 4 个 Island × 2-3 个/batch = 8-12 个候选进入 Stage 3 过滤
    logger.info(f"Stage 2 生成 {len(all_notes)} 个候选（来自 {len(batches)} 个 Island）")
    return {**state.dict(), "research_notes": all_notes}
```

---

## 4. Island 研究范围与字段约束

### 当前阶段（基础价量字段）

6 个 Island 的研究范围如下，均使用价量代理实现：

| Island | 核心机制 | 代理公式方向 |
|--------|---------|------------|
| momentum | 价格趋势延续/反转 | N日收益率、Ma 交叉、新高突破 |
| volatility | 波动率异常与均值回归 | 历史波动率分位、ATR、波动率偏度 |
| volume | 量价背离与资金异常 | 量价相关性、成交额异常、放量信号 |
| northbound | 外资行为的价格印记 | 高 AH 溢价股票的量价特征、外资重仓段位行为 |
| valuation | 价格相对历史的均值回归 | 52周新高距离、价格历史分位、成交量加权价格偏离 |
| sentiment | 市场关注度与情绪的价量代理 | 异常换手率、成交额/流动市值比、连涨天数 |

**注意**：`northbound` 和 `valuation` 在此阶段使用价量代理，研究深度受限。接入 Tushare 基本面字段后（见 `v2_data_sources.md` 任务B），这两个 Island 可升级为真正的基本面因子。

### 扩展阶段（Tushare 接入后）

通过环境变量控制：

```python
FUNDAMENTAL_FIELDS_ENABLED = os.getenv("FUNDAMENTAL_FIELDS_ENABLED", "false").lower() == "true"
```

`true` 时，AlphaResearcher System Prompt 中追加扩展字段列表，`valuation` 和 `sentiment` Island 的研究范围解锁。

---

## 5. 测试要求

更新 `tests/test_structured_output.py`，新增：

```python
def test_alpha_researcher_returns_batch():
    """AlphaResearcher 输出必须是 AlphaResearcherBatch，包含 2-3 个 notes"""

def test_alpha_researcher_batch_diversity():
    """同一 batch 的 notes，proposed_formula 不应完全相同"""

def test_alpha_researcher_with_feedback():
    """有 CriticVerdict 反馈时，输出不应重复上次的 proposed_formula"""

def test_alpha_researcher_parallel():
    """4 个 Island 并行生成，总耗时应 < 单个 × 2（真正并行）"""

def test_hypothesis_gen_node_note_count():
    """hypothesis_gen_node 的 research_notes 数量应 ≥ active_islands × 2"""

def test_synthesis_agent_no_forced_insights():
    """假设差异大时，SynthesisAgent 应返回空列表而非强行关联"""
```
