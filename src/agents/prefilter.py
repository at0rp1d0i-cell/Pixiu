"""
Pixiu v2 Stage 3：前置过滤层（PreFilter）

四重串联过滤器，在进入昂贵 Qlib 回测（Stage 4b）之前
低成本筛除劣质候选，最多放行 THRESHOLDS.stage3_top_k 个。

过滤器：
  A - Validator         ：A 股硬约束（字段白名单、Ref 方向、Log 安全、算子白名单）
  B - NoveltyFilter     ：AST Token Jaccard 相似度，防重复探索
  C - AlignmentChecker  ：LLM 快速调用，检验公式与经济假设语义一致性
  D - ConstraintChecker ：历史失败约束检查，拦截已知硬约束模式

参考设计：docs/design/stage-3-prefilter.md
"""
import asyncio
import json
import logging
import re
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.formula.capabilities import FormulaCapabilities, get_runtime_formula_capabilities
from src.schemas.research_note import FactorResearchNote
from src.schemas.thresholds import THRESHOLDS
from src.factor_pool.pool import FactorPool
from src.llm.openai_compat import build_researcher_llm
from src.schemas.stage_io import PrefilterDiagnostics, PrefilterOutput
from src.skills.loader import SkillLoader
from src.schemas.market_context import MarketRegime

logger = logging.getLogger(__name__)

_SKILL_LOADER = SkillLoader()
_MAX_REJECTION_SAMPLES = 5

_STRICT_ARITY_BY_NAME: dict[str, int] = {
    "Ref": 2,
    "Mean": 2,
    "Std": 2,
    "Var": 2,
    "Max": 2,
    "Min": 2,
    "Sum": 2,
    "Delta": 2,
    "Slope": 2,
    "Rsquare": 2,
    "Resi": 2,
    "Power": 2,
    "Corr": 3,
    "Cov": 3,
    "If": 3,
    "Gt": 2,
    "Lt": 2,
    "Ge": 2,
    "Le": 2,
    "Eq": 2,
    "Ne": 2,
    "And": 2,
    "Or": 2,
    "Not": 1,
    "Add": 2,
    "Sub": 2,
    "Mul": 2,
    "Div": 2,
    "IdxMax": 2,
    "IdxMin": 2,
    "Comb": 2,
    "Count": 2,
    "Mad": 2,
    "WMA": 2,
    "EMA": 2,
    "Ts_Mean": 2,
    "Ts_Std": 2,
    "Ts_Max": 2,
    "Ts_Min": 2,
    "Ts_Sum": 2,
    "Ts_Rank": 2,
    "Ts_Corr": 3,
    "Ts_Cov": 3,
    "Ts_WMA": 2,
    "Ts_Slope": 2,
    "SignedPower": 2,
    "Greater": 2,
    "Less": 2,
    "Rank": 1,
    "Abs": 1,
    "Sign": 1,
    "Log": 1,
    "Sqrt": 1,
}

_TWO_EXPRESSIONS_THEN_WINDOW = {"Corr", "Cov", "Ts_Corr", "Ts_Cov"}
_WINDOW_OPERATORS = {
    "Ref",
    "Mean",
    "Std",
    "Var",
    "Max",
    "Min",
    "Sum",
    "Delta",
    "Slope",
    "Rsquare",
    "Resi",
    "Power",
    "WMA",
    "EMA",
    "Ts_Mean",
    "Ts_Std",
    "Ts_Max",
    "Ts_Min",
    "Ts_Sum",
    "Ts_Rank",
    "Ts_WMA",
    "Ts_Slope",
    "SignedPower",
    "Count",
    "Mad",
    "IdxMax",
    "IdxMin",
    "Greater",
    "Less",
}
_BOOLEAN_LITERALS = {"True", "False"}
_LEGACY_REGIME_MAP = {
    "trending_up": MarketRegime.BULL_TREND.value,
    "trending_down": MarketRegime.BEAR_TREND.value,
    "sideways": MarketRegime.RANGE_BOUND.value,
    "volatile": MarketRegime.HIGH_VOLATILITY.value,
    "unknown": MarketRegime.RANGE_BOUND.value,
}
_KNOWN_REGIMES = {regime.value for regime in MarketRegime}


