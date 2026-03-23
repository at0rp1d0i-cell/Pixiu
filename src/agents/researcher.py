"""
Pixiu v2: AlphaResearcher Agent（高通量批量生成版）

Stage 2 设计哲学：Agent 不受"研究员同时只能研究一个方向"的约束。
每次 LLM 调用强制生成 2-3 个差异化假设（AlphaResearcherBatch），
6 个 Island 并行 → 每轮漏斗入口 12-18 个候选。
"""
import asyncio
import json
import logging
import re
import uuid
from collections import Counter
from datetime import date
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.schemas.research_note import FactorResearchNote, AlphaResearcherBatch
from src.schemas.hypothesis import Hypothesis, StrategySpec, ExplorationSubspace
from src.schemas.stage_io import HypothesisGenOutput
from src.schemas.judgment import CriticVerdict
from src.schemas.market_context import MarketContextMemo
from src.factor_pool.pool import FactorPool
from src.formula.capabilities import (
    FormulaCapabilities,
    format_available_fields_for_prompt,
    format_available_operators_for_prompt,
    get_runtime_formula_capabilities,
)
from src.llm.openai_compat import build_researcher_llm
from src.scheduling.subspace_scheduler import SubspaceScheduler, SchedulerState
from src.scheduling.subspace_context import build_subspace_context
from src.schemas.exploration import SubspaceRegistry
from src.skills.loader import SkillLoader
from src.hypothesis.mutation import SymbolicMutator, try_all_mutations, build_mutation_record_dict
logger = logging.getLogger(__name__)

_SKILL_LOADER = SkillLoader()
_MAX_STAGE2_REJECTION_SAMPLES = 5
_MAX_LOCAL_RETRY = 1

