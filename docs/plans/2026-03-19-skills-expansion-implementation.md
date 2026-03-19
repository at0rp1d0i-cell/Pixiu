# Skills Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend SkillLoader from Researcher-only to all LLM-driven agents (MarketAnalyst, PreFilter, ExplorationAgent), add island-specific skills, and refactor to generic interface.

**Architecture:** Refactor `SkillLoader` to a single `load_for_agent(agent_role, state, **kwargs)` entry point with a declarative conditional-injection registry. Each LLM-driven agent calls this with its role name. New skill markdown files provide domain knowledge for each agent.

**Tech Stack:** Python, existing `SkillLoader` class, markdown skill files, pytest

**Design Doc:** `docs/plans/2026-03-19-multi-agent-skills-expansion-design.md`

---

### Task 1: Refactor SkillLoader to Generic Interface

**Files:**
- Modify: `src/skills/loader.py`
- Test: `tests/test_stage4.py` (existing `TestSkillLoader` class)

**Step 1: Write the failing test**

Add to `tests/test_stage4.py` after existing `TestSkillLoader`:

```python
class TestSkillLoaderGenericInterface:
    def test_load_for_agent_researcher_matches_legacy(self, loader):
        """New generic interface returns same result as legacy method."""
        state = _state(iteration=2, error="IC低")
        legacy = loader.load_for_researcher(state)
        generic = loader.load_for_agent("researcher", state)
        assert legacy == generic

    def test_load_for_agent_unknown_role_returns_constraints_only(self, loader):
        result = loader.load_for_agent("unknown_role")
        # Should still get Type A constraints (shared)
        assert "T+1" in result or "前视偏差" in result

    def test_load_for_agent_researcher_with_island(self, loader):
        result = loader.load_for_agent("researcher", _state(iteration=0), island="momentum")
        # Should include base researcher content
        assert "Ref(expr, N)" in result or "合法算子" in result
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stage4.py::TestSkillLoaderGenericInterface -v`
Expected: FAIL with "has no attribute 'load_for_agent'"

**Step 3: Implement `load_for_agent()` in loader.py**

Replace the contents of `src/skills/loader.py` with:

