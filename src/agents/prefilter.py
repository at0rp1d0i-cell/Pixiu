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
import os
import re
from typing import Optional

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from src.schemas.research_note import FactorResearchNote
from src.schemas.thresholds import THRESHOLDS
from src.factor_pool.pool import FactorPool
from src.schemas.stage_io import PrefilterOutput

logger = logging.getLogger(__name__)


def _load_dotenv_if_available():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


_load_dotenv_if_available()


# ─────────────────────────────────────────────────────────
# Filter A：Validator（A 股硬约束，扩展自 v1 validator.py）
# ─────────────────────────────────────────────────────────

_BASE_FIELDS = {
    "$close", "$open", "$high", "$low", "$volume", "$factor", "$amount", "$vwap",
}

_FUNDAMENTAL_FIELDS = {
    "$pe_ttm", "$pb", "$roe", "$revenue_yoy", "$profit_yoy",
    "$turnover_rate", "$float_mv",
}

FUNDAMENTAL_FIELDS_ENABLED = os.getenv("FUNDAMENTAL_FIELDS_ENABLED", "false").lower() == "true"

APPROVED_FIELDS = _BASE_FIELDS | (_FUNDAMENTAL_FIELDS if FUNDAMENTAL_FIELDS_ENABLED else set())

APPROVED_OPERATORS = {
    "Mean", "Std", "Var", "Max", "Min", "Sum",
    "Ref", "Delta", "Slope", "Rsquare", "Resi",
    "Rank", "Abs", "Sign",
    "Log", "Power", "Sqrt",
    "Corr", "Cov",
    "If", "Gt", "Lt", "Ge", "Le", "Eq", "Ne",
    "And", "Or", "Not",
    "Add", "Sub", "Mul", "Div",
    "IdxMax", "IdxMin", "Comb", "Count", "Mad",
    "WMA", "EMA",
    # qlib Ts_* 时序算子
    "Ts_Mean", "Ts_Std", "Ts_Max", "Ts_Min", "Ts_Sum",
    "Ts_Rank", "Ts_Corr", "Ts_Cov", "Ts_WMA", "Ts_Slope",
    # 其他合法 qlib 算子
    "SignedPower", "Greater", "Less",
}


class Validator:
    """Filter A: A 股 Qlib 公式硬约束检查。"""

    def validate(self, note: FactorResearchNote) -> tuple[bool, str]:
        """返回 (passed: bool, reason: str)"""
        formula = note.final_formula or note.proposed_formula

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

        # 规则 4：字段名合法性
        used_fields = set(re.findall(r'\$\w+', formula))
        invalid_fields = used_fields - APPROVED_FIELDS
        if invalid_fields:
            return False, f"使用了未注册字段：{invalid_fields}"

        # 规则 5：算子白名单
        used_operators = set(re.findall(r'\b([A-Za-z][A-Za-z0-9]*)\s*\(', formula))
        invalid_ops = used_operators - APPROVED_OPERATORS
        if invalid_ops:
            return False, f"使用了未批准的算子：{invalid_ops}"

        # 规则 6：Log() 安全性（Log 参数需有 +1 或类似保护）
        log_match = re.search(r'\bLog\s*\(([^)]+)\)', formula)
        if log_match:
            inner = log_match.group(1)
            if '+' not in inner and 'Abs' not in inner:
                return False, f"Log() 参数未添加 +1 或 Abs 保护，可能导致 Log(0) 错误：{inner}"

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


class AlignmentChecker:
    """Filter C: LLM 快速调用，检验公式与经济假设语义一致性。
    失败时放行（不因辅助检查阻塞主流程）。
    """

    def __init__(self):
        self.llm = ChatOpenAI(
            model=os.getenv("RESEARCHER_MODEL", "deepseek-chat"),
            base_url=os.getenv("RESEARCHER_BASE_URL"),
            api_key=os.getenv("RESEARCHER_API_KEY"),
            temperature=0,
            max_tokens=200,  # 输出很短
        )

    async def check(self, note: FactorResearchNote) -> tuple[bool, str]:
        formula = note.final_formula or note.proposed_formula
        prompt = ALIGNMENT_PROMPT.format(
            hypothesis=note.hypothesis[:300],
            formula=formula,
        )
        try:
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
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

        N_SHORT = 1-10，N_MID = 11-60，N_LONG = 61+
        也支持旧版 N 占位符（兼容未迁移的约束记录）。
        """
        if not formula or not pattern:
            return False

        def _classify(m: re.Match) -> str:
            n = int(m.group())
            if n <= 10:
                return "N_SHORT"
            elif n <= 60:
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
            "N_MID": r"([1-5][0-9]|60)",
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

        if not note.invalid_regimes:
            return True, "该因子未声明 invalid_regimes，放行"

        if current_regime in note.invalid_regimes:
            return False, f"Factor invalid in current regime: {current_regime}"

        return True, f"当前 regime {current_regime} 不在 invalid_regimes 中，放行"


# ─────────────────────────────────────────────────────────
# PreFilter：组合执行四重过滤器
# ─────────────────────────────────────────────────────────

class PreFilter:
    """Stage 3 四重过滤器组合执行器。"""

    def __init__(self, factor_pool: FactorPool):
        self.validator = Validator()
        self.novelty = NoveltyFilter(pool=factor_pool, threshold=THRESHOLDS.min_novelty_threshold)
        self.alignment = AlignmentChecker()
        self.constraint_checker = ConstraintChecker(pool=factor_pool)
        self.regime_filter = RegimeFilter()

    async def filter_batch(
        self,
        notes: list[FactorResearchNote],
        current_regime: str | None = None,
    ) -> tuple[list[FactorResearchNote], int]:
        """
        五重过滤（Filter A/B/C/D/E），返回 (approved_notes, filtered_count)。
        approved_notes 数量 <= THRESHOLDS.stage3_top_k

        Args:
            notes: 候选研究笔记列表
            current_regime: 当前市场 regime 的字符串值（如 "bull_trend"）。
                            为 None 时跳过 Filter E（Regime 过滤）。
        """
        candidates = []

        for note in notes:
            # Filter A（同步，最快，无 LLM）
            passed, reason = self.validator.validate(note)
            if not passed:
                logger.info("[Filter A] 拒绝 %s: %s", note.note_id, reason)
                continue

            # Filter B（同步，无 LLM）
            passed, reason = self.novelty.check(note)
            if not passed:
                logger.info("[Filter B] 拒绝 %s: %s", note.note_id, reason)
                continue

            # Filter C（异步，LLM 快速调用，失败放行）
            passed, reason = await self.alignment.check(note)
            if not passed:
                logger.info("[Filter C] 拒绝 %s: %s", note.note_id, reason)
                continue

            # Filter D（同步，结构化失败约束检查，失败时降级放行）
            passed, reason = self.constraint_checker.check(note)
            if not passed:
                logger.info("[Filter D] 拒绝 %s: %s", note.note_id, reason)
                continue

            # Filter E（同步，regime 适用性过滤）
            passed, reason = self.regime_filter.check(note, current_regime)
            if not passed:
                logger.info("[Filter E] 拒绝 %s: %s", note.note_id, reason)
                continue

            candidates.append(note)

        # 通过数量 > Top K 时，按探索需求排序（有 exploration_questions 的排后，先回测简单的）
        candidates.sort(key=lambda n: len(n.exploration_questions))
        approved = candidates[:THRESHOLDS.stage3_top_k]
        filtered_count = len(notes) - len(approved)

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
    return {"approved_notes": approved, "filtered_count": filtered_count}
