"""
Pixiu v2: AlphaResearcher Agent（高通量批量生成版）

Stage 2 设计哲学：Agent 不受"研究员同时只能研究一个方向"的约束。
每次 LLM 调用强制生成 2-3 个差异化假设（AlphaResearcherBatch），
6 个 Island 并行 → 每轮漏斗入口 12-18 个候选。
"""
import asyncio
import json
import logging
import os
import re
import uuid
from datetime import date
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.schemas.research_note import FactorResearchNote, AlphaResearcherBatch
from src.schemas.hypothesis import Hypothesis, StrategySpec, ExplorationSubspace
from src.schemas.stage_io import HypothesisGenOutput
from src.schemas.judgment import CriticVerdict
from src.schemas.market_context import MarketContextMemo
from src.factor_pool.pool import FactorPool
from src.llm.openai_compat import build_researcher_llm
from src.scheduling.subspace_scheduler import SubspaceScheduler, SchedulerState
from src.scheduling.subspace_context import build_subspace_context
from src.schemas.exploration import SubspaceRegistry
from src.skills.loader import SkillLoader
from src.hypothesis.mutation import SymbolicMutator, try_all_mutations, build_mutation_record_dict
logger = logging.getLogger(__name__)

_SKILL_LOADER = SkillLoader()

# ====================================================
# System Prompt（对齐 docs/design/stage-2-hypothesis-expansion.md）
# ====================================================
ALPHA_RESEARCHER_SYSTEM_PROMPT = """你是 Pixiu 的 Alpha 研究员，专注于 A 股市场量化因子发现。

禁止：
- 使用 Ref($close, -N) 等未来数据
- 使用未注册的字段名（见下方字段约束）
- 输出 JSON 以外的任何内容

可用字段（当前阶段）：
  基础价量字段（始终可用）：$close, $open, $high, $low, $volume, $factor, $amount, $vwap
  扩展基本面字段（仅在 FUNDAMENTAL_FIELDS_ENABLED=true 时可用）：
    $pe_ttm, $pb, $roe, $revenue_yoy, $profit_yoy, $turnover_rate, $float_mv

输出格式：返回一个 JSON 对象，包含字段：
  - notes: 一个包含 2-3 个 FactorResearchNote 的数组
  - generation_rationale: 字符串，说明为何选择这几个研究方向

每个 Note 的经济逻辑必须彼此差异化，禁止提交同一个公式的微小变体。

每个 FactorResearchNote 必须包含以下字段：
  - note_id: 字符串（可填任意唯一 ID，系统会自动覆盖）
  - island: 字符串（研究方向，如 "momentum"）
  - iteration: 整数（迭代轮次）
  - hypothesis: 字符串（经济直觉，100-300字）
  - economic_intuition: 字符串（为何此因子有效）
  - proposed_formula: 字符串（合法 Qlib 公式）
    关键规则（违反会被直接过滤）：
    1. 必须是单行表达式，不能有换行、注释（#）、或变量赋值（=）
    2. Ref(x, N) 中 N 必须为正整数：Ref($close, 1) = 昨日，Ref($close, 5) = 5日前（不能用负数）
    3. 如果假设难以用单行公式表达，选择最核心部分用合法公式近似，hypothesis 字段描述完整逻辑
  - risk_factors: 字符串数组（可能失败的原因）
  - market_context_date: 字符串（今日日期，格式 YYYY-MM-DD）
"""

ALPHA_RESEARCHER_USER_TEMPLATE = """
## 当前 Island：{island}
{island_description}

## 探索子空间上下文
{subspace_hint}

## 市场上下文
{market_context}

## 历史反馈
{feedback_section}

## 历史失败因子（避免重复）
{failed_factors_section}

请提出 2-3 个差异化的 FactorResearchNote，输出 AlphaResearcherBatch JSON。
每个假设应捕捉 {island} 方向下不同的市场机制，而非同一思路的变体。
每个假设必须声明 applicable_regimes（适用市场环境）和 invalid_regimes（失效环境）。
"""

# 子空间到 prompt 指令的映射
_SUBSPACE_PROMPTS = {
    ExplorationSubspace.FACTOR_ALGEBRA: (
        "本轮优先使用【因子代数搜索】方法：基于价量/基本面原语的受约束组合，"
        "关注时间变换、截面算子、交互项构造。"
    ),
    ExplorationSubspace.NARRATIVE_MINING: (
        "本轮优先使用【经济叙事挖掘】方法：从政策口径、产业链叙事、"
        "市场预期错位中抽取机制假设，将定性洞察转化为可测因子。"
    ),
    ExplorationSubspace.SYMBOLIC_MUTATION: (
        "本轮优先使用【符号变异】方法：对已知因子做结构化变异——"
        "添加/移除算子、交换时间窗口、改变归一化、修改交互项。"
    ),
    ExplorationSubspace.CROSS_MARKET: (
        "本轮优先使用【跨市场模式迁移】方法：从美股/港股/商品/利率的"
        "已知 alpha 机制中提取逻辑骨架，适配 A 股市场特征。"
    ),
}