# ─────────────────────────────────────────────────────────
# Filter A：Validator（A 股硬约束，扩展自 v1 validator.py）
# ─────────────────────────────────────────────────────────

class Validator:
    """Filter A: A 股 Qlib 公式硬约束检查。"""

    def __init__(
        self,
        allowed_fields: Optional[set[str]] = None,
        approved_operators: Optional[set[str]] = None,
    ):
        capabilities = None
        if allowed_fields is None or approved_operators is None:
            capabilities = get_runtime_formula_capabilities()
        self.allowed_fields = allowed_fields or set(capabilities.available_fields)
        self.approved_operators = approved_operators or set(capabilities.approved_operators)

    # 数学常数 → 数值替换（LLM 常生成裸 e / pi，qlib 不识别）
    _MATH_CONSTANTS = {"e": "2.71828", "pi": "3.14159"}

    @staticmethod
    def _normalize_formula(formula: str) -> str:
        """将公式中的数学常数替换为数值字面量。"""
        for name, value in Validator._MATH_CONSTANTS.items():
            formula = re.sub(rf'(?<!\$)\b{name}\b(?!\w|\()', value, formula)
        return formula

    def validate(self, note: FactorResearchNote) -> tuple[bool, str]:
        """返回 (passed: bool, reason: str)"""
        formula = note.final_formula or note.proposed_formula

        # 规则 0：数学常数归一化
        if formula:
            normalized = self._normalize_formula(formula)
            if normalized != formula:
                if note.final_formula:
                    note.final_formula = normalized
                else:
                    note.proposed_formula = normalized
                formula = normalized

        # 规则 1：公式非空且长度合理
        if not formula or not (5 < len(formula) < 500):
            return False, f"公式长度不合法（len={len(formula)}，要求 5-500）"

        # 规则 2：括号匹配
        if formula.count("(") != formula.count(")"):
            return False, "括号不匹配（(数量 ≠ )数量）"
        if formula.count("[") != formula.count("]"):
            return False, "方括号不匹配（[数量 ≠ ]数量）"

        # 规则 3：Ref() 偏移符号（Ref($close, -N) 是未来数据）
        # 正确形式：Ref($close, N)，N > 0
        for m in re.finditer(r'Ref\s*\([^,]+,\s*([-\d]+)\s*\)', formula):
            offset_str = m.group(1).strip()
            try:
                offset = int(offset_str)
                if offset <= 0:
                    return False, f"Ref() 偏移量必须为正整数，当前值={offset}（负值等于使用未来数据）"
            except ValueError:
                pass

        # 规则 4 - 7：基于 Qlib 原生 AST 的深度解析与语义校验
        from src.formula.semantic import parse_and_check_ast, MathSafetyError
        try:
            invalid_ops, invalid_fields, bare_identifiers = parse_and_check_ast(
                formula, self.approved_operators, self.allowed_fields
            )
            if invalid_fields:
                return False, f"使用了未注册字段：{invalid_fields}"
            if invalid_ops:
                return False, f"使用了未批准的算子：{invalid_ops}"
            if bare_identifiers:
                return False, f"使用了未知标识符：{bare_identifiers}"
        except ValueError as e:
            return False, f"语法或参数错误 (Syntax/Arity Error)：{e}"
        except MathSafetyError as e:
            return False, f"数学安全约束不通过 (Math Safety Domain)：{e}"

        return True, "通过语法硬约束"


# ─────────────────────────────────────────────────────────
# Filter B：NoveltyFilter（新颖性过滤，AST Jaccard 相似度）
# ─────────────────────────────────────────────────────────

