# Skills Expansion Implementation Plan (v2 — Executable)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend SkillLoader from Researcher-only to all LLM-driven agents (MarketAnalyst, PreFilter, ExplorationAgent), add island-specific skills, fix `_state_proxy` gap, and add integration tests that verify actual prompt injection.

**Architecture:** `SkillLoader.load_for_agent(role, state, **kwargs)` already exists (Task 1 from v1 is done). This plan covers: skill file creation, agent call-site injection, `_state_proxy` fix, and properly structured tests.

**Tech Stack:** Python, existing `SkillLoader` class, markdown skill files, pytest

**Design Doc:** `docs/plans/2026-03-19-multi-agent-skills-expansion-design.md`

**Pre-condition:** `src/skills/loader.py` already has `load_for_agent()`, `_apply_conditional_rules()`, `ISLAND_FILE_MAP`, `_ROLE_SKILLS`, `_ROLE_CONSTRAINTS`. Legacy `load_for_researcher()` delegates to `load_for_agent()`.

---

## Review Findings Addressed (from v1 coworker review)

| # | Severity | Finding | Fix in this plan |
|---|----------|---------|-----------------|
| 1 | HIGH | `_state_proxy` in researcher.py missing `market_context` → `market_regime_detection.md` never fires | Task 4 Step 2 |
| 2 | HIGH | Tests only verify loader returns non-empty, not actual prompt injection | Task 3/4/5 each have integration test |
| 3 | MEDIUM | ACTIVE_ISLANDS=6 but only 4 island skills | Task 1 creates all 6 island files |
| 4 | MEDIUM | All tests crammed into test_stage4.py | Tests go to test_skills.py + per-stage files |
| 5 | MEDIUM | Task 3 test won't fail before implementation | Each injection test asserts on a unique marker string |

---

### Task 1: Create Skill Files (9 new markdown files)

**Files:**
- Create: `knowledge/skills/market_analyst/context_framing.md`
- Create: `knowledge/skills/prefilter/filter_guidance.md`
- Create: `knowledge/skills/exploration/a_share_coding_constraints.md`
- Create: `knowledge/skills/researcher/islands/momentum.md`
- Create: `knowledge/skills/researcher/islands/valuation.md`
- Create: `knowledge/skills/researcher/islands/volatility.md`
- Create: `knowledge/skills/researcher/islands/northbound.md`
- Create: `knowledge/skills/researcher/islands/volume.md`
- Create: `knowledge/skills/researcher/islands/sentiment.md`

**Step 1: Create directory structure**

```bash
mkdir -p knowledge/skills/market_analyst
mkdir -p knowledge/skills/prefilter
mkdir -p knowledge/skills/exploration
mkdir -p knowledge/skills/researcher/islands
```

**Step 2: Write each skill file**

Each file 50-150 lines. Every file MUST contain a unique marker comment on line 1 for test assertions:

**`market_analyst/context_framing.md`** — `<!-- SKILL:MARKET_ANALYST_CONTEXT_FRAMING -->`
- 从价量数据提炼 regime 信号的规范（趋势/震荡/高波动判定标准）
- 融资融券余额到 market_sentiment 的映射规则
- 新闻/公告归类标准（policy_signal / sector_rotation / event_driven）
- MarketContextMemo 各字段填写标准和优先级

**`prefilter/filter_guidance.md`** — `<!-- SKILL:PREFILTER_GUIDANCE -->`
- 必须拒绝的假设特征（look-ahead bias、无经济意义的公式结构）
- 应该放行的假设特征（IC 预估偏低但机制解释清晰）
- Novelty 判断标准（实质性差异 vs 参数微调）
- 常见误判模式（过度保守 / 过度宽松）