def _today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


FUNDAMENTAL_FIELDS_ENABLED = os.getenv("FUNDAMENTAL_FIELDS_ENABLED", "false").lower() == "true"


class AlphaResearcher:
    """单 Island 的 Alpha 因子批量生成器。"""

    def __init__(self, island: str, skill_loader: Optional[SkillLoader] = None,
                 registry: Optional[SubspaceRegistry] = None,
                 factor_pool: Optional[FactorPool] = None):
        self.island = island
        self.skill_loader = skill_loader or _SKILL_LOADER
        self.registry = registry or SubspaceRegistry.get_default_registry()
        self.factor_pool = factor_pool
        self.llm = build_researcher_llm(temperature=0.8)

    async def generate_batch(
        self,
        context: Optional[MarketContextMemo],
        iteration: int,
        last_verdict: Optional[CriticVerdict] = None,
        failed_formulas: Optional[list] = None,
        subspace_hint: Optional[ExplorationSubspace] = None,
    ) -> AlphaResearcherBatch:
        """
        调用 LLM 一次，生成 2-3 个差异化的 FactorResearchNote。
        subspace_hint: 建议的探索方法，注入 prompt 引导生成方向。
        """
        from src.factor_pool.islands import ISLANDS
        island_info = ISLANDS.get(self.island, {})

        # 构建市场上下文字符串
        if context:
            mkt_ctx = (
                f"市场 Regime：{context.market_regime}\n"
                f"建议 Islands：{', '.join(context.suggested_islands)}\n"
                f"摘要：{context.raw_summary}"
            )
        else:
            mkt_ctx = "（无市场上下文，请基于通用 A 股规律提出假设）"

        # 历史反馈
        if last_verdict and not last_verdict.overall_passed:
            fb = f"上轮失败原因：{last_verdict.failure_explanation}\n建议：{last_verdict.suggested_fix}"
        else:
            fb = "（首次迭代，无历史反馈）"

        # 失败约束：优先从 FactorPool 查询结构化约束，fallback 到传入的 failed_formulas 文本
        failed_section = self._build_constraint_section(failed_formulas)

        # ── SYMBOLIC_MUTATION 纯符号快速路径 ──────────────────
        # 若子空间为 SYMBOLIC_MUTATION 且 FactorPool 中有历史因子，
        # 优先用 SymbolicMutator 纯符号生成，跳过 LLM 调用。
        # 失败（无种子公式 / 所有算子均返回 None）时 fallback 到 LLM 路径。
        if subspace_hint == ExplorationSubspace.SYMBOLIC_MUTATION and self.factor_pool is not None:
            symbolic_batch = self._try_symbolic_mutation_batch(iteration)
            if symbolic_batch is not None:
                return symbolic_batch

        # 子空间探索上下文（结构化注入）
        if subspace_hint:
            hint_text = build_subspace_context(
                subspace=subspace_hint,
                registry=self.registry,
                factor_pool=self.factor_pool,
                island=self.island,
            )
        else:
            hint_text = "不限定探索方法，自由发挥。"

        user_msg = ALPHA_RESEARCHER_USER_TEMPLATE.format(
            island=self.island,
            island_description=island_info.get("description", ""),
            subspace_hint=hint_text,
            market_context=mkt_ctx,
            feedback_section=fb,
            failed_factors_section=failed_section,
        )

        # 加载 Skill 文档（Type A/B 硬约束 + Type C 条件注入 + 子空间推理框架）
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
        system_content = ALPHA_RESEARCHER_SYSTEM_PROMPT
        if skill_context:
            system_content = (
                system_content + "\n\n## 研究规范与子空间框架\n\n" + skill_context
            )

        response = await self.llm.ainvoke([
            SystemMessage(content=system_content),
            HumanMessage(content=user_msg),
        ])

        return self._parse_batch(response.content, iteration, subspace_hint)

    def _parse_batch(self, content: str, iteration: int,
                     subspace_hint: Optional[ExplorationSubspace] = None) -> AlphaResearcherBatch:
        """
        解析 LLM 输出为 AlphaResearcherBatch。
        支持降级：若 LLM 只输出单个 Note，包装为长度为 1 的 Batch。
        """
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match:
            raise ValueError(f"AlphaResearcher 输出不含 JSON：{content[:200]}")

        data = json.loads(match.group())
        notes_data = data.get("notes", [data])  # 兼容降级

        notes = []
        for note_data in notes_data:
            note_data.setdefault("note_id", f"{self.island}_{_today_str()}_{uuid.uuid4().hex[:8]}")
            note_data.setdefault("island", self.island)
            note_data.setdefault("iteration", iteration)
            note_data.setdefault("exploration_questions", [])
            note_data.setdefault("risk_factors", [])
            note_data.setdefault("market_context_date", _today_str())
            # 子空间溯源：优先使用 LLM 输出的值，fallback 到调度器分配的 hint
            if "exploration_subspace" not in note_data and subspace_hint:
                note_data["exploration_subspace"] = subspace_hint.value
            notes.append(FactorResearchNote(**note_data))

        return AlphaResearcherBatch(
            island=self.island,
            notes=notes,
            generation_rationale=data.get("generation_rationale", ""),
        )

    def _try_symbolic_mutation_batch(
        self,
        iteration: int,
        batch_size: int = 3,
    ) -> Optional[AlphaResearcherBatch]:
        """SYMBOLIC_MUTATION 纯符号路径：从 FactorPool 取历史公式，施加所有算子。

        返回 AlphaResearcherBatch 或 None（当无可用种子或无有效变异时）。
        """
        try:
            seeds = self.factor_pool.get_island_best_factors(self.island, top_k=5)
            if not seeds:
                logger.debug(
                    "[AlphaResearcher] SYMBOLIC_MUTATION: no seed factors for island=%s, fallback to LLM",
                    self.island,
                )
                return None

            mutator = SymbolicMutator()
            candidates = []
            for seed in seeds:
                formula = seed.get("formula", "")
                if not formula:
                    continue
                results = try_all_mutations(formula, mutator)
                candidates.extend(results)

            if not candidates:
                logger.debug(
                    "[AlphaResearcher] SYMBOLIC_MUTATION: no valid mutations for island=%s, fallback to LLM",
                    self.island,
                )
                return None

            # 取前 batch_size 个，转换为 FactorResearchNote
            notes = []
            for mut_result in candidates[:batch_size]:
                note_id = f"{self.island}_{_today_str()}_{uuid.uuid4().hex[:8]}"
                mutation_dict = build_mutation_record_dict(mut_result)
                note = FactorResearchNote(
                    note_id=note_id,
                    island=self.island,
                    iteration=iteration,
                    hypothesis=f"符号变异: {mut_result.description}",
                    economic_intuition=f"对历史因子 {mut_result.source_formula} 施加 {mut_result.operator.value} 算子",
                    proposed_formula=mut_result.result_formula,
                    risk_factors=["纯符号变异，未经 LLM 语义验证"],
                    market_context_date=_today_str(),
                    exploration_subspace=ExplorationSubspace.SYMBOLIC_MUTATION,
                    mutation_record=mutation_dict,
                )
                notes.append(note)

            logger.info(
                "[AlphaResearcher] SYMBOLIC_MUTATION 纯符号路径：island=%s, seeds=%d, candidates=%d, notes=%d",
                self.island, len(seeds), len(candidates), len(notes),
            )
            return AlphaResearcherBatch(
                island=self.island,
                notes=notes,
                generation_rationale=f"SYMBOLIC_MUTATION 纯符号路径：从 {len(seeds)} 个历史因子生成 {len(candidates)} 个候选，取前 {len(notes)} 个",
            )
        except Exception as e:
            logger.warning(
                "[AlphaResearcher] _try_symbolic_mutation_batch failed: %s, fallback to LLM", e
            )
            return None

    def _build_constraint_section(self, failed_formulas: Optional[list] = None) -> str:
        """构建失败约束提示段落。

        优先从 FactorPool 查询结构化 FailureConstraint（按 island 过滤）；
        若 FactorPool 不可用或无结果，降级为传入的 failed_formulas 文本列表。
        """
        constraints_text = ""
        if self.factor_pool is not None:
            try:
                constraints = self.factor_pool.query_constraints(
                    island=self.island,
                    limit=10,
                )
                hard = [c for c in constraints if c.severity == "hard"]
                warnings = [c for c in constraints if c.severity == "warning"]
                if hard:
                    constraints_text += "## 硬约束（必须遵守）\n"
                    constraints_text += "\n".join(f"- {c.constraint_rule}" for c in hard)
                if warnings:
                    if constraints_text:
                        constraints_text += "\n"
                    constraints_text += "## 警告（建议避免）\n"
                    constraints_text += "\n".join(f"- {c.constraint_rule}" for c in warnings)
            except Exception as e:
                logger.debug("[AlphaResearcher] FailureConstraint query failed: %s", e)

        if not constraints_text:
            # fallback：使用传入的文本列表
            if not failed_formulas:
                return "无"
            return "\n".join(f"- {f}" for f in failed_formulas[:5])

        return constraints_text