class NoveltyFilter:
    """Filter B: 防止重复探索已有因子。

    使用 Token 集合 Jaccard 相似度与 FactorPool 历史因子对比。
    threshold: 相似度超过此值则认为是重复因子（默认从 THRESHOLDS 读取）
    """

    def __init__(self, pool: FactorPool, threshold: Optional[float] = None):
        self.pool = pool
        self.threshold = threshold if threshold is not None else THRESHOLDS.min_novelty_threshold

    def check(self, note: FactorResearchNote) -> tuple[bool, str]:
        formula = note.final_formula or note.proposed_formula
        tokens_new = self._tokenize(formula)

        # 从 FactorPool 获取同 Island 的历史因子
        existing = self.pool.get_island_factors(island=note.island, limit=50)

        for existing_factor in existing:
            existing_formula = existing_factor.get("formula", "")
            if not existing_formula:
                continue
            tokens_existing = self._tokenize(existing_formula)
            similarity = self._jaccard(tokens_new, tokens_existing)
            if similarity > self.threshold:
                return False, (
                    f"与已有因子 {existing_factor.get('factor_id', '?')} 相似度过高 "
                    f"({similarity:.2f} > {self.threshold})，"
                    f"已有因子：{existing_formula[:80]}"
                )

        return True, "通过新颖性检查"

    def _tokenize(self, formula: str) -> set:
        """将 Qlib 公式分解为 token 集合。
        例：Mean(Abs($close/Ref($close,1)-1), 20) → {"Mean","Abs","$close","Ref","1","20"}
        """
        return set(re.findall(r'\$\w+|[A-Za-z]+|\d+', formula))

    def _jaccard(self, a: set, b: set) -> float:
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)


# ─────────────────────────────────────────────────────────
# Filter C：AlignmentChecker（语义一致性，LLM 快速调用）
# ─────────────────────────────────────────────────────────

ALIGNMENT_PROMPT = """你是量化因子审核员。判断以下因子的经济假设与公式是否一致。

假设：{hypothesis}
公式：{formula}

判断标准：
- 公式的计算逻辑是否能捕捉假设描述的市场现象？
- 公式的时间窗口和操作符是否与假设的持仓周期/观测窗口匹配？

只输出 JSON，不输出其他内容：
{{"aligned": true/false, "reason": "一句话说明"}}
"""

ALIGNMENT_SYSTEM_PROMPT = """你是 Pixiu 的 Stage 3 预过滤审核员。

你的任务是快速判断研究假设与公式表达是否语义一致。
严格遵守 A 股领域约束和过滤规则，只输出 JSON，不输出额外解释。
"""


class AlignmentChecker:
    """Filter C: LLM 快速调用，检验公式与经济假设语义一致性。
    失败时放行（不因辅助检查阻塞主流程）。
    """

    def __init__(self, skill_loader: Optional[SkillLoader] = None):
        self.llm = build_researcher_llm(profile="alignment_checker")
        self.skill_loader = skill_loader or _SKILL_LOADER

    async def check(self, note: FactorResearchNote) -> tuple[bool, str]:
        formula = note.final_formula or note.proposed_formula
        prompt = ALIGNMENT_PROMPT.format(
            hypothesis=note.hypothesis[:300],
            formula=formula,
        )
        system_content = ALIGNMENT_SYSTEM_PROMPT
        skill_context = self.skill_loader.load_for_agent("prefilter")
        if skill_context:
            system_content = (
                system_content + "\n\n## 过滤规范\n\n" + skill_context
            )
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=system_content),
                HumanMessage(content=prompt),
            ])
            # 提取 JSON
            m = re.search(r'\{.*\}', response.content, re.DOTALL)
            if not m:
                return True, "AlignmentChecker 解析失败，放行"
            result = json.loads(m.group())
            return result["aligned"], result.get("reason", "")
        except Exception as e:
            # AlignmentChecker 失败时放行（不因辅助检查阻塞主流程）
            logger.warning("[AlignmentChecker] 调用失败，放行: %s", e)
            return True, f"AlignmentChecker 调用失败，跳过：{e}"


