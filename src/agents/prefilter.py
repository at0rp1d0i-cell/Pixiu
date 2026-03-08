"""
Pixiu v2 Stage 3：前置过滤层（PreFilter）

三重串联过滤器，在进入昂贵 Qlib 回测（Stage 4b）之前
低成本筛除劣质候选，最多放行 THRESHOLDS.stage3_top_k 个。

过滤器：
  A - Validator         ：A 股硬约束（字段白名单、Ref 方向、Log 安全、算子白名单）
  B - NoveltyFilter     ：AST Token Jaccard 相似度，防重复探索
  C - AlignmentChecker  ：LLM 快速调用，检验公式与经济假设语义一致性

参考 spec：docs/specs/v2_stage3_prefilter.md
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

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# Filter A：Validator（A 股硬约束，扩展自 v1 validator.py）
# ─────────────────────────────────────────────────────────

APPROVED_FIELDS = {
    "$close", "$open", "$high", "$low", "$volume", "$factor", "$amount", "$vwap",
    "$pe_ttm", "$pb", "$roe", "$revenue_yoy", "$profit_yoy",
    "$turnover_rate", "$float_mv",
}

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
# PreFilter：组合执行三重过滤器
# ─────────────────────────────────────────────────────────

class PreFilter:
    """Stage 3 三重过滤器组合执行器。"""

    def __init__(self, factor_pool: FactorPool):
        self.validator = Validator()
        self.novelty = NoveltyFilter(pool=factor_pool, threshold=THRESHOLDS.min_novelty_threshold)
        self.alignment = AlignmentChecker()

    async def filter_batch(
        self,
        notes: list[FactorResearchNote],
    ) -> tuple[list[FactorResearchNote], int]:
        """
        三重过滤，返回 (approved_notes, filtered_count)。
        approved_notes 数量 <= THRESHOLDS.stage3_top_k
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

def prefilter_node(state: dict) -> dict:
    """LangGraph Stage 3 同步入口。"""
    from src.factor_pool.pool import get_factor_pool

    notes: list[FactorResearchNote] = state.get("research_notes", [])
    pool = get_factor_pool()
    prefilter = PreFilter(factor_pool=pool)

    approved, filtered_count = asyncio.run(prefilter.filter_batch(notes))

    logger.info(
        "[Prefilter Node] %d → %d approved, %d filtered",
        len(notes), len(approved), filtered_count,
    )
    return {**state, "approved_notes": approved}