# ====================================================
# System Prompt（对齐 docs/design/stage-2-hypothesis-expansion.md）
# ====================================================
ALPHA_RESEARCHER_SYSTEM_PROMPT = """你是 Pixiu 的 Alpha 研究员，专注于 A 股市场量化因子发现。

禁止：
- 使用 Ref($close, -N) 等未来数据
- 使用未注册的字段名（见下方字段约束）
- 输出 JSON 以外的任何内容

可用字段（当前运行时，以本地 Qlib feature store 为准）：
{available_fields_block}

可用算子（当前运行时 allowlist）：
{available_operators_block}

注意：
- 只有上方明确列出的字段和算子可以出现在 proposed_formula 中
- 不要假设某个“常见字段”一定可用
- 如果估值/基本面字段当前不可用，请退化到价量代理

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
  - applicable_regimes: 字符串数组，声明该因子适用的市场环境，**必填**（至少一项）
  - invalid_regimes: 字符串数组，声明该因子失效的市场环境，**必填**（至少一项）

合法的 regime 标签（仅限以下值，其他值会被 Validator 拒绝）：
  - "bull_trend"       — 趋势上涨市
  - "bear_trend"       — 趋势下跌市
  - "high_volatility"  — 高波动市
  - "range_bound"      — 震荡盘整市
  - "structural_break" — 结构性断裂（黑天鹅/政策突变）

示例：applicable_regimes: ["bull_trend", "high_volatility"]，invalid_regimes: ["range_bound"]

⚠️ 生成公式前的强制检查：
1. 不要假设 Stage 3 会替你自动补 Max(..., 1e-8)、+1 或其他“保护壳”
2. Div/Mod/Log/Sqrt 只有在公式本身能满足当前 canonical 数学安全约束时才能使用；如果无法确保，换一个更稳健的表达
3. applicable_regimes 和 invalid_regimes 必须至少各填写一个，使用上述合法标签
4. Ref 的偏移量必须为正整数（Ref($close, 5) 表示 5 天前）
5. Rank 必须写成 Rank(expr, N)，禁止 Rank(expr)
6. 归一化仅允许 Rank(expr, N) 或 Quantile(expr, N, qscore)；禁止 Zscore/MinMax/Neutralize/Demean

违反以上任何一条，因子将被 Validator 直接拒绝。
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

def _today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


def _build_researcher_system_prompt(capabilities: FormulaCapabilities) -> str:
    return ALPHA_RESEARCHER_SYSTEM_PROMPT.format(
        available_fields_block=format_available_fields_for_prompt(capabilities),
        available_operators_block=format_available_operators_for_prompt(capabilities),
    )


class AlphaResearcher:
    """单 Island 的 Alpha 因子批量生成器。"""

    def __init__(self, island: str, skill_loader: Optional[SkillLoader] = None,
                 registry: Optional[SubspaceRegistry] = None,
                 factor_pool: Optional[FactorPool] = None,
                 capabilities: Optional[FormulaCapabilities] = None):
        self.island = island
        self.skill_loader = skill_loader or _SKILL_LOADER
        self.capabilities = capabilities or get_runtime_formula_capabilities()
        self.registry = registry or SubspaceRegistry.get_default_registry(capabilities=self.capabilities)
        self.factor_pool = factor_pool
        self._llm = None
        self.last_generation_diagnostics: dict[str, Any] = {}

    def _get_llm(self):
        if self._llm is None:
            self._llm = build_researcher_llm(profile="researcher")
        return self._llm

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
                approved_notes, diagnostics = self._local_prescreen_notes(symbolic_batch.notes)
                self.last_generation_diagnostics = {
                    "generated_count": diagnostics["generated_count"],
                    "delivered_count": len(approved_notes),
                    "local_retry_count": 0,
                    "rejection_counts_by_filter": diagnostics["rejection_counts_by_filter"],
                    "sample_rejections": diagnostics["sample_rejections"],
                }
                if not approved_notes:
                    logger.info(
                        "[AlphaResearcher] SYMBOLIC_MUTATION 本地预筛后无可用候选: island=%s",
                        self.island,
                    )
                return symbolic_batch.model_copy(update={"notes": approved_notes})

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

        # 加载 Skill 文档（Type A/B 硬约束 + Type C 条件注入 + 子空间推理框架）
        _state_proxy = {
            "current_iteration": iteration,
            "error_message": (
                last_verdict.failure_explanation
                if last_verdict and not last_verdict.overall_passed
                else None
            ),
            "market_context": context,
            "market_regime": (
                context.market_regime if context is not None else None
            ),
        }
        skill_context = self.skill_loader.load_for_agent(
            "researcher",
            _state_proxy,
            subspace=subspace_hint,
            island=self.island,
        )
        system_content = _build_researcher_system_prompt(self.capabilities)
        if skill_context:
            system_content = (
                system_content + "\n\n## 研究规范与子空间框架\n\n" + skill_context
            )

        llm = self._get_llm()
        local_rejection_feedback = "无"
        total_generated_count = 0
        local_retry_count = 0
        rejection_counts = Counter()
        sample_rejections: list[dict[str, str]] = []

        for attempt in range(_MAX_LOCAL_RETRY + 1):
            user_msg = ALPHA_RESEARCHER_USER_TEMPLATE.format(
                island=self.island,
                island_description=island_info.get("description", ""),
                subspace_hint=hint_text,
                market_context=mkt_ctx,
                feedback_section=fb,
                failed_factors_section=failed_section,
            )
            if attempt > 0:
                user_msg += (
                    "\n\n## 本地预筛拒绝反馈（重试约束）\n"
                    f"{local_rejection_feedback}\n"
                    "\n## 重试硬约束\n"
                    "- Rank 必须写成 Rank(expr, N)，禁止 Rank(expr)\n"
                    "- 归一化仅允许 Rank(expr, N) 或 Quantile(expr, N, qscore)\n"
                    "- 禁止 Zscore/MinMax/Neutralize/Demean\n"
                    "- 避免重复提交与本地预筛已拒绝原因相同的模式\n"
                )

            response = await llm.ainvoke([
                SystemMessage(content=system_content),
                HumanMessage(content=user_msg),
            ])

            parsed_batch = self._parse_batch(response.content, iteration, subspace_hint)
            approved_notes, diagnostics = self._local_prescreen_notes(parsed_batch.notes)

            total_generated_count += diagnostics["generated_count"]
            rejection_counts.update(diagnostics["rejection_counts_by_filter"])
            for sample in diagnostics["sample_rejections"]:
                if len(sample_rejections) >= _MAX_STAGE2_REJECTION_SAMPLES:
                    break
                sample_rejections.append(sample)

            if approved_notes or diagnostics["generated_count"] == 0:
                self.last_generation_diagnostics = {
                    "generated_count": total_generated_count,
                    "delivered_count": len(approved_notes),
                    "local_retry_count": local_retry_count,
                    "rejection_counts_by_filter": dict(rejection_counts),
                    "sample_rejections": sample_rejections,
                }
                return parsed_batch.model_copy(update={"notes": approved_notes})

            if attempt < _MAX_LOCAL_RETRY:
                local_retry_count += 1
                local_rejection_feedback = self._build_local_rejection_feedback(
                    diagnostics.get("sample_rejections", [])
                )
                logger.info(
                    "[AlphaResearcher] 本地预筛全拒绝，触发重试: island=%s, attempt=%d",
                    self.island,
                    attempt + 1,
                )

        self.last_generation_diagnostics = {
            "generated_count": total_generated_count,
            "delivered_count": 0,
            "local_retry_count": local_retry_count,
            "rejection_counts_by_filter": dict(rejection_counts),
            "sample_rejections": sample_rejections,
        }
        return AlphaResearcherBatch(
            island=self.island,
            notes=[],
            generation_rationale="本地预筛后无可用候选",
        )

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

    def _local_prescreen_notes(
        self, notes: list[FactorResearchNote]
    ) -> tuple[list[FactorResearchNote], dict[str, Any]]:
        """Stage 2 本地预筛：复用 Stage 3 的 canonical validator/novelty 规则。"""
        from src.agents.prefilter import NoveltyFilter, Validator

        approved_notes: list[FactorResearchNote] = []
        rejection_counts = Counter()
        sample_rejections: list[dict[str, str]] = []

        validator = Validator(
            allowed_fields=set(self.capabilities.available_fields),
            approved_operators=set(self.capabilities.approved_operators),
        )
        novelty_filter = NoveltyFilter(pool=self.factor_pool) if self.factor_pool is not None else None

        for note in notes:
            passed, reason = validator.validate(note)
            if not passed:
                rejection_counts["validator"] += 1
                if len(sample_rejections) < _MAX_STAGE2_REJECTION_SAMPLES:
                    sample_rejections.append(
                        {"note_id": note.note_id, "filter": "validator", "reason": reason}
                    )
                continue

            if novelty_filter is not None:
                passed, reason = novelty_filter.check(note)
                if not passed:
                    rejection_counts["novelty"] += 1
                    if len(sample_rejections) < _MAX_STAGE2_REJECTION_SAMPLES:
                        sample_rejections.append(
                            {"note_id": note.note_id, "filter": "novelty", "reason": reason}
                        )
                    continue

            approved_notes.append(note)

        return approved_notes, {
            "generated_count": len(notes),
            "delivered_count": len(approved_notes),
            "rejection_counts_by_filter": dict(rejection_counts),
            "sample_rejections": sample_rejections,
        }

    @staticmethod
    def _build_local_rejection_feedback(sample_rejections: list[dict[str, str]]) -> str:
        if not sample_rejections:
            return "本地预筛未通过，但无拒绝样本。请更换思路并避免重复提交已被本地预筛拒绝的模式。"
        lines = []
        for idx, item in enumerate(sample_rejections[:3], start=1):
            lines.append(f"{idx}. [{item.get('filter', 'unknown')}] {item.get('reason', '')}")
        lines.append("请避免重复提交与上述拒绝原因相同的公式模式。")
        return "\n".join(lines)


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
    factor_pool = state.get("factor_pool")
    if factor_pool is None:
        try:
            from src.factor_pool.pool import get_factor_pool
            factor_pool = get_factor_pool()
        except Exception as e:
            logger.debug("Stage 2 无法获取 factor pool，降级为无池模式: %s", e)
            factor_pool = None

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
    researchers = [
        AlphaResearcher(island=island, factor_pool=factor_pool)
        for island, _ in assignments
    ]
    tasks = [
        researcher.generate_batch(
            context=context,
            iteration=iteration,
            subspace_hint=subspace,
        )
        for researcher, (_, subspace) in zip(researchers, assignments)
    ]

    batches: list = await asyncio.gather(*tasks, return_exceptions=True)

    # 展开：每个 batch 包含 2-3 个 notes，汇总为一个大列表
    all_notes: list[FactorResearchNote] = []
    subspace_results: dict[ExplorationSubspace, list[int, int]] = {
        s: [0, 0] for s in ExplorationSubspace
    }
    stage2_rejection_counts = Counter()
    stage2_sample_rejections: list[dict[str, str]] = []
    stage2_generated_count = 0
    stage2_delivered_count = 0
    stage2_retry_count = 0

    for (island, subspace), researcher, batch in zip(assignments, researchers, batches):
        diagnostics = researcher.last_generation_diagnostics or {}
        stage2_generated_count += int(diagnostics.get("generated_count", 0))
        stage2_delivered_count += int(diagnostics.get("delivered_count", 0))
        stage2_retry_count += int(diagnostics.get("local_retry_count", 0))
        stage2_rejection_counts.update(diagnostics.get("rejection_counts_by_filter", {}))
        for item in diagnostics.get("sample_rejections", []):
            if len(stage2_sample_rejections) >= _MAX_STAGE2_REJECTION_SAMPLES:
                break
            stage2_sample_rejections.append(item)

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
        "stage2_diagnostics": {
            "generated_count": stage2_generated_count,
            "delivered_count": stage2_delivered_count,
            "local_retry_count": stage2_retry_count,
            "rejection_counts_by_filter": dict(stage2_rejection_counts),
            "sample_rejections": stage2_sample_rejections,
        },
    }


def hypothesis_gen_node(state: dict) -> HypothesisGenOutput:
    """LangGraph 同步入口。"""
    return asyncio.run(_hypothesis_gen_async(state))