# ─────────────────────────────────────────────────────────
# Filter D：ConstraintChecker（结构化失败约束检查）
# ─────────────────────────────────────────────────────────

class ConstraintChecker:
    """Filter D: 检查候选公式是否匹配已知失败约束（hard 级别）。

    失败时降级（不阻塞主链）：若 FactorPool 不可用，直接放行。
    """

    def __init__(self, pool: FactorPool):
        self.pool = pool

    def check(self, note: FactorResearchNote) -> tuple[bool, str]:
        """返回 (passed: bool, reason: str)。"""
        try:
            constraints = self.pool.query_constraints(
                island=note.island,
                limit=20,
            )
            hard_constraints = [c for c in constraints if c.severity == "hard"]

            formula = note.final_formula or note.proposed_formula
            for constraint in hard_constraints:
                matched = self._matches_pattern(formula, constraint.formula_pattern)
                try:
                    if matched:
                        self.pool.increment_violation(constraint.constraint_id)
                    else:
                        self.pool.increment_checked(constraint.constraint_id)
                except Exception:
                    pass  # 计数失败不阻塞判断
                if matched:
                    return False, f"Matches failure pattern: {constraint.constraint_rule}"
        except Exception as e:
            # ConstraintChecker 失败时放行，不阻塞主链
            logger.warning("[ConstraintChecker] 调用失败，放行: %s", e)
            return True, f"ConstraintChecker 调用失败，跳过：{e}"

        return True, "No known failure patterns matched"

    def _matches_pattern(self, formula: str, pattern: str) -> bool:
        """判断公式是否匹配已知失败模式。

        策略：
        1. 将 formula 中的数值规范化为 N_SHORT/N_MID/N_LONG，再与 pattern 精确比较。
        2. 将 pattern 中的占位符替换为对应范围的 regex，做局部匹配。

        N_SHORT = 1-10，N_MID = 11-59，N_LONG = 60+
        也支持旧版 N 占位符（兼容未迁移的约束记录）。
        """
        if not formula or not pattern:
            return False

        def _classify(m: re.Match) -> str:
            n = int(m.group())
            if n <= 10:
                return "N_SHORT"
            elif n < 60:
                return "N_MID"
            else:
                return "N_LONG"

        # 方法一：规范化 formula 后与 pattern 精确比较
        normalized = re.sub(r'\b\d+\b', _classify, formula)
        if normalized == pattern:
            return True

        # 方法二：将 pattern 占位符转换为对应 regex，做局部匹配
        # 支持三档占位符以及旧版 N（向后兼容）
        _PLACEHOLDER_REGEX = {
            "N_SHORT": r"([1-9]|10)",
            "N_MID": r"([1-5][0-9])",
            "N_LONG": r"([6-9][0-9]|[1-9][0-9]{2,})",
            "N": r"\d+",  # legacy fallback
        }
        try:
            escaped = re.escape(pattern)
            # Replace placeholders longest-first to avoid partial replacement
            for placeholder in ("N_SHORT", "N_MID", "N_LONG", "N"):
                escaped = escaped.replace(re.escape(placeholder), _PLACEHOLDER_REGEX[placeholder])
            if re.search(escaped, formula):
                return True
        except re.error:
            pass

        return False


# ─────────────────────────────────────────────────────────
# Filter E：RegimeFilter（Regime 适用性过滤）
# ─────────────────────────────────────────────────────────