```python
"""
Pixiu: SkillLoader — 统一管理 Skill 文档的加载与条件注入
"""
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_SKILLS_BASE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "knowledge", "skills")
)

# Island → skill file mapping (only active islands)
ISLAND_FILE_MAP = {
    "momentum":   "researcher/islands/momentum.md",
    "valuation":  "researcher/islands/valuation.md",
    "volatility": "researcher/islands/volatility.md",
    "northbound": "researcher/islands/northbound.md",
}

# Per-role Type B skills (always injected for that role)
_ROLE_SKILLS: dict[str, list[str]] = {
    "researcher": ["researcher/alpha_generation.md"],
    "market_analyst": ["market_analyst/context_framing.md"],
    "prefilter": ["prefilter/filter_guidance.md"],
    "exploration": ["exploration/a_share_coding_constraints.md"],
}

# Per-role Type A constraints (subset of shared constraints relevant to each role)
_ROLE_CONSTRAINTS: dict[str, list[str]] = {
    "researcher":     ["constraints/a_share_constraints.md", "constraints/qlib_formula_syntax.md"],
    "market_analyst": ["constraints/a_share_constraints.md"],
    "prefilter":      ["constraints/a_share_constraints.md", "constraints/qlib_formula_syntax.md"],
    "exploration":    ["constraints/qlib_formula_syntax.md"],
}

# Default constraints for unknown roles
_DEFAULT_CONSTRAINTS = ["constraints/a_share_constraints.md"]


class SkillLoader:
    """按 Agent 角色和 AgentState 动态加载 Skill 文档。

    三类 Skill：
      Type A (Rules)  — 永久注入，硬约束
      Type B (Process)— 永久注入，流程规范
      Type C (Context)— 按 AgentState 条件注入
    """

    def load_for_agent(
        self,
        agent_role: str,
        state: Any = None,
        **kwargs,
    ) -> str:
        """通用 skill 加载入口。

        Args:
            agent_role: "researcher" | "market_analyst" | "prefilter" | "exploration"
            state: AgentState dict, used for conditional injection
            **kwargs: role-specific params (e.g. subspace=, island=)
        """
        parts = []

        # ── Type A: 硬约束 ──
        for path in _ROLE_CONSTRAINTS.get(agent_role, _DEFAULT_CONSTRAINTS):
            parts.append(self._load(path, required=True))

        # ── Type B: 角色固定 skill ──
        for path in _ROLE_SKILLS.get(agent_role, []):
            parts.append(self._load(path))

        # ── Type C: 条件注入 ──
        self._apply_conditional_rules(agent_role, state, kwargs, parts)

        valid_parts = [p for p in parts if p]
        logger.debug(
            "[SkillLoader] %s 加载了 %d 个 Skill 文档 (kwargs=%s)",
            agent_role, len(valid_parts), list(kwargs.keys()),
        )
        return "\n\n---\n\n".join(valid_parts)

    def _apply_conditional_rules(
        self, role: str, state: Any, kwargs: dict, parts: list
    ) -> None:
        """Apply Type C conditional injection rules."""
        if state is None:
            state = {}

        if role == "researcher":
            # Iteration > 0: inject island evolution
            if state.get("current_iteration", 0) > 0:
                parts.append(self._load("researcher/island_evolution.md"))

            # Has error: inject feedback interpretation
            if state.get("error_message"):
                parts.append(self._load("researcher/feedback_interpretation.md"))

            # Market regime context: inject regime detection
            if state.get("market_regime") or state.get("market_context"):
                parts.append(self._load("researcher/market_regime_detection.md"))

            # Subspace-specific skill
            subspace = kwargs.get("subspace")
            if subspace is not None:
                subspace_file_map = {
                    "FACTOR_ALGEBRA": "researcher/subspaces/factor_algebra.md",
                    "SYMBOLIC_MUTATION": "researcher/subspaces/symbolic_mutation.md",
                    "CROSS_MARKET": "researcher/subspaces/cross_market.md",
                    "NARRATIVE_MINING": "researcher/subspaces/narrative_mining.md",
                }
                subspace_key = subspace.value if hasattr(subspace, "value") else str(subspace)
                skill_path = subspace_file_map.get(subspace_key)
                if skill_path:
                    parts.append(self._load(skill_path))

            # Island-specific skill
            island = kwargs.get("island")
            if island and island in ISLAND_FILE_MAP:
                parts.append(self._load(ISLAND_FILE_MAP[island]))

    # ── Legacy compatibility ──────────────────────────────

    def load_for_researcher(self, state: Any, subspace: Any = None) -> str:
        """Legacy wrapper — delegates to load_for_agent."""
        return self.load_for_agent("researcher", state, subspace=subspace)

    def load_for_coder(self) -> str:
        """Legacy (dead code — Coder is deterministic, no LLM calls)."""
        parts = [
            self._load("constraints/qlib_formula_syntax.md", required=True),
            self._load("coder/qlib_debugging.md", required=True),
        ]
        return "\n\n---\n\n".join(p for p in parts if p)

    def load_for_critic(self) -> str:
        """Legacy (dead code — Critic is deterministic, no LLM calls)."""
        parts = [
            self._load("constraints/a_share_constraints.md", required=True),
        ]
        return "\n\n---\n\n".join(p for p in parts if p)

    # ─────────────────────────────────────────────
    def _load(self, relative_path: str, required: bool = False) -> Optional[str]:
        """加载单个 Skill 文档。"""
        full_path = os.path.join(_SKILLS_BASE, relative_path)
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            if required:
                logger.warning("[SkillLoader] 必要的 Skill 文档缺失：%s", full_path)
            return None
        except Exception as e:
            logger.error("[SkillLoader] 加载 Skill 文档失败 %s: %s", full_path, e)
            return None
```

