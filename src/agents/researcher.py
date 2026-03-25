"""
Pixiu v2: AlphaResearcher Agent（高通量批量生成版）

Stage 2 设计哲学：Agent 不受"研究员同时只能研究一个方向"的约束。
默认每次 LLM 调用生成 2-3 个差异化假设（AlphaResearcherBatch），
6 个 Island 并行 → 常规轮次漏斗入口约 12-18 个候选。
"""
import asyncio
import json
import logging
import os
import re
import uuid
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
from collections.abc import Mapping
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
from src.formula.gene import (
    build_family_gene,
    build_family_gene_key,
    build_variant_gene,
    build_variant_gene_key,
)
from src.formula.family_semantics import render_factor_algebra_family_semantics_block
from src.formula.sketch import (
    ALLOWED_BASE_FIELDS,
    ALLOWED_TRANSFORM_FAMILIES,
    ALLOWED_QUANTILE_QSCORES,
    ALLOWED_WINDOW_BUCKETS,
    FormulaRecipe,
    render_formula_recipe,
    validate_formula_recipe_alignment,
)
from src.llm.call_context import build_llm_call_config
from src.llm.openai_compat import build_researcher_llm
from src.scheduling.subspace_scheduler import SubspaceScheduler, SchedulerState
from src.scheduling.subspace_context import build_subspace_context
from src.schemas.exploration import SubspaceRegistry
from src.skills.loader import SkillLoader
from src.hypothesis.mutation import SymbolicMutator, try_all_mutations, build_mutation_record_dict
from src.hypothesis.grounding import MechanismProxyClaim, validate_grounding_claim
logger = logging.getLogger(__name__)

_SKILL_LOADER = SkillLoader()
_MAX_STAGE2_REJECTION_SAMPLES = 5
_MAX_LOCAL_RETRY = 1
_MAX_ANTI_COLLAPSE_SKELETONS = 3
_FAST_FEEDBACK_MAX_ANTI_COLLAPSE_SKELETONS = 2
_FACTOR_ALGEBRA_BATCH_FAMILY_BUDGET = 1
_FACTOR_ALGEBRA_SATURATED_FAMILY_MIN_VARIANTS = 2
_FACTOR_ALGEBRA_LOW_VALUE_FAMILY_MIN_FAILURES = 2
_FAST_FEEDBACK_NONRETRY_FILTERS = frozenset({"alignment", "novelty", "anti_collapse", "value_density"})
_FACTOR_ALGEBRA_RECIPE_STATUS_PREFIX = "invalid_recipe:"
_FACTOR_ALGEBRA_ALIGNMENT_STATUS_PREFIX = "invalid_alignment:"
_GROUNDING_STATUS_PREFIX = "invalid_grounding:"
_FACTOR_ALGEBRA_RECIPE_PLACEHOLDER_FORMULA = "Mean($close, 5) - Mean($close, 20)"
_FACTOR_ALGEBRA_ALLOWED_FIELDS_TEXT = ", ".join(ALLOWED_BASE_FIELDS)
_FACTOR_GENE_RUNTIME_FIELD = "__factor_gene_runtime"
_FACTOR_GENE_DIAGNOSTICS_KEY = "factor_gene_by_note_id"
_GROUNDING_RUNTIME_FIELD = "__grounding_runtime"
_PROMPT_ASSETS_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "prompt_assets" / "researcher"
_FAST_FEEDBACK_FACTOR_ALGEBRA_ALLOWED_FAMILIES = (
    "mean_spread",
    "ratio_momentum",
    "volatility_state",
)


def _is_fast_feedback_factor_algebra(subspace_hint: Optional[ExplorationSubspace]) -> bool:
    return (
        subspace_hint == ExplorationSubspace.FACTOR_ALGEBRA
        and os.getenv("PIXIU_EXPERIMENT_PROFILE_KIND", "").strip() == "fast_feedback"
    )


def _requested_note_count_text(subspace_hint: Optional[ExplorationSubspace]) -> str:
    if _is_fast_feedback_factor_algebra(subspace_hint):
        return "1"
    return "2-3"


def _is_fast_feedback_profile() -> bool:
    return os.getenv("PIXIU_EXPERIMENT_PROFILE_KIND", "").strip() == "fast_feedback"

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
  - notes: 一个包含目标数量个 FactorResearchNote 的数组
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