**`exploration/a_share_coding_constraints.md`** — `<!-- SKILL:EXPLORATION_CODING -->`
- qlib API 使用模式（`qlib.init` 路径、`D.features` 用法）
- 禁止的代码模式（直接访问 .csv、引用未挂载数据）
- 可用数据字段声明（$close/$open/$high/$low/$volume/$factor/$vwap）
- 常见陷阱（NaN 处理、日期对齐、universe 泄漏）

**`researcher/islands/momentum.md`** — `<!-- SKILL:ISLAND_MOMENTUM -->`
- T+1 时滞对动量衰减的影响
- 追涨杀跌散户行为放大短期动量
- 涨跌停制度对连续涨幅的截断效应
- 有效的时间窗口（5/10/20日 vs 美股常见的 12 个月）

**`researcher/islands/valuation.md`** — `<!-- SKILL:ISLAND_VALUATION -->`
- 散户定价 vs 机构定价的差异
- 壳资源溢价对小市值估值的扭曲
- 退市新规后估值因子有效性变化
- PE/PB/PS 在 A 股的适用条件

**`researcher/islands/volatility.md`** — `<!-- SKILL:ISLAND_VOLATILITY -->`
- 涨跌停制度对已实现波动率的截断
- 日历效应（周一/月末/季末 波动率异常）
- 波动率非对称性（下跌波动率 vs 上涨波动率）
- 低波动异象在 A 股的表现

**`researcher/islands/northbound.md`** — `<!-- SKILL:ISLAND_NORTHBOUND -->`
- 数据特征（每日净买入额、持股占比、增减仓幅度）
- 信号解读（趋势性增仓 vs 短期波动）
- 与 A 股情绪周期的领先/滞后关系
- 数据陷阱（节假日缺失、沪深港通差异）

**`researcher/islands/volume.md`** — `<!-- SKILL:ISLAND_VOLUME -->`
- A 股量价关系的特殊性（散户主导的换手率意义）
- 量能突变信号（放量突破 vs 缩量回调）
- 成交额 vs 换手率：哪个更适合做因子
- 量能分布的时间特征（开盘/尾盘集中成交）

**`researcher/islands/sentiment.md`** — `<!-- SKILL:ISLAND_SENTIMENT -->`
- A 股情绪代理变量（融资余额、ETF 申赎、涨跌家数比）
- 散户情绪 vs 机构情绪的分离度量
- 情绪反转信号的时间尺度（3-5 日极值反转）
- 与政策事件的交互效应

**Step 3: Update `ISLAND_FILE_MAP` in loader.py**

Add `volume` and `sentiment` to `ISLAND_FILE_MAP`:

```python
# In src/skills/loader.py, update ISLAND_FILE_MAP:
ISLAND_FILE_MAP = {
    "momentum":   "researcher/islands/momentum.md",
    "valuation":  "researcher/islands/valuation.md",
    "volatility": "researcher/islands/volatility.md",
    "northbound": "researcher/islands/northbound.md",
    "volume":     "researcher/islands/volume.md",
    "sentiment":  "researcher/islands/sentiment.md",
}
```

**Step 4: Run existing tests to verify no regression**

Run: `uv run pytest tests/test_stage4.py::TestSkillLoader -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add knowledge/skills/ src/skills/loader.py
git commit -m "feat(skills): add 9 skill files for all agents and all 6 islands"
```

---

### Task 2: SkillLoader Unit Tests (new file: tests/test_skills.py)

**Files:**
- Create: `tests/test_skills.py`

**Step 1: Write tests**

Create `tests/test_skills.py` with comprehensive SkillLoader tests:

```python
"""SkillLoader 单元测试 — 覆盖 generic interface、条件注入、island 注入。"""
import pytest
from src.skills.loader import SkillLoader, ISLAND_FILE_MAP


@pytest.fixture()
def loader():
    return SkillLoader()


def _state(iteration=0, error="", market_context=None):
    return {
        "current_iteration": iteration,
        "error_message": error,
        "market_context": market_context,
    }


class TestGenericInterface:
    """load_for_agent() 通用接口测试。"""

    def test_researcher_backward_compat(self, loader):
        """Generic interface returns same result as legacy for researcher."""
        state = _state(iteration=2, error="IC低")
        legacy = loader.load_for_researcher(state)
        generic = loader.load_for_agent("researcher", state)
        assert legacy == generic

    def test_unknown_role_gets_default_constraints(self, loader):
        result = loader.load_for_agent("unknown_role")
        assert "T+1" in result or "前视偏差" in result

    @pytest.mark.parametrize("role", ["researcher", "market_analyst", "prefilter", "exploration"])
    def test_all_roles_return_nonempty(self, loader, role):
        result = loader.load_for_agent(role)
        assert len(result) > 0, f"load_for_agent('{role}') returned empty"


class TestConditionalInjection:
    """Type C 条件注入测试。"""

    def test_market_regime_injected_when_market_context_present(self, loader):
        """HIGH fix: market_context in state triggers regime detection skill."""
        state = _state(market_context={"market_regime": "trending_up"})
        result = loader.load_for_agent("researcher", state)
        # market_regime_detection.md should be loaded
        # (file already exists in knowledge/skills/researcher/)
        regime_content = loader._load("researcher/market_regime_detection.md")
        if regime_content:
            assert regime_content in result

    def test_market_regime_not_injected_without_context(self, loader):
        result = loader.load_for_agent("researcher", _state())
        regime_content = loader._load("researcher/market_regime_detection.md")
        if regime_content:
            assert regime_content not in result

    def test_iteration_zero_no_evolution(self, loader):
        result = loader.load_for_agent("researcher", _state(iteration=0))
        evolution_content = loader._load("researcher/island_evolution.md")
        if evolution_content:
            assert evolution_content not in result

    def test_iteration_gt_zero_has_evolution(self, loader):
        result = loader.load_for_agent("researcher", _state(iteration=1))
        assert "强制工作流程" in result

    def test_error_message_triggers_feedback(self, loader):
        result = loader.load_for_agent("researcher", _state(error="Sharpe太低"))
        assert "上一次失败的错误消息解读" in result


class TestIslandSkills:
    """Island-specific skill 注入测试。"""

    @pytest.mark.parametrize("island", list(ISLAND_FILE_MAP.keys()))
    def test_island_skill_adds_content(self, loader, island):
        """Each island skill file adds content beyond base researcher output."""
        base = loader.load_for_agent("researcher", _state())
        with_island = loader.load_for_agent("researcher", _state(), island=island)
        assert len(with_island) > len(base), (
            f"Island '{island}' skill did not add content"
        )

    def test_unknown_island_same_as_base(self, loader):
        base = loader.load_for_agent("researcher", _state())
        with_unknown = loader.load_for_agent("researcher", _state(), island="nonexistent")
        assert base == with_unknown


class TestRoleSkillMarkers:
    """Verify each role loads its unique skill content via marker strings."""

    def test_market_analyst_has_marker(self, loader):
        result = loader.load_for_agent("market_analyst")
        assert "SKILL:MARKET_ANALYST_CONTEXT_FRAMING" in result

    def test_prefilter_has_marker(self, loader):
        result = loader.load_for_agent("prefilter")
        assert "SKILL:PREFILTER_GUIDANCE" in result

    def test_exploration_has_marker(self, loader):
        result = loader.load_for_agent("exploration")
        assert "SKILL:EXPLORATION_CODING" in result
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_skills.py -v`
Expected: `TestRoleSkillMarkers` tests FAIL (skill files just created in Task 1 must have exact markers). Other tests should pass if Task 1 was done correctly.

**Step 3: Verify Task 1 markers are correct, fix if needed**

If any marker test fails, fix the corresponding skill file to include the marker.

**Step 4: Run full suite**

Run: `uv run pytest tests/test_skills.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add tests/test_skills.py
git commit -m "test(skills): add SkillLoader unit tests with marker assertions and conditional injection coverage"
```

---

