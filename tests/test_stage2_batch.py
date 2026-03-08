"""
Stage 2: AlphaResearcher Batch Generation TDD Tests
按照 v2_stage2_hypothesis_generation.md Section 5 的测试要求编写。
"""
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from src.schemas.research_note import FactorResearchNote, AlphaResearcherBatch


# ─────────────────────────────────────────────────────────
# Schema tests
# ─────────────────────────────────────────────────────────

def test_alpha_researcher_batch_schema():
    """AlphaResearcherBatch Schema 验证：包含 island, notes, generation_rationale"""
    note = FactorResearchNote(
        note_id="momentum_2026_abc",
        island="momentum",
        iteration=1,
        hypothesis="价格动量因子假设",
        economic_intuition="动量效应....",
        proposed_formula="Ref($close, -5) / Ref($close, -20) - 1",
        risk_factors=["市场反转"],
        market_context_date="2026-03-08",
    )
    batch = AlphaResearcherBatch(
        island="momentum",
        notes=[note, note],
        generation_rationale="测试两个动量因子",
    )
    assert batch.island == "momentum"
    assert len(batch.notes) == 2
    assert batch.generation_rationale == "测试两个动量因子"


def test_alpha_researcher_returns_batch():
    """AlphaResearcher 输出必须是 AlphaResearcherBatch，包含 2-3 个 notes"""
    from src.agents.researcher import AlphaResearcher

    mock_response = MagicMock()
    mock_response.content = '''{
        "notes": [
            {
                "note_id": "momentum_2026_aaa",
                "island": "momentum",
                "iteration": 1,
                "hypothesis": "5日收益率动量",
                "economic_intuition": "趋势延续效应",
                "proposed_formula": "Ref($close, -5) / Ref($close, -20) - 1",
                "risk_factors": ["市场反转"],
                "market_context_date": "2026-03-08"
            },
            {
                "note_id": "momentum_2026_bbb",
                "island": "momentum",
                "iteration": 1,
                "hypothesis": "成交量放大动量",
                "economic_intuition": "量价背离后续跟进",
                "proposed_formula": "($volume / Mean($volume, 20) - 1) * ($close / Ref($close, -5) - 1)",
                "risk_factors": ["假突破"],
                "market_context_date": "2026-03-08"
            }
        ],
        "generation_rationale": "两种不同的动量机制：价格动量和量价动量"
    }'''

    with patch('src.agents.researcher.ChatOpenAI') as MockLLM:
        mock_chat = MockLLM.return_value
        mock_chat.ainvoke = AsyncMock(return_value=mock_response)
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            researcher = AlphaResearcher(island="momentum")
            batch = asyncio.run(researcher.generate_batch(
                context=None,
                iteration=1
            ))

    assert isinstance(batch, AlphaResearcherBatch)
    assert len(batch.notes) >= 2
    assert batch.island == "momentum"
    assert batch.generation_rationale != ""


def test_alpha_researcher_batch_diversity():
    """同一 batch 的 notes，proposed_formula 不应完全相同"""
    from src.agents.researcher import AlphaResearcher

    mock_response = MagicMock()
    mock_response.content = '''{
        "notes": [
            {
                "note_id": "a", "island": "momentum", "iteration": 1,
                "hypothesis": "动量1", "economic_intuition": "趋势",
                "proposed_formula": "Ref($close, -5) / Ref($close, -20) - 1",
                "risk_factors": [], "market_context_date": "2026-03-08"
            },
            {
                "note_id": "b", "island": "momentum", "iteration": 1,
                "hypothesis": "动量2", "economic_intuition": "量价",
                "proposed_formula": "Mean($close, 5) / Mean($close, 20) - 1",
                "risk_factors": [], "market_context_date": "2026-03-08"
            }
        ],
        "generation_rationale": "两种不同机制"
    }'''

    with patch('src.agents.researcher.ChatOpenAI') as MockLLM:
        mock_chat = MockLLM.return_value
        mock_chat.ainvoke = AsyncMock(return_value=mock_response)
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            researcher = AlphaResearcher(island="momentum")
            batch = asyncio.run(researcher.generate_batch(context=None, iteration=1))

    # 所有公式不能完全相同
    formulas = [n.proposed_formula for n in batch.notes]
    assert len(set(formulas)) == len(formulas), "同一 Batch 中出现了重复公式！"


def test_alpha_researcher_with_feedback():
    """有 CriticVerdict 反馈时，测试 LLM 接收到了反馈内容"""
    from src.agents.researcher import AlphaResearcher
    from src.schemas.judgment import CriticVerdict

    captured_messages = []

    async def capture_ainvoke(messages):
        captured_messages.extend(messages)
        resp = MagicMock()
        resp.content = '''{
            "notes": [{
                "note_id": "x", "island": "momentum", "iteration": 2,
                "hypothesis": "改进后动量", "economic_intuition": "修正",
                "proposed_formula": "Mean($close, 5) / Mean($close, 10) - 1",
                "risk_factors": [], "market_context_date": "2026-03-08"
            }],
            "generation_rationale": "针对反馈调整"
        }'''
        return resp

    verdict = CriticVerdict(
        report_id="r1",
        factor_id="f1",
        overall_passed=False,
        checks=[],
        failure_mode="low_sharpe",
        failure_explanation="Sharpe=1.5 < 2.0",
        suggested_fix="尝试延长均线窗口",
        register_to_pool=False,
        pool_tags=[],
    )

    with patch('src.agents.researcher.ChatOpenAI') as MockLLM:
        mock_chat = MockLLM.return_value
        mock_chat.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            researcher = AlphaResearcher(island="momentum")
            batch = asyncio.run(researcher.generate_batch(
                context=None,
                iteration=2,
                last_verdict=verdict
            ))

    # 确认反馈内容被注入到 user prompt
    assert any("Sharpe=1.5" in str(m.content) for m in captured_messages)
    assert isinstance(batch, AlphaResearcherBatch)


def test_hypothesis_gen_node_note_count():
    """hypothesis_gen_node 的 research_notes 数量应 >= active_islands × 2"""
    from src.agents.researcher import hypothesis_gen_node

    def mock_batch_factory(island):
        note = FactorResearchNote(
            note_id=f"{island}_x",
            island=island,
            iteration=1,
            hypothesis="test",
            economic_intuition="test",
            proposed_formula="$close",
            risk_factors=[],
            market_context_date="2026-03-08",
        )
        return AlphaResearcherBatch(island=island, notes=[note, note], generation_rationale="test")

    with patch('src.agents.researcher.AlphaResearcher') as MockResearcher:
        def make_instance(island):
            instance = MagicMock()
            instance.generate_batch = AsyncMock(return_value=mock_batch_factory(island))
            return instance
        MockResearcher.side_effect = make_instance

        state = {
            "active_islands": ["momentum", "volatility", "volume"],
            "market_context": None,
            "iteration": 1,
        }
        result = hypothesis_gen_node(state)

    # 3 islands × 2 notes = 6 notes minimum
    assert len(result["research_notes"]) >= 3 * 2