请提出 {requested_note_count} 个差异化的 FactorResearchNote，输出 AlphaResearcherBatch JSON。
每个假设应捕捉 {island} 方向下不同的市场机制，而非同一思路的变体。
每个假设必须声明 applicable_regimes（适用市场环境）和 invalid_regimes（失效环境）。
"""

@lru_cache(maxsize=None)
def _read_prompt_asset(filename: str) -> str:
    return (_PROMPT_ASSETS_DIR / filename).read_text(encoding="utf-8").strip()


def _build_factor_algebra_recipe_instruction() -> str:
    return _build_factor_algebra_recipe_instruction_for_families(ALLOWED_TRANSFORM_FAMILIES)


@lru_cache(maxsize=None)
def _build_factor_algebra_recipe_instruction_for_families(
    allowed_transform_families: tuple[str, ...],
) -> str:
    return _read_prompt_asset("factor_algebra_contract.md").format(
        allowed_transform_families_text=" | ".join(allowed_transform_families),
        factor_algebra_family_semantics_block=render_factor_algebra_family_semantics_block(
            allowed_transform_families
        ),
    )


def _build_cross_market_grounding_instruction() -> str:
    return _read_prompt_asset("cross_market_grounding_contract.md")


def _build_narrative_mining_grounding_instruction() -> str:
    return _read_prompt_asset("narrative_mining_grounding_contract.md")


FACTOR_ALGEBRA_RECIPE_INSTRUCTION = _build_factor_algebra_recipe_instruction()
CROSS_MARKET_GROUNDING_INSTRUCTION = _build_cross_market_grounding_instruction()
NARRATIVE_GROUNDING_INSTRUCTION = _build_narrative_mining_grounding_instruction()


def _formula_skeleton(formula: str) -> str:
    """Collapse numeric micro-variants into one readable family skeleton."""
    compact = re.sub(r"\s+", "", formula)
    compact = re.sub(r"(?<![\w$])\d+(?:\.\d+)?e[+-]?\d+(?![\w$])", "EPS", compact, flags=re.IGNORECASE)
    compact = re.sub(r"(?<![\w$])\d+\.\d+(?![\w$])", "Q", compact)
    compact = re.sub(r"(?<![\w$])\d+(?![\w$])", "N", compact)
    return compact


def _format_family_gene_summary(family_key: str) -> str:
    parts = family_key.split("|")
    if len(parts) != 6:
        return family_key
    _, transform_family, base_field, secondary_field, interaction_mode, normalization_kind = parts
    secondary_value = secondary_field if secondary_field != "null" else "none"
    return (
        f"transform_family={transform_family}, "
        f"base_field={base_field}, "
        f"secondary_field={secondary_value}, "
        f"interaction_mode={interaction_mode}, "
        f"normalization_kind={normalization_kind}"
    )


def _legacy_low_value_family_key_from_formula(formula: str) -> str | None:
    compact = re.sub(r"\s+", "", formula)
    ratio_rank = re.fullmatch(
        r"Rank\((\$\w+)/Ref\(\1,(\d+)\)-1,(\d+)\)",
        compact,
    )
    if ratio_rank is not None:
        return f"factor_algebra|ratio_momentum|{ratio_rank.group(1)}|null|none|rank"
    return None


def _build_factor_algebra_retry_family_bans(sample_rejections: list[dict[str, Any]]) -> list[str]:
    volume_confirmation_alignment_hits = 0
    for item in sample_rejections:
        if not isinstance(item, dict):
            continue
        if item.get("filter") != "alignment":
            continue
        family_key = str(item.get("family_gene_key") or "")
        reason = str(item.get("reason") or "").lower()
        if family_key.startswith("factor_algebra|volume_confirmation|") and "volume_confirmation" in reason:
            volume_confirmation_alignment_hits += 1

    banned_families: list[str] = []
    if volume_confirmation_alignment_hits >= 1:
        banned_families.append("volume_confirmation")
    return banned_families


def _build_fast_feedback_factor_algebra_focus_section() -> str:
    allowed = " | ".join(_FAST_FEEDBACK_FACTOR_ALGEBRA_ALLOWED_FAMILIES)
    return (
        "## fast_feedback 限制\n"
        f"- 当前 fast_feedback 的 factor_algebra 只允许使用以下 transform_family：{allowed}\n"
        "- 本 profile 暂停 volume_confirmation；不要提交 volume_confirmation recipe\n"
        "- 优先产出价格代理的单变量结构，先验证 mean_spread / ratio_momentum / volatility_state 的质量"
    )


def _build_fast_feedback_factor_algebra_recipe_instruction() -> str:
    return _build_factor_algebra_recipe_instruction_for_families(
        _FAST_FEEDBACK_FACTOR_ALGEBRA_ALLOWED_FAMILIES
    )


def _should_skip_fast_feedback_retry(
    subspace_hint: Optional[ExplorationSubspace],
    diagnostics: Mapping[str, Any],
) -> bool:
    if not _is_fast_feedback_factor_algebra(subspace_hint):
        return False
    rejection_counts = diagnostics.get("rejection_counts_by_filter")
    if not isinstance(rejection_counts, Mapping) or not rejection_counts:
        return False
    active_filters = {
        str(name)
        for name, count in rejection_counts.items()
        if isinstance(count, int) and count > 0
    }
    if not active_filters:
        return False
    return active_filters.issubset(_FAST_FEEDBACK_NONRETRY_FILTERS)

def _today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


def _note_subspace_value(note: FactorResearchNote) -> str:
    subspace = note.exploration_subspace
    return subspace.value if subspace is not None else "unknown"


def _make_unique_note_id(candidate: Any, *, used_note_ids: set[str], fallback_prefix: str) -> str:
    normalized = candidate.strip() if isinstance(candidate, str) else ""
    base_note_id = normalized or f"{fallback_prefix}_{uuid.uuid4().hex[:8]}"
    note_id = base_note_id
    while note_id in used_note_ids:
        note_id = f"{base_note_id}_{uuid.uuid4().hex[:8]}"
    return note_id


def _factor_gene_identity(payload: dict[str, Any]) -> tuple[str, str | None] | None:
    family_key = payload.get("family_gene_key")
    if not isinstance(family_key, str):
        return None
    variant_key = payload.get("variant_gene_key")
    if isinstance(variant_key, str):
        return family_key, variant_key
    return family_key, None


def _sample_matches_factor_gene_identity(sample: dict[str, Any], *, family_key: str, variant_key: str | None) -> bool:
    sample_family_key = sample.get("family_gene_key")
    if not isinstance(sample_family_key, str) or sample_family_key != family_key:
        return False
    sample_variant_key = sample.get("variant_gene_key")
    if isinstance(sample_variant_key, str):
        return isinstance(variant_key, str) and sample_variant_key == variant_key
    return True


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
        self._factor_gene_by_note_id: dict[str, dict[str, Any]] = {}

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
        调用 LLM 一次，生成目标数量的差异化 FactorResearchNote。
        subspace_hint: 建议的探索方法，注入 prompt 引导生成方向。
        """
        from src.factor_pool.islands import ISLANDS
        island_info = ISLANDS.get(self.island, {})
        self._factor_gene_by_note_id = {}

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
                    "rejection_counts_by_filter_and_subspace": diagnostics["rejection_counts_by_filter_and_subspace"],
                    "sample_rejections": diagnostics["sample_rejections"],
                }
                if self._factor_gene_by_note_id:
                    self.last_generation_diagnostics[_FACTOR_GENE_DIAGNOSTICS_KEY] = dict(self._factor_gene_by_note_id)
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
        rejection_counts_by_filter_and_subspace: dict[str, Counter] = defaultdict(Counter)
        sample_rejections: list[dict[str, str]] = []
        requested_note_count = _requested_note_count_text(subspace_hint)
        retry_banned_transform_families: list[str] = []

        for attempt in range(_MAX_LOCAL_RETRY + 1):
            user_msg = ALPHA_RESEARCHER_USER_TEMPLATE.format(
                island=self.island,
                island_description=island_info.get("description", ""),
                subspace_hint=hint_text,
                market_context=mkt_ctx,
                feedback_section=fb,
                failed_factors_section=failed_section,
                requested_note_count=requested_note_count,
            )
            if subspace_hint == ExplorationSubspace.FACTOR_ALGEBRA:
                if _is_fast_feedback_factor_algebra(subspace_hint):
                    user_msg += "\n" + _build_fast_feedback_factor_algebra_recipe_instruction()
                    user_msg += "\n\n" + _build_fast_feedback_factor_algebra_focus_section()
                else:
                    user_msg += "\n" + FACTOR_ALGEBRA_RECIPE_INSTRUCTION
                anti_collapse_section = self._build_factor_algebra_anti_collapse_section()
                if anti_collapse_section:
                    user_msg += "\n\n" + anti_collapse_section
            elif subspace_hint == ExplorationSubspace.CROSS_MARKET:
                user_msg += "\n" + CROSS_MARKET_GROUNDING_INSTRUCTION
            elif subspace_hint == ExplorationSubspace.NARRATIVE_MINING:
                user_msg += "\n" + NARRATIVE_GROUNDING_INSTRUCTION
            if attempt > 0:
                user_msg += (
                    "\n\n## 本地预筛拒绝反馈（重试约束）\n"
                    f"{local_rejection_feedback}\n"
                    "\n## 重试硬约束\n"
                    "- Rank 必须写成 Rank(expr, N)，禁止 Rank(expr)\n"
                    "- 归一化仅允许 Rank(expr, N) 或 Quantile(expr, N, qscore)\n"
                    f"- base_field/secondary_field 仅允许：{_FACTOR_ALGEBRA_ALLOWED_FIELDS_TEXT}\n"
                    "- `lookback_short/lookback_long/normalization_window` 仅允许: 5, 10, 20, 30, 60\n"
                    "- `quantile_qscore` 仅允许: 0.2, 0.5, 0.8\n"
                    "- 禁止 Zscore/MinMax/Neutralize/Demean\n"
                    "- 避免重复提交与本地预筛已拒绝原因相同的模式\n"
                )
                if retry_banned_transform_families:
                    banned_text = ", ".join(retry_banned_transform_families)
                    user_msg += f"- 本次重试禁止使用以下 transform_family：{banned_text}\n"

            response = await llm.ainvoke(
                [
                    SystemMessage(content=system_content),
                    HumanMessage(content=user_msg),
                ],
                config=build_llm_call_config(
                    stage="hypothesis_gen",
                    round_index=iteration,
                    agent_role="alpha_researcher",
                    llm_profile="researcher",
                    island=self.island,
                    subspace=subspace_hint.value if subspace_hint is not None else None,
                ),
            )

            parsed_batch = self._parse_batch(response.content, iteration, subspace_hint)
            approved_notes, diagnostics = self._local_prescreen_notes(parsed_batch.notes)

            total_generated_count += diagnostics["generated_count"]
            rejection_counts.update(diagnostics["rejection_counts_by_filter"])
            for filter_name, subspace_counts in diagnostics["rejection_counts_by_filter_and_subspace"].items():
                rejection_counts_by_filter_and_subspace[filter_name].update(subspace_counts)
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
                    "rejection_counts_by_filter_and_subspace": {
                        filter_name: dict(subspace_counts)
                        for filter_name, subspace_counts in rejection_counts_by_filter_and_subspace.items()
                    },
                    "sample_rejections": sample_rejections,
                }
                if self._factor_gene_by_note_id:
                    self.last_generation_diagnostics[_FACTOR_GENE_DIAGNOSTICS_KEY] = dict(self._factor_gene_by_note_id)
                return parsed_batch.model_copy(update={"notes": approved_notes})

            if attempt < _MAX_LOCAL_RETRY and _should_skip_fast_feedback_retry(subspace_hint, diagnostics):
                logger.info(
                    "[AlphaResearcher] fast_feedback stop-loss: skip retry after local full rejection "
                    "(island=%s, filters=%s)",
                    self.island,
                    diagnostics.get("rejection_counts_by_filter"),
                )
                break

            if attempt < _MAX_LOCAL_RETRY:
                local_retry_count += 1
                local_rejection_feedback = self._build_local_rejection_feedback(
                    diagnostics.get("sample_rejections", [])
                )
                if _is_fast_feedback_factor_algebra(subspace_hint):
                    retry_banned_transform_families = _build_factor_algebra_retry_family_bans(
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
            "rejection_counts_by_filter_and_subspace": {
                filter_name: dict(subspace_counts)
                for filter_name, subspace_counts in rejection_counts_by_filter_and_subspace.items()
            },
            "sample_rejections": sample_rejections,
        }
        if self._factor_gene_by_note_id:
            self.last_generation_diagnostics[_FACTOR_GENE_DIAGNOSTICS_KEY] = dict(self._factor_gene_by_note_id)
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
        if _is_fast_feedback_factor_algebra(subspace_hint):
            notes_data = notes_data[:1]

        notes = []
        emitted_note_ids: set[str] = set()
        for note_data in notes_data:
            if subspace_hint == ExplorationSubspace.FACTOR_ALGEBRA:
                note_data = self._render_factor_algebra_recipe_into_note(note_data)
            elif subspace_hint in {
                ExplorationSubspace.CROSS_MARKET,
                ExplorationSubspace.NARRATIVE_MINING,
            }:
                note_data = self._render_grounding_claim_into_note(note_data, subspace_hint)
            note_data["note_id"] = _make_unique_note_id(
                note_data.get("note_id"),
                used_note_ids=emitted_note_ids,
                fallback_prefix=f"{self.island}_{_today_str()}",
            )
            note_id = str(note_data["note_id"])
            emitted_note_ids.add(note_id)
            note_data.setdefault("island", self.island)
            note_data.setdefault("iteration", iteration)
            note_data.setdefault("exploration_questions", [])
            note_data.setdefault("risk_factors", [])
            note_data.setdefault("market_context_date", _today_str())
            factor_gene_diagnostics = note_data.pop(_FACTOR_GENE_RUNTIME_FIELD, None)
            grounding_diagnostics = note_data.pop(_GROUNDING_RUNTIME_FIELD, None)
            # 子空间溯源：优先使用 LLM 输出的值，fallback 到调度器分配的 hint
            if "exploration_subspace" not in note_data and subspace_hint:
                note_data["exploration_subspace"] = subspace_hint.value
            note = FactorResearchNote(**note_data)
            notes.append(note)
            if isinstance(factor_gene_diagnostics, dict):
                self._factor_gene_by_note_id[note.note_id] = factor_gene_diagnostics
            if isinstance(grounding_diagnostics, dict):
                note.status = grounding_diagnostics.get("status", note.status)

        return AlphaResearcherBatch(
            island=self.island,
            notes=notes,
            generation_rationale=data.get("generation_rationale", ""),
        )

    @staticmethod
    def _render_factor_algebra_recipe_into_note(note_data: dict[str, Any]) -> dict[str, Any]:
        rendered_note = dict(note_data)
        recipe_payload = rendered_note.pop("formula_recipe", None)
        if recipe_payload is None:
            recipe_payload = rendered_note.pop("recipe", None)
        if not isinstance(recipe_payload, dict):
            rendered_note["status"] = f"{_FACTOR_ALGEBRA_RECIPE_STATUS_PREFIX}missing_formula_recipe"
            rendered_note["proposed_formula"] = _FACTOR_ALGEBRA_RECIPE_PLACEHOLDER_FORMULA
            return rendered_note

        try:
            recipe = FormulaRecipe(**recipe_payload)
            alignment_error = validate_formula_recipe_alignment(
                recipe,
                hypothesis=str(rendered_note.get("hypothesis") or ""),
                economic_intuition=str(rendered_note.get("economic_intuition") or ""),
                island=str(rendered_note.get("island") or self.island or ""),
            )
            rendered_note["proposed_formula"] = render_formula_recipe(recipe)
            family_gene = build_family_gene(recipe)
            variant_gene = build_variant_gene(recipe)
            rendered_note[_FACTOR_GENE_RUNTIME_FIELD] = {
                "family_gene": family_gene,
                "variant_gene": variant_gene,
                "family_gene_key": build_family_gene_key(family_gene),
                "variant_gene_key": build_variant_gene_key(variant_gene),
            }
            if alignment_error is not None:
                rendered_note["status"] = f"{_FACTOR_ALGEBRA_ALIGNMENT_STATUS_PREFIX}{alignment_error}"
        except Exception as exc:
            rendered_note["status"] = f"{_FACTOR_ALGEBRA_RECIPE_STATUS_PREFIX}{exc}"
            rendered_note["proposed_formula"] = _FACTOR_ALGEBRA_RECIPE_PLACEHOLDER_FORMULA
        return rendered_note

    def _render_grounding_claim_into_note(
        self,
        note_data: dict[str, Any],
        subspace: ExplorationSubspace,
    ) -> dict[str, Any]:
        rendered_note = dict(note_data)
        grounding_payload = rendered_note.pop("grounding_claim", None)
        if not isinstance(grounding_payload, dict):
            rendered_note["status"] = f"{_GROUNDING_STATUS_PREFIX}missing_grounding_claim"
            rendered_note[_GROUNDING_RUNTIME_FIELD] = {"subspace": subspace.value}
            return rendered_note

        try:
            claim = MechanismProxyClaim(**grounding_payload)
            formula = str(rendered_note.get("proposed_formula") or "")
            error = validate_grounding_claim(
                claim,
                subspace=subspace,
                registry=self.registry,
                available_fields=self.capabilities.available_fields,
                formula=formula,
            )
            rendered_note[_GROUNDING_RUNTIME_FIELD] = {
                "subspace": subspace.value,
                "mechanism_source": claim.mechanism_source,
                "proxy_fields": list(claim.proxy_fields),
                "proxy_rationale": claim.proxy_rationale,
                "formula_claim": claim.formula_claim,
                "status": rendered_note.get("status", "draft"),
            }
            if error is not None:
                rendered_note["status"] = f"{_GROUNDING_STATUS_PREFIX}{error}"
                rendered_note[_GROUNDING_RUNTIME_FIELD]["status"] = rendered_note["status"]
        except Exception as exc:
            rendered_note["status"] = f"{_GROUNDING_STATUS_PREFIX}{exc}"
            rendered_note[_GROUNDING_RUNTIME_FIELD] = {
                "subspace": subspace.value,
                "status": rendered_note["status"],
            }
        return rendered_note

    @staticmethod
    def _factor_algebra_recipe_rejection_reason(note: FactorResearchNote) -> str | None:
        status = note.status or ""
        if not status.startswith(_FACTOR_ALGEBRA_RECIPE_STATUS_PREFIX):
            return None
        detail = status.removeprefix(_FACTOR_ALGEBRA_RECIPE_STATUS_PREFIX).strip() or "invalid_formula_recipe"
        return f"FormulaSketch recipe 无效：{detail}"

    @staticmethod
    def _factor_algebra_alignment_rejection_reason(note: FactorResearchNote) -> str | None:
        status = note.status or ""
        if not status.startswith(_FACTOR_ALGEBRA_ALIGNMENT_STATUS_PREFIX):
            return None
        detail = status.removeprefix(_FACTOR_ALGEBRA_ALIGNMENT_STATUS_PREFIX).strip() or "invalid_factor_alignment"
        return f"Factor-algebra alignment 无效：{detail}"

    @staticmethod
    def _grounding_rejection_reason(note: FactorResearchNote) -> str | None:
        status = note.status or ""
        if not status.startswith(_GROUNDING_STATUS_PREFIX):
            return None
        detail = status.removeprefix(_GROUNDING_STATUS_PREFIX).strip() or "invalid_grounding_claim"
        return f"Mechanism grounding 无效：{detail}"

    def _fast_feedback_factor_algebra_policy_rejection_reason(
        self,
        note: FactorResearchNote,
    ) -> str | None:
        if not _is_fast_feedback_profile():
            return None
        if note.exploration_subspace != ExplorationSubspace.FACTOR_ALGEBRA:
            return None
        factor_gene = self._factor_gene_by_note_id.get(note.note_id, {})
        family_key = factor_gene.get("family_gene_key")
        if not isinstance(family_key, str):
            return None
        parts = family_key.split("|")
        if len(parts) < 2:
            return None
        transform_family = parts[1]
        if transform_family in _FAST_FEEDBACK_FACTOR_ALGEBRA_ALLOWED_FAMILIES:
            return None
        allowed = ", ".join(_FAST_FEEDBACK_FACTOR_ALGEBRA_ALLOWED_FAMILIES)
        return (
            "fast_feedback 暂停 "
            f"transform_family={transform_family}; 当前 profile 仅允许 {allowed}"
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

    def _build_factor_algebra_anti_collapse_section(self) -> str:
        """Build a short family-memory prompt to reduce repeated factor_algebra variants."""
        if self.factor_pool is None:
            return ""
        from src.agents.prefilter import NoveltyFilter

        existing: list[dict[str, Any]] = []
        try:
            existing = list(self.factor_pool.get_passed_factors(island=self.island, limit=12))
        except Exception as exc:
            logger.debug("[AlphaResearcher] get_passed_factors failed for anti-collapse: %s", exc)

        if not existing:
            try:
                existing = list(self.factor_pool.get_island_factors(island=self.island, limit=12))
            except Exception as exc:
                logger.debug("[AlphaResearcher] get_island_factors failed for anti-collapse: %s", exc)
                return ""

        family_samples: dict[str, dict[str, Any]] = {}
        for item in existing:
            family_key, variant_key = NoveltyFilter._resolve_factor_gene_keys_from_factor(item)
            if family_key is None:
                continue
            bucket = family_samples.setdefault(
                family_key,
                {
                    "count": 0,
                    "variants": set(),
                    "labels": [],
                },
            )
            label = item.get("factor_id") or item.get("factor_name") or f"family_{len(family_samples)}"
            bucket["count"] += 1
            if isinstance(variant_key, str):
                bucket["variants"].add(variant_key)
            if len(bucket["labels"]) < 2 and str(label) not in bucket["labels"]:
                bucket["labels"].append(str(label))

        low_value_family_counts = self._load_island_low_value_family_counts()

        if not family_samples and not low_value_family_counts:
            return ""

        ranked_families = sorted(
            family_samples.items(),
            key=lambda item: (
                -int(item[1]["count"]),
                -len(item[1]["variants"]),
                item[0],
            ),
        )[:(
            _FAST_FEEDBACK_MAX_ANTI_COLLAPSE_SKELETONS
            if _is_fast_feedback_profile()
            else _MAX_ANTI_COLLAPSE_SKELETONS
        )]

        lines = ["## FACTOR_ALGEBRA Anti-Collapse 提示"]
        if family_samples:
            lines.extend(
                [
                    "- 当前岛上已有一些已占满的 factor_gene family；如果你的新 recipe 只是改 lookback_short/lookback_long/normalization_window/quantile_qscore，请不要提交。",
                    "- 若命中下列 family，请优先改变 base_field、secondary_field、transform_family、interaction_mode 或 normalization_kind。",
                    "- 当前已占满 family 示例：",
                ]
            )
        compact_mode = _is_fast_feedback_profile()
        for idx, (family_key, payload) in enumerate(ranked_families, start=1):
            lines.append(f"  {idx}. {family_key}")
            lines.append(f"     - summary: {_format_family_gene_summary(family_key)}")
            if compact_mode:
                continue
            variants = sorted(payload["variants"])
            if variants:
                lines.append(f"     - seen variants: {', '.join(variants[:3])}")
            if payload["labels"]:
                lines.append(f"     - examples: {', '.join(payload['labels'])}")
        if low_value_family_counts:
            ranked_low_value_families = sorted(
                low_value_family_counts.items(),
                key=lambda item: (-int(item[1]), item[0]),
            )[:(
                _FAST_FEEDBACK_MAX_ANTI_COLLAPSE_SKELETONS
                if _is_fast_feedback_profile()
                else _MAX_ANTI_COLLAPSE_SKELETONS
            )]
            lines.append("- 当前已知低价值 family（多次进入执行后仍因 LOW_SHARPE/弱 IC 被归档）：")
            for idx, (family_key, count) in enumerate(ranked_low_value_families, start=1):
                lines.append(f"  {idx}. {family_key}")
                lines.append(f"     - summary: {_format_family_gene_summary(family_key)}")
                lines.append(
                    "     - warning: "
                    f"historical low-value count={count}; 若无强新机制，不要继续提交同类 generic 变体"
                )
        return "\n".join(lines)

    def _load_island_family_variant_counts(self) -> dict[str, int]:
        """Return historical variant counts grouped by factor_gene family key."""
        if self.factor_pool is None:
            return {}
        from src.agents.prefilter import NoveltyFilter

        existing: list[dict[str, Any]] = []
        try:
            existing = list(self.factor_pool.get_passed_factors(island=self.island, limit=120))
        except Exception as exc:
            logger.debug("[AlphaResearcher] get_passed_factors failed for diversity control: %s", exc)
        if not existing:
            try:
                existing = list(self.factor_pool.get_island_factors(island=self.island, limit=120))
            except Exception as exc:
                logger.debug("[AlphaResearcher] get_island_factors failed for diversity control: %s", exc)
                return {}

        family_to_variants: dict[str, set[str]] = defaultdict(set)
        for item in existing:
            family_key, variant_key = NoveltyFilter._resolve_factor_gene_keys_from_factor(item)
            if not isinstance(family_key, str):
                continue
            if isinstance(variant_key, str):
                family_to_variants[family_key].add(variant_key)
                continue
            fallback = item.get("factor_id") or item.get("formula")
            if isinstance(fallback, str) and fallback:
                family_to_variants[family_key].add(f"__unknown__:{fallback}")
            else:
                family_to_variants[family_key].add("__unknown__")

        return {family_key: len(variants) for family_key, variants in family_to_variants.items()}

    def _load_island_low_value_family_counts(self) -> dict[str, int]:
        """Return low-value factor_algebra family counts grouped by family key."""
        if self.factor_pool is None:
            return {}
        from src.agents.prefilter import NoveltyFilter

        try:
            existing = list(self.factor_pool.get_island_factors(island=self.island, limit=120))
        except Exception as exc:
            logger.debug("[AlphaResearcher] get_island_factors failed for value density: %s", exc)
            return {}

        counts: Counter[str] = Counter()
        for item in existing:
            if item.get("subspace_origin") != ExplorationSubspace.FACTOR_ALGEBRA.value:
                continue
            failure_mode = str(item.get("failure_mode") or "").strip().lower()
            if failure_mode != "low_sharpe":
                continue
            family_key, _variant_key = NoveltyFilter._resolve_factor_gene_keys_from_factor(item)
            if family_key is None:
                formula = item.get("formula")
                if isinstance(formula, str) and formula.strip():
                    family_key = _legacy_low_value_family_key_from_formula(formula)
            if isinstance(family_key, str):
                counts[family_key] += 1
        return dict(counts)

    def _local_prescreen_notes(
        self, notes: list[FactorResearchNote]
    ) -> tuple[list[FactorResearchNote], dict[str, Any]]:
        """Stage 2 本地预筛：复用 Stage 3 的 canonical validator/novelty 规则。"""
        from src.agents.prefilter import NoveltyFilter, Validator

        approved_notes: list[FactorResearchNote] = []
        rejection_counts = Counter()
        rejection_counts_by_filter_and_subspace: dict[str, Counter] = defaultdict(Counter)
        sample_rejections: list[dict[str, str]] = []

        validator = Validator(
            allowed_fields=set(self.capabilities.available_fields),
            approved_operators=set(self.capabilities.approved_operators),
        )
        novelty_filter = NoveltyFilter(pool=self.factor_pool) if self.factor_pool is not None else None
        historical_family_variant_counts = self._load_island_family_variant_counts()
        low_value_family_counts = self._load_island_low_value_family_counts()
        kept_factor_algebra_families: set[str] = set()

        for note in notes:
            recipe_reason = self._factor_algebra_recipe_rejection_reason(note)
            if recipe_reason is not None:
                rejection_counts["validator"] += 1
                subspace = _note_subspace_value(note)
                rejection_counts_by_filter_and_subspace["validator"][subspace] += 1
                if len(sample_rejections) < _MAX_STAGE2_REJECTION_SAMPLES:
                    sample_rejections.append(self._build_stage2_rejection_sample(note, "validator", recipe_reason, subspace))
                continue

            alignment_reason = self._factor_algebra_alignment_rejection_reason(note)
            if alignment_reason is not None:
                rejection_counts["alignment"] += 1
                subspace = _note_subspace_value(note)
                rejection_counts_by_filter_and_subspace["alignment"][subspace] += 1
                if len(sample_rejections) < _MAX_STAGE2_REJECTION_SAMPLES:
                    sample_rejections.append(
                        self._build_stage2_rejection_sample(note, "alignment", alignment_reason, subspace)
                    )
                continue

            grounding_reason = self._grounding_rejection_reason(note)
            if grounding_reason is not None:
                rejection_counts["grounding"] += 1
                subspace = _note_subspace_value(note)
                rejection_counts_by_filter_and_subspace["grounding"][subspace] += 1
                if len(sample_rejections) < _MAX_STAGE2_REJECTION_SAMPLES:
                    sample_rejections.append(self._build_stage2_rejection_sample(note, "grounding", grounding_reason, subspace))
                continue

            passed, reason = validator.validate(note)
            if not passed:
                rejection_counts["validator"] += 1
                subspace = _note_subspace_value(note)
                rejection_counts_by_filter_and_subspace["validator"][subspace] += 1
                if len(sample_rejections) < _MAX_STAGE2_REJECTION_SAMPLES:
                    sample_rejections.append(self._build_stage2_rejection_sample(note, "validator", reason, subspace))
                continue

            subspace = _note_subspace_value(note)
            if subspace == ExplorationSubspace.FACTOR_ALGEBRA.value:
                policy_reason = self._fast_feedback_factor_algebra_policy_rejection_reason(note)
                if policy_reason is not None:
                    rejection_counts["value_density"] += 1
                    rejection_counts_by_filter_and_subspace["value_density"][subspace] += 1
                    if len(sample_rejections) < _MAX_STAGE2_REJECTION_SAMPLES:
                        sample_rejections.append(
                            self._build_stage2_rejection_sample(note, "value_density", policy_reason, subspace)
                        )
                    continue
                factor_gene = self._factor_gene_by_note_id.get(note.note_id, {})
                family_key = factor_gene.get("family_gene_key")
                if isinstance(family_key, str):
                    if family_key in kept_factor_algebra_families:
                        rejection_counts["anti_collapse"] += 1
                        rejection_counts_by_filter_and_subspace["anti_collapse"][subspace] += 1
                        if len(sample_rejections) < _MAX_STAGE2_REJECTION_SAMPLES:
                            sample_rejections.append(
                                self._build_stage2_rejection_sample(
                                    note,
                                    "anti_collapse",
                                    (
                                        "same-batch family budget exceeded: "
                                        f"{family_key} (max kept={_FACTOR_ALGEBRA_BATCH_FAMILY_BUDGET})"
                                    ),
                                    subspace,
                                )
                            )
                        continue
                    historical_count = historical_family_variant_counts.get(family_key, 0)
                    if historical_count >= _FACTOR_ALGEBRA_SATURATED_FAMILY_MIN_VARIANTS:
                        rejection_counts["anti_collapse"] += 1
                        rejection_counts_by_filter_and_subspace["anti_collapse"][subspace] += 1
                        if len(sample_rejections) < _MAX_STAGE2_REJECTION_SAMPLES:
                            sample_rejections.append(
                                self._build_stage2_rejection_sample(
                                    note,
                                    "anti_collapse",
                                    (
                                        "historical saturated family: "
                                        f"{family_key} (variant_count={historical_count} "
                                        f">= {_FACTOR_ALGEBRA_SATURATED_FAMILY_MIN_VARIANTS})"
                                    ),
                                    subspace,
                                )
                            )
                        continue
                    low_value_count = low_value_family_counts.get(family_key, 0)
                    if (
                        _is_fast_feedback_profile()
                        and low_value_count >= _FACTOR_ALGEBRA_LOW_VALUE_FAMILY_MIN_FAILURES
                    ):
                        rejection_counts["value_density"] += 1
                        rejection_counts_by_filter_and_subspace["value_density"][subspace] += 1
                        if len(sample_rejections) < _MAX_STAGE2_REJECTION_SAMPLES:
                            sample_rejections.append(
                                self._build_stage2_rejection_sample(
                                    note,
                                    "value_density",
                                    (
                                        "historical low-value family: "
                                        f"{family_key} (low_sharpe_count={low_value_count} "
                                        f">= {_FACTOR_ALGEBRA_LOW_VALUE_FAMILY_MIN_FAILURES})"
                                    ),
                                    subspace,
                                )
                            )
                        continue

            if novelty_filter is not None:
                passed, reason = novelty_filter.check(note)
                if not passed:
                    rejection_counts["novelty"] += 1
                    rejection_counts_by_filter_and_subspace["novelty"][subspace] += 1
                    if len(sample_rejections) < _MAX_STAGE2_REJECTION_SAMPLES:
                        sample_rejections.append(self._build_stage2_rejection_sample(note, "novelty", reason, subspace))
                    continue

            if subspace == ExplorationSubspace.FACTOR_ALGEBRA.value:
                factor_gene = self._factor_gene_by_note_id.get(note.note_id, {})
                family_key = factor_gene.get("family_gene_key")
                if isinstance(family_key, str):
                    kept_factor_algebra_families.add(family_key)
            approved_notes.append(note)

        return approved_notes, {
            "generated_count": len(notes),
            "delivered_count": len(approved_notes),
            "rejection_counts_by_filter": dict(rejection_counts),
            "rejection_counts_by_filter_and_subspace": {
                filter_name: dict(subspace_counts)
                for filter_name, subspace_counts in rejection_counts_by_filter_and_subspace.items()
            },
            "sample_rejections": sample_rejections,
        }

    def _build_stage2_rejection_sample(
        self,
        note: FactorResearchNote,
        filter_name: str,
        reason: str,
        exploration_subspace: str,
    ) -> dict[str, str]:
        sample: dict[str, str] = {
            "note_id": note.note_id,
            "filter": filter_name,
            "reason": reason,
            "exploration_subspace": exploration_subspace,
        }
        factor_gene = self._factor_gene_by_note_id.get(note.note_id)
        if not factor_gene:
            return sample
        family_gene_key = factor_gene.get("family_gene_key")
        variant_gene_key = factor_gene.get("variant_gene_key")
        if isinstance(family_gene_key, str):
            sample["family_gene_key"] = family_gene_key
        if isinstance(variant_gene_key, str):
            sample["variant_gene_key"] = variant_gene_key
        return sample

    @staticmethod
    def _build_local_rejection_feedback(sample_rejections: list[dict[str, str]]) -> str:
        if not sample_rejections:
            return "本地预筛未通过，但无拒绝样本。请更换思路并避免重复提交已被本地预筛拒绝的模式。"
        lines = []
        hints: list[str] = []
        seen_hints: set[str] = set()
        for idx, item in enumerate(sample_rejections[:3], start=1):
            reason = item.get("reason", "")
            lines.append(f"{idx}. [{item.get('filter', 'unknown')}] {reason}")
        for item in sample_rejections:
            reason = item.get("reason", "")
            reason_lower = reason.lower()
            if "missing_formula_recipe" in reason_lower:
                hint = "- FACTOR_ALGEBRA 必须提供 formula_recipe 对象，不能只给 proposed_formula 字符串。"
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "lookback_short must be smaller than lookback_long" in reason_lower:
                hint = "- 公式窗口必须满足 lookback_short < lookback_long（例如 5 < 20）。"
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "unsupported lookback_short" in reason_lower or "unsupported lookback_long" in reason_lower:
                hint = (
                    "- lookback_short/lookback_long 仅允许固定窗口桶："
                    f"{', '.join(str(v) for v in ALLOWED_WINDOW_BUCKETS)}。"
                )
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "unsupported normalization_window" in reason_lower:
                hint = (
                    "- normalization_window 仅允许固定窗口桶："
                    f"{', '.join(str(v) for v in ALLOWED_WINDOW_BUCKETS)}。"
                )
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "unsupported quantile_qscore" in reason_lower:
                hint = (
                    "- quantile_qscore 仅允许："
                    f"{', '.join(str(v) for v in ALLOWED_QUANTILE_QSCORES)}。"
                )
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "unsupported base_field" in reason_lower or "unsupported secondary_field" in reason_lower:
                hint = (
                    "- factor_algebra 的 base_field/secondary_field 仅允许："
                    f"{_FACTOR_ALGEBRA_ALLOWED_FIELDS_TEXT}；"
                    "不要把 ROE/PB/float_mv/turnover_rate 等字段直接写进 formula_recipe。"
                )
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "相似度过高" in reason and item.get("exploration_subspace") == ExplorationSubspace.FACTOR_ALGEBRA.value:
                hint = "- novelty 命中说明你仍在重复已有 factor_algebra family；不要只改窗口、qscore 或 normalization_window，优先更换 transform_family、base_field 或 interaction_mode。"
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "volume_confirmation requires interaction_mode='mul'" in reason_lower:
                hint = "- 当 transform_family=volume_confirmation 时，interaction_mode 必须为 mul。"
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "mean_spread cannot claim return delta or acceleration" in reason_lower:
                hint = "- mean_spread 只能描述均价/均线差，不要把它写成收益率差、相对收益或动量加速度。"
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "volatility_state cannot claim momentum or return-delta effects" in reason_lower:
                hint = "- volatility_state 只能描述长短期波动状态差，不要把它写成价格动量、收益率变化或趋势延续。"
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "hypothesis mentions normalization but recipe.normalization='none'" in reason_lower:
                hint = "- 如果 hypothesis 说标准化/归一化，就必须在 recipe 中显式使用 rank 或 quantile normalization。"
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "hypothesis mentions volume/liquidity but recipe has no volume proxy" in reason_lower:
                hint = "- 如果 hypothesis 说量价或流动性确认，recipe 必须实际使用 $volume 或 $amount。"
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "volume_confirmation must explicitly mention a volume/liquidity confirmation mechanism" in reason_lower:
                hint = (
                    "- transform_family=volume_confirmation 时，hypothesis/economic_intuition 必须明确说明成交量或流动性确认机制；"
                    "建议直接写成“短期价格均值差由成交量/金额差值确认”。"
                )
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "volume_confirmation must describe a price-spread signal confirmed by volume/liquidity spread" in reason_lower:
                hint = (
                    "- volume_confirmation 必须明确写成“价格均值差/价差”由“成交量或流动性差值”确认；"
                    "可直接使用“短期价格均值差在成交量差值配合下更可靠”这类表述。"
                )
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "volume_confirmation cannot claim relative volume change" in reason_lower:
                hint = "- 目前的 volume_confirmation 表达的是量价差值确认，不要写成相对成交量变化或量能比。"
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "volume_confirmation cannot claim momentum, trend continuation, or return-delta effects" in reason_lower:
                hint = (
                    "- volume_confirmation 只能描述量价差值/流动性确认，不要写成动量、趋势延续或收益率变化；"
                    "改写为“价格均值差由成交量/金额差值确认”，不要出现‘动量’或‘趋势延续’。"
                )
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "ratio_momentum should not be described as a mean spread" in reason_lower:
                hint = "- ratio_momentum 应描述相对强弱或比值动量，不要写成均线差或价差。"
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "ratio_momentum on momentum island must describe a comparative relative-strength mechanism" in reason_lower:
                hint = "- momentum island 下的 ratio_momentum 不能只写成泛化动量或趋势延续；必须明确说明相对强弱、比值比较或短强长弱机制。"
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "missing_grounding_claim" in reason_lower:
                hint = "- CROSS_MARKET / NARRATIVE_MINING 必须提供 grounding_claim 对象，不能只给自由 hypothesis 和公式。"
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "unsupported mechanism_source" in reason_lower:
                hint = "- mechanism_source 必须选择当前上下文里明确列出的机制模板名或叙事类别名。"
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "unsupported proxy_fields" in reason_lower:
                hint = "- proxy_fields 必须全部来自当前运行时可用字段列表，不要猜测外部字段。"
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
            if "formula does not use declared proxy_fields" in reason_lower:
                hint = "- proposed_formula 必须实际使用 grounding_claim.proxy_fields 中至少一个字段。"
                if hint not in seen_hints:
                    hints.append(hint)
                    seen_hints.add(hint)
        if hints:
            lines.append("针对本轮拒绝样本，请按下列结构化约束修正：")
            lines.extend(hints)
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

    # 展开：每个 batch 包含目标数量个 notes，汇总为一个大列表
    all_notes: list[FactorResearchNote] = []
    subspace_results: dict[ExplorationSubspace, list[int, int]] = {
        s: [0, 0] for s in ExplorationSubspace
    }
    stage2_rejection_counts = Counter()
    stage2_rejection_counts_by_filter_and_subspace: dict[str, Counter] = defaultdict(Counter)
    stage2_sample_rejections: list[dict[str, Any]] = []
    stage2_factor_gene_by_note_id: dict[str, dict[str, Any]] = {}
    stage2_non_factor_note_ids: set[str] = set()
    stage2_factor_note_entries: list[dict[str, Any]] = []
    stage2_sample_rejections_by_researcher: list[list[Any]] = []
    stage2_generated_count = 0
    stage2_delivered_count = 0
    stage2_retry_count = 0

    for researcher_idx, ((island, subspace), researcher, batch) in enumerate(zip(assignments, researchers, batches)):
        diagnostics = researcher.last_generation_diagnostics or {}
        stage2_generated_count += int(diagnostics.get("generated_count", 0))
        stage2_delivered_count += int(diagnostics.get("delivered_count", 0))
        stage2_retry_count += int(diagnostics.get("local_retry_count", 0))
        stage2_rejection_counts.update(diagnostics.get("rejection_counts_by_filter", {}))
        for filter_name, subspace_counts in diagnostics.get("rejection_counts_by_filter_and_subspace", {}).items():
            if isinstance(subspace_counts, dict):
                stage2_rejection_counts_by_filter_and_subspace[filter_name].update(subspace_counts)
        sample_rejections = diagnostics.get("sample_rejections", [])
        if not isinstance(sample_rejections, list):
            sample_rejections = []
        stage2_sample_rejections_by_researcher.append(sample_rejections)

        if isinstance(batch, Exception):
            logger.warning("AlphaResearcher[%s/%s] 失败（跳过）: %s", island, subspace.value, batch)
        else:
            factor_gene_diagnostics = diagnostics.get(_FACTOR_GENE_DIAGNOSTICS_KEY)
            if not isinstance(factor_gene_diagnostics, dict):
                factor_gene_diagnostics = {}
            for note in batch.notes:
                source_note_id = note.note_id
                factor_gene_payload = factor_gene_diagnostics.get(source_note_id)
                if isinstance(factor_gene_payload, dict):
                    stage2_factor_note_entries.append(
                        {
                            "researcher_idx": researcher_idx,
                            "source_note_id": source_note_id,
                            "note": note,
                            "factor_gene_payload": factor_gene_payload,
                        }
                    )
                elif isinstance(source_note_id, str):
                    stage2_non_factor_note_ids.add(source_note_id)
                all_notes.append(note)
            subspace_results[subspace][0] += len(batch.notes)  # generated

    stage2_factor_note_id_remap_by_researcher: dict[int, dict[str, list[dict[str, str | None]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    occupied_note_ids = set(stage2_non_factor_note_ids)
    for item in stage2_factor_note_entries:
        note = item["note"]
        source_note_id = item["source_note_id"]
        factor_gene_payload = item["factor_gene_payload"]
        final_note_id = _make_unique_note_id(
            source_note_id,
            used_note_ids=occupied_note_ids,
            fallback_prefix=f"{note.island}_{_today_str()}",
        )
        if final_note_id != source_note_id:
            note.note_id = final_note_id
        occupied_note_ids.add(final_note_id)
        stage2_factor_gene_by_note_id[final_note_id] = factor_gene_payload
        identity = _factor_gene_identity(factor_gene_payload)
        if identity is not None:
            family_key, variant_key = identity
            stage2_factor_note_id_remap_by_researcher[item["researcher_idx"]][source_note_id].append(
                {
                    "family_gene_key": family_key,
                    "variant_gene_key": variant_key,
                    "final_note_id": final_note_id,
                }
            )

    for researcher_idx, sample_rejections in enumerate(stage2_sample_rejections_by_researcher):
        note_id_remap = stage2_factor_note_id_remap_by_researcher.get(researcher_idx, {})
        for item in sample_rejections:
            if len(stage2_sample_rejections) >= _MAX_STAGE2_REJECTION_SAMPLES:
                break
            if not isinstance(item, dict):
                stage2_sample_rejections.append(item)
                continue
            mapped_item = item
            sample_note_id = item.get("note_id")
            has_factor_gene_keys = isinstance(item.get("family_gene_key"), str) or isinstance(
                item.get("variant_gene_key"), str
            )
            if has_factor_gene_keys and isinstance(sample_note_id, str) and sample_note_id in note_id_remap:
                candidates = note_id_remap[sample_note_id]
                for candidate in candidates:
                    if _sample_matches_factor_gene_identity(
                        item,
                        family_key=str(candidate["family_gene_key"]),
                        variant_key=(candidate["variant_gene_key"] if isinstance(candidate["variant_gene_key"], str) else None),
                    ):
                        mapped_item = dict(item)
                        mapped_item["note_id"] = str(candidate["final_note_id"])
                        break
            stage2_sample_rejections.append(mapped_item)

    logger.info(
        "Stage 2 生成 %d 个候选（%d 个任务，%d 个 Island）",
        len(all_notes), len(assignments), len(active_islands),
    )

    # Bridge：将 FactorResearchNote 转换为 Hypothesis + StrategySpec
    hypotheses: list[Hypothesis] = [note.to_hypothesis() for note in all_notes]
    strategy_specs: list[StrategySpec] = [note.to_strategy_spec() for note in all_notes]

    stage2_diagnostics = {
        "generated_count": stage2_generated_count,
        "delivered_count": stage2_delivered_count,
        "local_retry_count": stage2_retry_count,
        "rejection_counts_by_filter": dict(stage2_rejection_counts),
        "rejection_counts_by_filter_and_subspace": {
            filter_name: dict(subspace_counts)
            for filter_name, subspace_counts in stage2_rejection_counts_by_filter_and_subspace.items()
        },
        "sample_rejections": stage2_sample_rejections,
    }
    if stage2_factor_gene_by_note_id:
        stage2_diagnostics[_FACTOR_GENE_DIAGNOSTICS_KEY] = stage2_factor_gene_by_note_id

    return {
        "research_notes": all_notes,
        "hypotheses": hypotheses,
        "strategy_specs": strategy_specs,
        "scheduler_state": scheduler_state.model_dump(),
        "subspace_generated": {s.value: v[0] for s, v in subspace_results.items()},
        "stage2_diagnostics": stage2_diagnostics,
    }


def hypothesis_gen_node(state: dict) -> HypothesisGenOutput:
    """LangGraph 同步入口。"""
    return asyncio.run(_hypothesis_gen_async(state))