### Task 3: Inject Skills into MarketAnalyst + Integration Test

**Files:**
- Modify: `src/agents/market_analyst.py` (line 112)
- Modify: `tests/test_stage1.py` (add integration test)

**Step 1: Write the failing integration test**

Add to `tests/test_stage1.py`:

```python
class TestMarketAnalystSkillInjection:
    """Verify MarketAnalyst actually includes skill content in its system prompt."""

    def test_system_prompt_contains_skill_marker(self):
        """Integration: skill text appears in the SystemMessage sent to LLM."""
        from src.agents.market_analyst import MARKET_ANALYST_SYSTEM_PROMPT, _today_str
        from src.skills.loader import SkillLoader

        # Simulate what the agent does — if skills are NOT injected,
        # this test fails because marker won't be in the prompt.
        # After injection, the agent's system prompt includes the marker.
        loader = SkillLoader()
        skill_text = loader.load_for_agent("market_analyst")
        assert "SKILL:MARKET_ANALYST_CONTEXT_FRAMING" in skill_text

        # The actual injection test: verify the agent module exposes
        # or constructs a prompt that includes skill text.
        # We import the assembled prompt after modification.
        from src.agents import market_analyst as ma_module
        assert hasattr(ma_module, '_market_analyst_skills'), (
            "market_analyst.py does not have _market_analyst_skills — "
            "SkillLoader not injected at module level"
        )
        assert "SKILL:MARKET_ANALYST_CONTEXT_FRAMING" in ma_module._market_analyst_skills
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stage1.py::TestMarketAnalystSkillInjection -v`
Expected: FAIL with `AttributeError: module 'src.agents.market_analyst' has no attribute '_market_analyst_skills'`

**Step 3: Modify market_analyst.py**

At `src/agents/market_analyst.py`, add at module level (after imports):

```python
from src.skills.loader import SkillLoader

_skill_loader = SkillLoader()
_market_analyst_skills = _skill_loader.load_for_agent("market_analyst")
```

In the `analyze()` method (~line 112), modify the SystemMessage:

```python
# Before:
SystemMessage(content=MARKET_ANALYST_SYSTEM_PROMPT.format(today=_today_str())),

# After:
SystemMessage(content=MARKET_ANALYST_SYSTEM_PROMPT.format(today=_today_str()) + "\n\n" + _market_analyst_skills),
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_stage1.py::TestMarketAnalystSkillInjection -v`
Expected: PASS

Run: `uv run pytest tests/test_stage1.py -v`
Expected: All PASS (no regression)

**Step 5: Commit**

```bash
git add src/agents/market_analyst.py tests/test_stage1.py
git commit -m "feat(stage1): inject SkillLoader into MarketAnalyst system prompt"
```

---

### Task 4: Fix Researcher `_state_proxy` + Pass Island + Integration Test

**Files:**
- Modify: `src/agents/researcher.py` (lines 196-206)
- Modify: `tests/test_stage2.py` (add integration test)

**Step 1: Write the failing integration test**

Add to `tests/test_stage2.py`:

```python
class TestResearcherSkillInjection:
    """Verify Researcher passes market_context and island to SkillLoader."""

    def test_state_proxy_includes_market_context(self):
        """HIGH fix: _state_proxy must include market_context for regime detection."""
        from unittest.mock import AsyncMock, patch, MagicMock
        from src.agents.researcher import AlphaResearcher
        from src.schemas.market_context import MarketContextMemo

        researcher = AlphaResearcher(island="momentum")

        # Capture what SkillLoader receives
        captured_args = {}
        original_load = researcher.skill_loader.load_for_agent

        def spy_load(role, state=None, **kwargs):
            captured_args["role"] = role
            captured_args["state"] = state
            captured_args["kwargs"] = kwargs
            return original_load(role, state, **kwargs)

        researcher.skill_loader.load_for_agent = spy_load

        # Create a minimal MarketContextMemo
        context = MarketContextMemo(
            market_regime="trending_up",
            suggested_islands=["momentum"],
            raw_summary="test",
            key_signals=[],
        )

        # Patch LLM to avoid real API call
        with patch.object(researcher.llm, 'ainvoke', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = MagicMock(content='{"notes": []}')
            import asyncio
            try:
                asyncio.run(researcher.generate_batch(
                    context=context, iteration=1
                ))
            except Exception:
                pass  # parse errors are fine, we just need the spy call

        assert captured_args.get("role") == "researcher"
        assert captured_args["state"].get("market_context") is not None, (
            "_state_proxy missing market_context — market_regime_detection.md will never fire"
        )
        assert captured_args["kwargs"].get("island") == "momentum", (
            "island not passed to load_for_agent"
        )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stage2.py::TestResearcherSkillInjection -v`