class RegimeFilter:
    """Filter E: 检查候选因子是否在当前市场 regime 下有效。

    若 note.invalid_regimes 包含当前 regime（字符串值），则拒绝该 note。
    当 current_regime 为 None 时直接放行（无上下文时不阻塞流程）。
    """

    def check(
        self,
        note: FactorResearchNote,
        current_regime: Optional[str],
    ) -> tuple[bool, str]:
        """返回 (passed: bool, reason: str)。

        Args:
            note: 候选因子研究笔记
            current_regime: 当前市场 regime 的字符串值（如 "bull_trend"），
                            为 None 时直接放行
        """
        if not current_regime:
            return True, "无当前 regime 上下文，跳过 regime 过滤"
        current = self._normalize_regime(current_regime)
        if current is None:
            return False, f"当前 regime 非法或未知：{current_regime}"

        applicable_regimes, invalid_applicable = self._normalize_regime_list(note.applicable_regimes)
        invalid_regimes, invalid_invalid = self._normalize_regime_list(note.invalid_regimes)
        invalid_labels = sorted(set(invalid_applicable + invalid_invalid))
        if invalid_labels:
            return False, f"包含未知 regime 标签：{invalid_labels}"

        if not applicable_regimes and not invalid_regimes:
            return False, "必须至少声明 applicable_regimes 或 invalid_regimes 之一"

        if applicable_regimes and current not in applicable_regimes:
            return False, f"当前 regime {current} 不在 applicable_regimes 中"

        if current in invalid_regimes:
            return False, f"Factor invalid in current regime: {current}"

        return True, f"当前 regime {current} 通过适用性检查"

    @staticmethod
    def _normalize_regime(regime: str) -> str | None:
        value = _LEGACY_REGIME_MAP.get(regime, regime)
        return value if value in _KNOWN_REGIMES else None

    def _normalize_regime_list(self, regimes: list[str]) -> tuple[list[str], list[str]]:
        normalized: list[str] = []
        invalid: list[str] = []
        for regime in regimes:
            value = self._normalize_regime(regime)
            if value is None:
                invalid.append(regime)
                continue
            if value not in normalized:
                normalized.append(value)
        return normalized, invalid


# ─────────────────────────────────────────────────────────
# PreFilter：组合执行四重过滤器
# ─────────────────────────────────────────────────────────