# ====================================================
# LangGraph 节点：hypothesis_gen_node
# ====================================================
def _build_island_subspace_assignments(
    allocations: list,
    active_islands: list[str],
) -> list[tuple[str, ExplorationSubspace]]:
    """
    将 subspace 配额分配到 island 调用。

    策略：按配额展开 subspace 列表，round-robin 分配给 islands。
    例：allocations=[algebra:4, narrative:3, mutation:3, cross_market:2], 6 islands
    → 12 个 (island, subspace) 任务对
    """
    # 展开为 subspace 列表（按配额重复）
    subspace_slots: list[ExplorationSubspace] = []
    for alloc in allocations:
        subspace_slots.extend([alloc.subspace] * alloc.quota)

    # Round-robin 分配到 islands
    assignments = []
    for i, subspace in enumerate(subspace_slots):
        island = active_islands[i % len(active_islands)]
        assignments.append((island, subspace))

    return assignments


async def _hypothesis_gen_async(state: dict) -> dict:
    """
    使用 SubspaceScheduler 分配配额，并行运行 AlphaResearcher，
    展开 Batch → 收集所有 notes 进入 Stage 3 过滤。
    """
    from src.factor_pool.islands import ISLANDS

    active_islands = state.get("active_islands", list(ISLANDS.keys()))
    context: Optional[MarketContextMemo] = state.get("market_context")
    iteration: int = state.get("iteration", 0)

    # ── Scheduler 分配 ──
    scheduler = SubspaceScheduler()
    scheduler_state = state.get("scheduler_state") or SchedulerState()
    if isinstance(scheduler_state, dict):
        scheduler_state = SchedulerState(**scheduler_state)

    allocations = scheduler.allocate(scheduler_state)
    warnings = scheduler.get_warnings(scheduler_state)
    for w in warnings:
        logger.warning("SubspaceScheduler: %s", w)

    logger.info(
        "Stage 2 调度器分配: %s",
        {a.subspace.value: a.quota for a in allocations},
    )

    # ── 构建 (island, subspace) 任务对 ──
    assignments = _build_island_subspace_assignments(allocations, active_islands)

    # ── 并行生成（按 island 分组，每组带 subspace hint） ──
    tasks = [
        AlphaResearcher(island=island).generate_batch(
            context=context,
            iteration=iteration,
            subspace_hint=subspace,
        )
        for island, subspace in assignments
    ]

    batches: list = await asyncio.gather(*tasks, return_exceptions=True)

    # 展开：每个 batch 包含 2-3 个 notes，汇总为一个大列表
    all_notes: list[FactorResearchNote] = []
    subspace_results: dict[ExplorationSubspace, list[int, int]] = {
        s: [0, 0] for s in ExplorationSubspace
    }

    for (island, subspace), batch in zip(assignments, batches):
        if isinstance(batch, Exception):
            logger.warning("AlphaResearcher[%s/%s] 失败（跳过）: %s", island, subspace.value, batch)
        else:
            all_notes.extend(batch.notes)
            subspace_results[subspace][0] += len(batch.notes)  # generated

    logger.info(
        "Stage 2 生成 %d 个候选（%d 个任务，%d 个 Island）",
        len(all_notes), len(assignments), len(active_islands),
    )

    # Bridge：将 FactorResearchNote 转换为 Hypothesis + StrategySpec
    hypotheses: list[Hypothesis] = [note.to_hypothesis() for note in all_notes]
    strategy_specs: list[StrategySpec] = [note.to_strategy_spec() for note in all_notes]

    return {
        "research_notes": all_notes,
        "hypotheses": hypotheses,
        "strategy_specs": strategy_specs,
        "scheduler_state": scheduler_state.model_dump(),
        "subspace_generated": {s.value: v[0] for s, v in subspace_results.items()},
    }


def hypothesis_gen_node(state: dict) -> HypothesisGenOutput:
    """LangGraph 同步入口。"""
    return asyncio.run(_hypothesis_gen_async(state))