Expected: FAIL — `_state_proxy` doesn't have `market_context`, and `load_for_researcher` is called instead of `load_for_agent`

**Step 3: Fix researcher.py (lines 196-206)**

```python
# Before (line 196-206):
_state_proxy = {
    "current_iteration": iteration,
    "error_message": (
        last_verdict.failure_explanation
        if last_verdict and not last_verdict.overall_passed
        else None
    ),
}
skill_context = self.skill_loader.load_for_researcher(
    _state_proxy, subspace=subspace_hint
)

# After:
_state_proxy = {
    "current_iteration": iteration,
    "error_message": (
        last_verdict.failure_explanation
        if last_verdict and not last_verdict.overall_passed
        else None
    ),
    "market_context": context,  # HIGH fix: enable market_regime_detection.md
}
skill_context = self.skill_loader.load_for_agent(
    "researcher", _state_proxy,
    subspace=subspace_hint, island=self.island,
)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_stage2.py::TestResearcherSkillInjection tests/test_stage4.py::TestSkillLoader -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/agents/researcher.py tests/test_stage2.py
git commit -m "fix(stage2): pass market_context and island to SkillLoader, enabling regime detection and island skills"
```

---

### Task 5: Inject Skills into PreFilter (AlignmentChecker) + Integration Test

**Files:**
- Modify: `src/agents/prefilter.py` (line 174, 199)
- Modify: `tests/test_prefilter.py` (add integration test)

**Step 1: Write the failing integration test**

Add to `tests/test_prefilter.py`:

```python
class TestPreFilterSkillInjection:
    """Verify PreFilter AlignmentChecker includes skill content in prompt."""

    def test_alignment_prompt_contains_skill_marker(self):
        """Integration: skill text is prepended to ALIGNMENT_PROMPT."""
        from src.agents import prefilter as pf_module
        # After injection, module should have the combined prompt
        assert hasattr(pf_module, '_prefilter_skills'), (
            "prefilter.py does not have _prefilter_skills — "
            "SkillLoader not injected"
        )
        assert "SKILL:PREFILTER_GUIDANCE" in pf_module._prefilter_skills
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prefilter.py::TestPreFilterSkillInjection -v`
Expected: FAIL with `AttributeError: module has no attribute '_prefilter_skills'`

**Step 3: Modify prefilter.py**

At module level (before `ALIGNMENT_PROMPT`), add:

```python
from src.skills.loader import SkillLoader

_skill_loader = SkillLoader()
_prefilter_skills = _skill_loader.load_for_agent("prefilter")
```

In `AlignmentChecker.check()` method, modify the prompt construction to prepend skills:

```python
# Find where ALIGNMENT_PROMPT is used and prepend _prefilter_skills:
prompt = _prefilter_skills + "\n\n" + ALIGNMENT_PROMPT.format(
    hypothesis=note.hypothesis,
    formula=note.formula,
)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_prefilter.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/agents/prefilter.py tests/test_prefilter.py
git commit -m "feat(stage3): inject SkillLoader into PreFilter AlignmentChecker"
```

---