**Step 4: Run tests to verify backward compatibility**

Run: `uv run pytest tests/test_stage4.py::TestSkillLoader tests/test_stage4.py::TestSkillLoaderGenericInterface -v`
Expected: All PASS (legacy tests unchanged, new tests pass)

**Step 5: Commit**

```bash
git add src/skills/loader.py tests/test_stage4.py
git commit -m "refactor(skills): add generic load_for_agent() interface with backward-compatible legacy wrappers"
```

---

### Task 2: Create Skill Files (7 new markdown files)

**Files:**
- Create: `knowledge/skills/market_analyst/context_framing.md`
- Create: `knowledge/skills/prefilter/filter_guidance.md`
- Create: `knowledge/skills/exploration/a_share_coding_constraints.md`
- Create: `knowledge/skills/researcher/islands/momentum.md`
- Create: `knowledge/skills/researcher/islands/valuation.md`
- Create: `knowledge/skills/researcher/islands/volatility.md`
- Create: `knowledge/skills/researcher/islands/northbound.md`

**Step 1: Create directory structure**

```bash
mkdir -p knowledge/skills/market_analyst
mkdir -p knowledge/skills/prefilter
mkdir -p knowledge/skills/exploration
mkdir -p knowledge/skills/researcher/islands
```

**Step 2: Write each skill file**

Each file should be 50-150 lines of domain-specific guidance in markdown. Content guidelines per file:

**`market_analyst/context_framing.md`** — 指导 MarketAnalyst 从 MCP 工具数据生成结构化 MarketContextMemo：
- 从价量数据提炼 regime 信号的规范（趋势/震荡/高波动判定标准）
- 融资融券余额到 market_sentiment 的映射规则
- 新闻/公告归类标准（policy_signal / sector_rotation / event_driven）
- MarketContextMemo 各字段填写标准和优先级

**`prefilter/filter_guidance.md`** — 补充 Filter C（AlignmentChecker）的 LLM 判断规范：
- 必须拒绝的假设特征（look-ahead bias、无经济意义的公式结构）
- 应该放行的假设特征（IC 预估偏低但机制解释清晰）
- Novelty 判断标准（实质性差异 vs 参数微调）
- 常见误判模式（过度保守 / 过度宽松）

**`exploration/a_share_coding_constraints.md`** — ExplorationAgent 的 A 股代码规范：
- qlib API 使用模式（`qlib.init` 路径、`D.features` 用法）
- 禁止的代码模式（直接访问 .csv、引用未挂载数据）
- 可用数据字段声明（$close/$open/$high/$low/$volume/$factor/$vwap）
- 常见陷阱（NaN 处理、日期对齐、universe 泄漏）

**`researcher/islands/momentum.md`** — A 股动量因子特异性：
- T+1 时滞对动量衰减的影响
- 追涨杀跌散户行为放大短期动量
- 涨跌停制度对连续涨幅的截断效应
- 有效的时间窗口（5/10/20日 vs 美股常见的 12 个月）

**`researcher/islands/valuation.md`** — A 股估值因子适配：
- 散户定价 vs 机构定价的差异
- 壳资源溢价对小市值估值的扭曲
- 退市新规后估值因子有效性变化
- PE/PB/PS 在 A 股的适用条件

**`researcher/islands/volatility.md`** — A 股波动率因子特征：
- 涨跌停制度对已实现波动率的截断
- 日历效应（周一/月末/季末 波动率异常）
- 波动率非对称性（下跌波动率 vs 上涨波动率）
- 低波动异象在 A 股的表现

**`researcher/islands/northbound.md`** — 北向资金因子构建规范：
- 数据特征（每日净买入额、持股占比、增减仓幅度）
- 信号解读（趋势性增仓 vs 短期波动）
- 与 A 股情绪周期的领先/滞后关系
- 数据陷阱（节假日缺失、沪深港通差异）

**Step 3: Commit**