class PreFilter:
    """Stage 3 四重过滤器组合执行器。"""

    def __init__(
        self,
        factor_pool: FactorPool,
        validator: Optional[Validator] = None,
        capabilities: Optional[FormulaCapabilities] = None,
    ):
        self.capabilities = capabilities or get_runtime_formula_capabilities()
        self.validator = validator or Validator(
            allowed_fields=set(self.capabilities.available_fields),
            approved_operators=set(self.capabilities.approved_operators),
        )
        self.novelty = NoveltyFilter(pool=factor_pool, threshold=THRESHOLDS.min_novelty_threshold)
        self.alignment = AlignmentChecker()
        self.constraint_checker = ConstraintChecker(pool=factor_pool)
        self.regime_filter = RegimeFilter()
        self.last_diagnostics: PrefilterDiagnostics = {
            "input_count": 0,
            "approved_count": 0,
            "rejection_counts_by_filter": {},
            "sample_rejections": [],
        }

    def _reset_diagnostics(self, input_count: int) -> None:
        self.last_diagnostics = {
            "input_count": input_count,
            "approved_count": 0,
            "rejection_counts_by_filter": {},
            "sample_rejections": [],
        }

    def _record_rejection(self, note: FactorResearchNote, filter_name: str, reason: str) -> None:
        counts = self.last_diagnostics.setdefault("rejection_counts_by_filter", {})
        counts[filter_name] = counts.get(filter_name, 0) + 1

        samples = self.last_diagnostics.setdefault("sample_rejections", [])
        if len(samples) < _MAX_REJECTION_SAMPLES:
            samples.append({
                "note_id": note.note_id,
                "filter": filter_name,
                "reason": reason,
            })

    def _record_top_k_truncation(self, notes: list[FactorResearchNote]) -> None:
        for note in notes:
            self._record_rejection(
                note,
                "top_k_truncation",
                f"ranked below stage3_top_k={THRESHOLDS.stage3_top_k}",
            )

    async def filter_batch(
        self,
        notes: list[FactorResearchNote],
        current_regime: str | None = None,
    ) -> tuple[list[FactorResearchNote], int]:
        """
        五重过滤（Filter A/B/C/D/E），返回 (approved_notes, filtered_count)。
        approved_notes 数量 <= THRESHOLDS.stage3_top_k
        """
        self._reset_diagnostics(len(notes))
        
        async def _check_note(note: FactorResearchNote) -> tuple[FactorResearchNote, str, str]:
            # Filter A (同步)
            passed, reason = self.validator.validate(note)
            if not passed: return note, "validator", reason

            # Filter B (同步)
            passed, reason = self.novelty.check(note)
            if not passed: return note, "novelty", reason

            # Filter C (异步 LLM)
            passed, reason = await self.alignment.check(note)
            if not passed: return note, "alignment", reason

            # Filter D (同步)
            passed, reason = self.constraint_checker.check(note)
            if not passed: return note, "constraint_checker", reason

            # Filter E (同步)
            passed, reason = self.regime_filter.check(note, current_regime)
            if not passed: return note, "regime_filter", reason

            return note, "passed", ""

        # 并行执行所有 note 的检查
        tasks = [_check_note(note) for note in notes]
        results = await asyncio.gather(*tasks)

        candidates = []
        for note, status, reason in results:
            if status == "passed":
                candidates.append(note)
            else:
                # 按照原先的 log 风格: [Filter A] 拒绝 ...
                filter_num_map = {
                    "validator": "Filter A",
                    "novelty": "Filter B",
                    "alignment": "Filter C",
                    "constraint_checker": "Filter D",
                    "regime_filter": "Filter E"
                }
                filter_label = filter_num_map.get(status, status)
                logger.info("[%s] 拒绝 %s: %s", filter_label, note.note_id, reason)
                self._record_rejection(note, status, reason)

        # 通过数量 > Top K 时，按探索需求排序（有 exploration_questions 的排后，先回测简单的）
        candidates.sort(key=lambda n: len(n.exploration_questions))
        approved = candidates[:THRESHOLDS.stage3_top_k]
        overflow = candidates[THRESHOLDS.stage3_top_k:]
        if overflow:
            self._record_top_k_truncation(overflow)
        filtered_count = len(notes) - len(approved)
        self.last_diagnostics["approved_count"] = len(approved)

        logger.info(
            "[Stage 3] %d 个候选 → %d 个通过（淘汰 %d 个）",
            len(notes), len(approved), filtered_count,
        )
        return approved, filtered_count


# ─────────────────────────────────────────────────────────
# LangGraph 节点
# ─────────────────────────────────────────────────────────

def prefilter_node(state: dict) -> PrefilterOutput:
    """LangGraph Stage 3 同步入口。"""
    from src.factor_pool.pool import get_factor_pool

    notes: list[FactorResearchNote] = state.get("research_notes", [])
    pool = get_factor_pool()
    prefilter = PreFilter(factor_pool=pool)

    # 从 state 中提取当前 regime（若有）
    market_context = state.get("market_context")
    current_regime: str | None = None
    if market_context is not None:
        regime = getattr(market_context, "market_regime", None)
        if regime is not None:
            current_regime = regime.value if hasattr(regime, "value") else str(regime)

    approved, filtered_count = asyncio.run(
        prefilter.filter_batch(notes, current_regime=current_regime)
    )

    logger.info(
        "[Prefilter Node] %d → %d approved, %d filtered (regime=%s)",
        len(notes), len(approved), filtered_count, current_regime,
    )
    return {
        "approved_notes": approved,
        "filtered_count": filtered_count,
        "prefilter_diagnostics": prefilter.last_diagnostics,
    }