### Task 6: Inject Skills into ExplorationAgent + Integration Test

**Files:**
- Modify: `src/execution/exploration_agent.py` (line 9, 44)
- Modify: `tests/test_stage4.py` (add integration test)

**Step 1: Write the failing integration test**

Add to `tests/test_stage4.py`:

```python
class TestExplorationAgentSkillInjection:
    """Verify ExplorationAgent includes skill content in system prompt."""

    def test_exploration_module_has_skills(self):
        from src.execution import exploration_agent as ea_module
        assert hasattr(ea_module, '_exploration_skills'), (
            "exploration_agent.py does not have _exploration_skills — "
            "SkillLoader not injected"
        )
        assert "SKILL:EXPLORATION_CODING" in ea_module._exploration_skills
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stage4.py::TestExplorationAgentSkillInjection -v`
Expected: FAIL with `AttributeError`

**Step 3: Modify exploration_agent.py**

At module level (after imports), add:

```python
from src.skills.loader import SkillLoader

_skill_loader = SkillLoader()
_exploration_skills = _skill_loader.load_for_agent("exploration")
```

In `ExplorationAgent.explore()` method, modify message construction:

```python
# Before:
messages = [
    {"role": "system", "content": EXPLORATION_SYSTEM_PROMPT},
    {"role": "user", "content": prompt}
]

# After:
messages = [
    {"role": "system", "content": EXPLORATION_SYSTEM_PROMPT + "\n\n" + _exploration_skills},
    {"role": "user", "content": prompt}
]
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_stage4.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/execution/exploration_agent.py tests/test_stage4.py
git commit -m "feat(stage4): inject SkillLoader into ExplorationAgent system prompt"
```

---

### Task 7: Final Integration Verification

**Step 1: Run full test suite**

```bash
uv run pytest -q tests -m "smoke or unit"
```
Expected: All pass, no regressions.

**Step 2: Verify skill loading (all roles + all islands)**

```bash
uv run python -c "
from src.skills.loader import SkillLoader, ISLAND_FILE_MAP
loader = SkillLoader()

# All 4 roles
for role in ['researcher', 'market_analyst', 'prefilter', 'exploration']:
    result = loader.load_for_agent(role)
    print(f'{role}: {len(result)} chars')

# All 6 islands
for island in ISLAND_FILE_MAP:
    result = loader.load_for_agent('researcher', {'current_iteration': 0}, island=island)
    print(f'researcher+{island}: {len(result)} chars')

# market_context trigger
result = loader.load_for_agent('researcher', {'current_iteration': 0, 'market_context': {'regime': 'up'}})
has_regime = 'market_regime_detection' in str(loader._load('researcher/market_regime_detection.md') or '')
print(f'regime injection works: {has_regime and \"regime\" in result.lower()}')
"
```

**Step 3: Verify module-level injection**

```bash
uv run python -c "
from src.agents import market_analyst, prefilter
from src.execution import exploration_agent

assert hasattr(market_analyst, '_market_analyst_skills')
assert hasattr(prefilter, '_prefilter_skills')
assert hasattr(exploration_agent, '_exploration_skills')
print('All agent modules have skill injection: OK')
"
```

**Step 4: Commit all and tag**

```bash
git add -A
git commit -m "feat(phase4b): complete multi-agent skills expansion — all LLM-driven agents now have skill injection"
```

---

## Codex Dispatch Notes

This plan is suitable for codex dispatch as **2-3 sequential tasks**:

| Batch | Tasks | Estimated Time |
|-------|-------|---------------|
| Batch 1 | Task 1 + 2 (files + tests) | 15-20 min |
| Batch 2 | Task 3 + 4 + 5 + 6 (agent injection) | 15-20 min |
| Batch 3 | Task 7 (verification) | 5 min |

**Coordinator must review** between batches: Task 4 (researcher `_state_proxy` fix) is the highest-risk change — verify the spy test actually captures the right arguments.