```bash
git add knowledge/skills/
git commit -m "feat(skills): add 7 new skill files for MarketAnalyst, PreFilter, ExplorationAgent, and island-specific guidance"
```

---

### Task 3: Inject Skills into MarketAnalyst

**Files:**
- Modify: `src/agents/market_analyst.py` (line 37, 112)

**Step 1: Write the failing test**

Add to `tests/test_stage4.py`:

```python
class TestMarketAnalystSkillInjection:
    def test_market_analyst_skill_loaded(self, loader):
        result = loader.load_for_agent("market_analyst")
        # Should include Type A constraint + Type B market_analyst skill
        assert len(result) > 0
        # a_share_constraints should be present
        assert "T+1" in result or "前视偏差" in result
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stage4.py::TestMarketAnalystSkillInjection -v`
Expected: FAIL (skill file doesn't exist yet → returns only constraints)

Wait — this test should pass even without the skill file if we just check for constraints. Adjust test to check for market_analyst-specific content after the skill file is created in Task 2.

**Step 3: Modify market_analyst.py**

At `src/agents/market_analyst.py`, add import and inject skill into system prompt:

```python
# Add import at top
from src.skills.loader import SkillLoader

# Near line 112, modify the system message construction:
_skill_loader = SkillLoader()
_market_analyst_skills = _skill_loader.load_for_agent("market_analyst")

# In the messages list, append skill context to system prompt:
SystemMessage(content=MARKET_ANALYST_SYSTEM_PROMPT.format(today=_today_str()) + "\n\n" + _market_analyst_skills),
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_stage4.py -v -m "smoke or unit"`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/agents/market_analyst.py tests/test_stage4.py
git commit -m "feat(stage1): inject SkillLoader into MarketAnalyst system prompt"
```

---

### Task 4: Inject Skills into PreFilter (AlignmentChecker)

**Files:**
- Modify: `src/agents/prefilter.py` (around line 174, AlignmentChecker)

**Step 1: Write the failing test**

```python
class TestPreFilterSkillInjection:
    def test_prefilter_skill_loaded(self, loader):
        result = loader.load_for_agent("prefilter")
        assert len(result) > 0
```

**Step 2: Modify prefilter.py**

In `AlignmentChecker.__init__` or at module level, load the prefilter skill and prepend to `ALIGNMENT_PROMPT`:

```python
from src.skills.loader import SkillLoader

_skill_loader = SkillLoader()
_prefilter_skills = _skill_loader.load_for_agent("prefilter")

# Modify ALIGNMENT_PROMPT to include skill context:
ALIGNMENT_PROMPT_FULL = _prefilter_skills + "\n\n" + ALIGNMENT_PROMPT
```

Then use `ALIGNMENT_PROMPT_FULL` in the `AlignmentChecker.check()` method where `ALIGNMENT_PROMPT` is currently used.

**Step 3: Run tests**

Run: `uv run pytest tests/test_stage4.py -v -m "smoke or unit"`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/agents/prefilter.py tests/test_stage4.py
git commit -m "feat(stage3): inject SkillLoader into PreFilter AlignmentChecker"
```

---

### Task 5: Inject Skills into ExplorationAgent

**Files:**
- Modify: `src/execution/exploration_agent.py` (line 9, 44)

**Step 1: Write the failing test**

```python
class TestExplorationAgentSkillInjection:
    def test_exploration_skill_loaded(self, loader):
        result = loader.load_for_agent("exploration")
        assert len(result) > 0
```

**Step 2: Modify exploration_agent.py**

```python
from src.skills.loader import SkillLoader

_skill_loader = SkillLoader()
_exploration_skills = _skill_loader.load_for_agent("exploration")

# In ExplorationAgent.explore(), modify message construction:
messages = [
    {"role": "system", "content": EXPLORATION_SYSTEM_PROMPT + "\n\n" + _exploration_skills},
    {"role": "user", "content": prompt}
]
```

**Step 3: Run tests**

Run: `uv run pytest tests/test_stage4.py -v -m "smoke or unit"`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/execution/exploration_agent.py tests/test_stage4.py
git commit -m "feat(stage4): inject SkillLoader into ExplorationAgent system prompt"
```

---

### Task 6: Pass Island Parameter to SkillLoader in Researcher

**Files:**
- Modify: `src/agents/researcher.py` (line 204)

**Step 1: Write the failing test**

```python
class TestResearcherIslandSkillInjection:
    def test_researcher_with_island_loads_island_skill(self, loader):
        result = loader.load_for_agent(
            "researcher", _state(iteration=0), island="momentum"
        )
        # After momentum.md exists, this should contain A-share momentum content
        assert len(result) > 0

    def test_researcher_without_island_no_island_skill(self, loader):
        result = loader.load_for_agent("researcher", _state(iteration=0))
        # Should not contain island-specific content
        assert "T+1 时滞" not in result  # momentum-specific
```

**Step 2: Modify researcher.py**

At line 204, change the skill loader call to pass the island:

```python
# Before (line 204):
skill_context = self.skill_loader.load_for_researcher(
    _state_proxy, subspace=subspace_hint
)

# After:
skill_context = self.skill_loader.load_for_agent(
    "researcher", _state_proxy, subspace=subspace_hint, island=self.island
)
```

**Step 3: Fix market_regime_detection injection**

This is now handled by the `_apply_conditional_rules` in Task 1 — when `state.get("market_context")` is truthy (which it is when MarketContextMemo is passed), `market_regime_detection.md` gets injected automatically.

**Step 4: Run tests**

Run: `uv run pytest tests/test_stage4.py -v -m "smoke or unit"`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/agents/researcher.py tests/test_stage4.py
git commit -m "feat(stage2): pass island param to SkillLoader, enable island-specific and regime skills"
```

---

### Task 7: Smoke Test — All Roles Return Non-Empty

**Files:**
- Modify: `tests/test_stage4.py`

**Step 1: Write parameterized smoke test**

```python
import pytest

class TestSkillsSmoke:
    @pytest.mark.parametrize("role", ["researcher", "market_analyst", "prefilter", "exploration"])
    def test_all_roles_return_nonempty(self, loader, role):
        result = loader.load_for_agent(role)
        assert len(result) > 0, f"load_for_agent('{role}') returned empty"

    @pytest.mark.parametrize("island", ["momentum", "valuation", "volatility", "northbound"])
    def test_island_files_exist_and_load(self, loader, island):
        result = loader.load_for_agent("researcher", _state(iteration=0), island=island)
        assert len(result) > len(
            loader.load_for_agent("researcher", _state(iteration=0))
        ), f"Island '{island}' skill did not add content"
```

**Step 2: Run full test suite**

Run: `uv run pytest -q tests -m "smoke or unit"`
Expected: All PASS

**Step 3: Commit**

```bash
git add tests/test_stage4.py
git commit -m "test(skills): add smoke tests for all agent roles and island skills"
```

---

### Task 8: Final Integration Verification

**Step 1: Run full test suite**

```bash
uv run pytest -q tests -m "smoke or unit"
```
Expected: All pass, no regressions.

**Step 2: Verify skill loading in debug log**

```bash
PIXIU_LOG_LEVEL=DEBUG uv run python -c "
from src.skills.loader import SkillLoader
loader = SkillLoader()
for role in ['researcher', 'market_analyst', 'prefilter', 'exploration']:
    result = loader.load_for_agent(role)
    print(f'{role}: {len(result)} chars loaded')
# Test island injection
result = loader.load_for_agent('researcher', {'current_iteration': 0}, island='momentum')
print(f'researcher+momentum: {len(result)} chars loaded')
"
```

**Step 3: Commit all and tag**

```bash
git add -A
git commit -m "feat(phase4b): complete multi-agent skills expansion — all LLM-driven agents now have skill injection"
```
