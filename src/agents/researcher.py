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
from langchain_openai import ChatOpenAI

from src.schemas.research_note import FactorResearchNote, AlphaResearcherBatch
from src.schemas.judgment import CriticVerdict
from src.schemas.market_context import MarketContextMemo
from src.factor_pool.pool import FactorPool
from src.skills.loader import SkillLoader


def load_dotenv_if_available():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


load_dotenv_if_available()
logger = logging.getLogger(__name__)

_SKILL_LOADER = SkillLoader()

# ====================================================
# System Prompt（严格按照 v2_stage2_hypothesis_generation.md）
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
  - risk_factors: 字符串数组（可能失败的原因）
  - market_context_date: 字符串（今日日期，格式 YYYY-MM-DD）
"""

ALPHA_RESEARCHER_USER_TEMPLATE = """
## 当前 Island：{island}
{island_description}

## 市场上下文
{market_context}

## 历史反馈
{feedback_section}

## 历史失败因子（避免重复）
{failed_factors_section}

请提出 2-3 个差异化的 FactorResearchNote，输出 AlphaResearcherBatch JSON。
每个假设应捕捉 {island} 方向下不同的市场机制，而非同一思路的变体。
"""


def _today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


FUNDAMENTAL_FIELDS_ENABLED = os.getenv("FUNDAMENTAL_FIELDS_ENABLED", "false").lower() == "true"


class AlphaResearcher:
    """单 Island 的 Alpha 因子批量生成器。"""

    def __init__(self, island: str, skill_loader: Optional[SkillLoader] = None):
        self.island = island
        self.skill_loader = skill_loader or _SKILL_LOADER
        self.llm = ChatOpenAI(
            model=os.getenv("RESEARCHER_MODEL", "deepseek-chat"),
            base_url=os.getenv("RESEARCHER_BASE_URL", os.getenv("OPENAI_API_BASE")),
            api_key=os.getenv("RESEARCHER_API_KEY", os.getenv("OPENAI_API_KEY")),
            temperature=0.8,  # 稍高温度，促进多样性
        )

    async def generate_batch(
        self,
        context: Optional[MarketContextMemo],
        iteration: int,
        last_verdict: Optional[CriticVerdict] = None,
        failed_formulas: Optional[list] = None,
    ) -> AlphaResearcherBatch:
        """
        调用 LLM 一次，生成 2-3 个差异化的 FactorResearchNote。
        """
        from src.factor_pool.islands import ISLANDS
        island_info = ISLANDS.get(self.island, {})

        # 构建市场上下文字符串
        if context:
            mkt_ctx = (
                f"市场 Regime：{context.regime}\n"
                f"风险评分：{context.risk_score:.1f}/10\n"
                f"摘要：{context.summary}"
            )
        else:
            mkt_ctx = "（无市场上下文，请基于通用 A 股规律提出假设）"

        # 历史反馈
        if last_verdict and not last_verdict.overall_passed:
            fb = f"上轮失败原因：{last_verdict.failure_explanation}\n建议：{last_verdict.suggested_fix}"
        else:
            fb = "（首次迭代，无历史反馈）"

        # 失败因子
        failed_section = "无" if not failed_formulas else "\n".join(
            f"- {f}" for f in (failed_formulas or [])[:5]
        )

        user_msg = ALPHA_RESEARCHER_USER_TEMPLATE.format(
            island=self.island,
            island_description=island_info.get("description", ""),
            market_context=mkt_ctx,
            feedback_section=fb,
            failed_factors_section=failed_section,
        )

        response = await self.llm.ainvoke([
            SystemMessage(content=ALPHA_RESEARCHER_SYSTEM_PROMPT),
            HumanMessage(content=user_msg),
        ])

        return self._parse_batch(response.content, iteration)

    def _parse_batch(self, content: str, iteration: int) -> AlphaResearcherBatch:
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
            notes.append(FactorResearchNote(**note_data))

        return AlphaResearcherBatch(
            island=self.island,
            notes=notes,
            generation_rationale=data.get("generation_rationale", ""),
        )


# ====================================================
# LangGraph 节点：hypothesis_gen_node
# ====================================================
async def _hypothesis_gen_async(state: dict) -> dict:
    """
    并行运行所有激活 Island 的 AlphaResearcher，
    展开 Batch → 收集所有 notes 进入 Stage 3 过滤。
    """
    from src.factor_pool.islands import ISLANDS

    active_islands = state.get("active_islands", list(ISLANDS.keys()))
    context: Optional[MarketContextMemo] = state.get("market_context")
    iteration: int = state.get("iteration", 0)

    tasks = [
        AlphaResearcher(island=island).generate_batch(
            context=context,
            iteration=iteration,
        )
        for island in active_islands
    ]

    batches: list = await asyncio.gather(*tasks, return_exceptions=True)

    # 展开：每个 Island 的 batch 包含 2-3 个 notes，汇总为一个大列表
    all_notes: list[FactorResearchNote] = []
    for island, batch in zip(active_islands, batches):
        if isinstance(batch, Exception):
            logger.warning("AlphaResearcher[%s] 失败（跳过）: %s", island, batch)
        else:
            all_notes.extend(batch.notes)

    logger.info(
        "Stage 2 生成 %d 个候选（来自 %d 个 Island）",
        len(all_notes), len(active_islands)
    )

    return {**state, "research_notes": all_notes}


def hypothesis_gen_node(state: dict) -> dict:
    """LangGraph 同步入口。"""
    return asyncio.run(_hypothesis_gen_async(state))


# ====================================================
# 向后兼容：旧版 research_node（Legacy v1 路径）
# ====================================================
def research_node(state: dict) -> dict:
    """Legacy v1 单 Island 研究节点（兼容旧 orchestrator）。"""
    import asyncio
    island_name = state.get("island_name", "momentum")
    researcher = AlphaResearcher(island=island_name)

    async def _run():
        batch = await researcher.generate_batch(
            context=state.get("market_context"),
            iteration=state.get("current_iteration", 0),
        )
        # v1 兼容：取第一个 note 转成旧 schema
        if batch.notes:
            note = batch.notes[0]
            return {
                "factor_proposal": note.proposed_formula,
                "factor_hypothesis": None,
                "messages": [],
            }
        return {"factor_proposal": "", "factor_hypothesis": None, "messages": []}

    return asyncio.run(_run())
