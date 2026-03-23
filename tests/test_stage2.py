"""
Stage 2 merged tests: batch + researcher hypothesis generation + research note methods +
research note hypothesis bridge + stage2 hypothesis output.

Sources:
  - tests/test_stage2_batch.py
  - tests/test_researcher_hypothesis_generation.py
  - tests/test_research_note_methods.py
  - tests/test_research_note_hypothesis_bridge.py
  - tests/test_stage2_hypothesis_output.py
"""
from unittest.mock import AsyncMock, MagicMock, patch

import asyncio

import pytest

from src.schemas.research_note import FactorResearchNote, AlphaResearcherBatch, ExplorationQuestion
from src.schemas.hypothesis import Hypothesis, StrategySpec, ExplorationSubspace
from src.schemas.market_context import MarketContextMemo
from src.scheduling.subspace_scheduler import SubspaceScheduler

pytestmark = pytest.mark.unit


# ─────────────────────────────────────────────────────────
# From test_stage2_batch.py — Schema tests
# ─────────────────────────────────────────────────────────

def test_alpha_researcher_batch_schema():
    """AlphaResearcherBatch Schema 验证：包含 island, notes, generation_rationale"""
    note = FactorResearchNote(
        note_id="momentum_2026_abc",
        island="momentum",
        iteration=1,
        hypothesis="价格动量因子假设",
        economic_intuition="动量效应....",
        proposed_formula="Ref($close, 5) / Ref($close, 20) - 1",
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
                "proposed_formula": "Ref($close, 5) / Ref($close, 20) - 1",
                "risk_factors": ["市场反转"],
                "market_context_date": "2026-03-08"
            },
            {
                "note_id": "momentum_2026_bbb",
                "island": "momentum",
                "iteration": 1,
                "hypothesis": "成交量放大动量",
                "economic_intuition": "量价背离后续跟进",
                "proposed_formula": "($volume / Mean($volume, 20) - 1) * ($close / Ref($close, 5) - 1)",
                "risk_factors": ["假突破"],
                "market_context_date": "2026-03-08"
            }
        ],
        "generation_rationale": "两种不同的动量机制：价格动量和量价动量"
    }'''

    with patch('src.agents.researcher.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(return_value=mock_response)
        mock_builder.return_value = mock_chat
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
                "proposed_formula": "Ref($close, 5) / Ref($close, 20) - 1",
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

    with patch('src.agents.researcher.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(return_value=mock_response)
        mock_builder.return_value = mock_chat
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            researcher = AlphaResearcher(island="momentum")
            batch = asyncio.run(researcher.generate_batch(context=None, iteration=1))

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

    with patch('src.agents.researcher.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        mock_builder.return_value = mock_chat
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            researcher = AlphaResearcher(island="momentum")
            batch = asyncio.run(researcher.generate_batch(
                context=None,
                iteration=2,
                last_verdict=verdict
            ))

    assert any("Sharpe=1.5" in str(m.content) for m in captured_messages)
    assert isinstance(batch, AlphaResearcherBatch)


def test_alpha_researcher_system_prompt_injects_runtime_available_fields():
    from src.agents.researcher import AlphaResearcher

    captured_messages = []

    async def capture_ainvoke(messages):
        captured_messages.extend(messages)
        resp = MagicMock()
        resp.content = '''{
            "notes": [{
                "note_id": "x", "island": "momentum", "iteration": 1,
                "hypothesis": "test", "economic_intuition": "test",
                "proposed_formula": "Mean($close, 5)",
                "risk_factors": [], "market_context_date": "2026-03-19"
            }],
            "generation_rationale": "test"
        }'''
        return resp

    with patch('src.agents.researcher.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        mock_builder.return_value = mock_chat
        with patch('src.agents.researcher.format_available_fields_for_prompt', return_value="  基础价量字段：$close\n  扩展实验字段：$roe"):
            with patch('src.agents.researcher.get_runtime_formula_capabilities', return_value=MagicMock()):
                with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
                    researcher = AlphaResearcher(island="momentum")
                    asyncio.run(researcher.generate_batch(context=None, iteration=1))

    assert captured_messages
    system_message = captured_messages[0]
    assert "$roe" in system_message.content


def test_alpha_researcher_system_prompt_injects_runtime_operator_block():
    from src.agents.researcher import AlphaResearcher

    captured_messages = []

    async def capture_ainvoke(messages):
        captured_messages.extend(messages)
        resp = MagicMock()
        resp.content = '''{
            "notes": [{
                "note_id": "x", "island": "momentum", "iteration": 1,
                "hypothesis": "test", "economic_intuition": "test",
                "proposed_formula": "Mean($close, 5)",
                "risk_factors": [], "market_context_date": "2026-03-19"
            }],
            "generation_rationale": "test"
        }'''
        return resp

    with patch('src.agents.researcher.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        mock_builder.return_value = mock_chat
        with patch('src.agents.researcher.format_available_fields_for_prompt', return_value="  基础价量字段：$close"):
            with patch('src.agents.researcher.format_available_operators_for_prompt', return_value="  常用稳定算子：\n    - `Ref($field, N)` — N 日前的值"):
                with patch('src.agents.researcher.get_runtime_formula_capabilities', return_value=MagicMock()):
                    with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
                        researcher = AlphaResearcher(island="momentum")
                        asyncio.run(researcher.generate_batch(context=None, iteration=1))

    assert captured_messages
    system_message = captured_messages[0]
    assert "可用算子" in system_message.content
    assert "Ref($field, N)" in system_message.content
    assert "Ref($field, -N)" not in system_message.content
    assert "Rank(expr, N)" in system_message.content
    assert "禁止 Rank(expr)" in system_message.content
    assert "Zscore/MinMax/Neutralize/Demean" in system_message.content


def test_stage2_subspace_context_avoids_legacy_cross_section_and_normalization_wording():
    from src.schemas.exploration import SubspaceRegistry
    from src.scheduling.subspace_context import (
        build_factor_algebra_context,
        build_symbolic_mutation_context,
    )

    registry = SubspaceRegistry.get_default_registry()
    factor_algebra = build_factor_algebra_context(registry=registry, island="momentum", pool=None)
    symbolic_mutation = build_symbolic_mutation_context(
        registry=registry,
        factor_pool=None,
        island="momentum",
    )

    assert "截面算子用于横截面排名/标准化" not in factor_algebra
    assert "zscore/rank/minmax" not in symbolic_mutation
    assert "Rank(expr, N)" in symbolic_mutation


def test_alpha_researcher_composed_prompt_avoids_legacy_skill_contracts():
    from src.agents.researcher import AlphaResearcher

    captured_messages = []

    async def capture_ainvoke(messages):
        captured_messages.extend(messages)
        resp = MagicMock()
        resp.content = '''{
            "notes": [{
                "note_id": "x", "island": "valuation", "iteration": 2,
                "hypothesis": "test", "economic_intuition": "test",
                "proposed_formula": "Mean($roe, 5)",
                "risk_factors": [], "market_context_date": "2026-03-19"
            }],
            "generation_rationale": "test"
        }'''
        return resp

    with patch('src.agents.researcher.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        mock_builder.return_value = mock_chat
        with patch('src.agents.researcher.format_available_fields_for_prompt', return_value="  基础价量字段：$close\n  扩展实验字段：$roe"):
            with patch('src.agents.researcher.get_runtime_formula_capabilities', return_value=MagicMock()):
                with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
                    researcher = AlphaResearcher(island="valuation")
                    asyncio.run(
                        researcher.generate_batch(
                            context=None,
                            iteration=2,
                            subspace_hint=ExplorationSubspace.FACTOR_ALGEBRA,
                        )
                    )

    assert captured_messages
    system_message = captured_messages[0]
    assert "$roe" in system_message.content
    assert "FUNDAMENTAL_FIELDS_ENABLED" not in system_message.content
    # CSRank 可以出现在 "不要使用" 的上下文中（skill 文件里的禁用提示）
    # 但不应作为可用算子推荐
    assert "CSRank(" not in system_message.content
    assert "get_island_best_factors" not in system_message.content
    assert "AKShare 工具" not in system_message.content


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
        def make_instance(island, **kwargs):
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

    assert len(result["research_notes"]) >= 3 * 2


def test_batch_notes_carry_exploration_subspace():
    """当 subspace_hint 传入时，生成的 notes 应带 exploration_subspace 字段"""
    from src.agents.researcher import AlphaResearcher

    mock_response = MagicMock()
    mock_response.content = '''{
        "notes": [
            {
                "note_id": "a", "island": "momentum", "iteration": 1,
                "hypothesis": "动量1", "economic_intuition": "趋势",
                "proposed_formula": "Ref($close, 5) / Ref($close, 20) - 1",
                "risk_factors": [], "market_context_date": "2026-03-08"
            }
        ],
        "generation_rationale": "测试子空间溯源"
    }'''

    with patch('src.agents.researcher.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(return_value=mock_response)
        mock_builder.return_value = mock_chat
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            researcher = AlphaResearcher(island="momentum")
            batch = asyncio.run(researcher.generate_batch(
                context=None,
                iteration=1,
                subspace_hint=ExplorationSubspace.FACTOR_ALGEBRA,
            ))

    assert batch.notes[0].exploration_subspace == ExplorationSubspace.FACTOR_ALGEBRA


def test_alpha_researcher_local_prescreen_rejects_unsafe_formula():
    from src.agents.researcher import AlphaResearcher

    mock_response = MagicMock()
    mock_response.content = '''{
        "notes": [
            {
                "note_id": "safe", "island": "momentum", "iteration": 1,
                "hypothesis": "safe", "economic_intuition": "safe",
                "proposed_formula": "Mean($close, 5) - Mean($close, 20)",
                "risk_factors": [], "market_context_date": "2026-03-08",
                "applicable_regimes": ["bull_trend"], "invalid_regimes": ["range_bound"]
            },
            {
                "note_id": "unsafe", "island": "momentum", "iteration": 1,
                "hypothesis": "unsafe", "economic_intuition": "unsafe",
                "proposed_formula": "Div($close, Std($close, 5))",
                "risk_factors": [], "market_context_date": "2026-03-08",
                "applicable_regimes": ["bull_trend"], "invalid_regimes": ["range_bound"]
            }
        ],
        "generation_rationale": "mixed"
    }'''

    with patch("src.agents.researcher.build_researcher_llm") as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(return_value=mock_response)
        mock_builder.return_value = mock_chat
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test", "RESEARCHER_API_KEY": "test"}):
            researcher = AlphaResearcher(island="momentum")
            batch = asyncio.run(researcher.generate_batch(context=None, iteration=1))

    assert len(batch.notes) == 1
    assert batch.notes[0].note_id == "safe"
    assert researcher.last_generation_diagnostics["rejection_counts_by_filter"].get("validator", 0) >= 1
    grouped = researcher.last_generation_diagnostics.get("rejection_counts_by_filter_and_subspace", {})
    assert grouped.get("validator", {}).get("unknown", 0) >= 1
    sample = researcher.last_generation_diagnostics["sample_rejections"][0]
    assert sample["exploration_subspace"] == "unknown"
    assert researcher.last_generation_diagnostics["local_retry_count"] == 0


def test_alpha_researcher_local_prescreen_retries_once_on_full_reject():
    from src.agents.researcher import AlphaResearcher

    captured_user_messages = []
    first = MagicMock()
    first.content = '''{
        "notes": [{
            "note_id": "bad", "island": "momentum", "iteration": 1,
            "hypothesis": "bad", "economic_intuition": "bad",
            "proposed_formula": "Div($close, Std($close, 5))",
            "risk_factors": [], "market_context_date": "2026-03-08",
            "applicable_regimes": ["bull_trend"], "invalid_regimes": ["range_bound"]
        }],
        "generation_rationale": "first"
    }'''
    second = MagicMock()
    second.content = '''{
        "notes": [{
            "note_id": "good", "island": "momentum", "iteration": 1,
            "hypothesis": "good", "economic_intuition": "good",
            "proposed_formula": "Mean($close, 5) - Mean($close, 20)",
            "risk_factors": [], "market_context_date": "2026-03-08",
            "applicable_regimes": ["bull_trend"], "invalid_regimes": ["range_bound"]
        }],
        "generation_rationale": "second"
    }'''

    async def capture_ainvoke(messages):
        captured_user_messages.append(messages[1].content)
        if len(captured_user_messages) == 1:
            return first
        return second

    with patch("src.agents.researcher.build_researcher_llm") as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        mock_builder.return_value = mock_chat
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test", "RESEARCHER_API_KEY": "test"}):
            researcher = AlphaResearcher(island="momentum")
            batch = asyncio.run(researcher.generate_batch(context=None, iteration=1))

    assert len(batch.notes) == 1
    assert batch.notes[0].note_id == "good"
    assert researcher.last_generation_diagnostics["local_retry_count"] == 1
    assert mock_chat.ainvoke.await_count == 2
    assert len(captured_user_messages) == 2
    assert "重试硬约束" in captured_user_messages[1]
    assert "Rank(expr, N)" in captured_user_messages[1]
    assert "禁止 Rank(expr)" in captured_user_messages[1]
    assert "Zscore/MinMax/Neutralize/Demean" in captured_user_messages[1]


def test_alpha_researcher_local_prescreen_no_retry_when_partial_pass():
    from src.agents.researcher import AlphaResearcher

    mixed = MagicMock()
    mixed.content = '''{
        "notes": [
            {
                "note_id": "good", "island": "momentum", "iteration": 1,
                "hypothesis": "good", "economic_intuition": "good",
                "proposed_formula": "Mean($close, 5) - Mean($close, 20)",
                "risk_factors": [], "market_context_date": "2026-03-08",
                "applicable_regimes": ["bull_trend"], "invalid_regimes": ["range_bound"]
            },
            {
                "note_id": "bad", "island": "momentum", "iteration": 1,
                "hypothesis": "bad", "economic_intuition": "bad",
                "proposed_formula": "Div($close, Std($close, 5))",
                "risk_factors": [], "market_context_date": "2026-03-08",
                "applicable_regimes": ["bull_trend"], "invalid_regimes": ["range_bound"]
            }
        ],
        "generation_rationale": "mixed"
    }'''

    with patch("src.agents.researcher.build_researcher_llm") as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(return_value=mixed)
        mock_builder.return_value = mock_chat
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test", "RESEARCHER_API_KEY": "test"}):
            researcher = AlphaResearcher(island="momentum")
            batch = asyncio.run(researcher.generate_batch(context=None, iteration=1))

    assert len(batch.notes) == 1
    assert batch.notes[0].note_id == "good"
    assert researcher.last_generation_diagnostics["local_retry_count"] == 0
    assert mock_chat.ainvoke.await_count == 1


def test_alpha_researcher_local_novelty_rejects_duplicate_formula():
    from src.agents.researcher import AlphaResearcher

    duplicate = MagicMock()
    duplicate.content = '''{
        "notes": [{
            "note_id": "dup", "island": "momentum", "iteration": 1,
            "hypothesis": "dup", "economic_intuition": "dup",
            "proposed_formula": "Mean($close, 5) - Mean($close, 20)",
            "risk_factors": [], "market_context_date": "2026-03-08",
            "applicable_regimes": ["bull_trend"], "invalid_regimes": ["range_bound"]
        }],
        "generation_rationale": "dup"
    }'''
    mock_pool = MagicMock()
    mock_pool.get_island_factors.return_value = [
        {"formula": "Mean($close, 5) - Mean($close, 20)", "factor_id": "existing"}
    ]

    with patch("src.agents.researcher.build_researcher_llm") as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(side_effect=[duplicate, duplicate])
        mock_builder.return_value = mock_chat
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test", "RESEARCHER_API_KEY": "test"}):
            researcher = AlphaResearcher(island="momentum", factor_pool=mock_pool)
            batch = asyncio.run(researcher.generate_batch(context=None, iteration=1))

    assert len(batch.notes) == 0
    assert researcher.last_generation_diagnostics["local_retry_count"] == 1
    assert researcher.last_generation_diagnostics["rejection_counts_by_filter"].get("novelty", 0) >= 1


def test_hypothesis_gen_node_passes_factor_pool_and_returns_stage2_diagnostics():
    from src.agents.researcher import hypothesis_gen_node

    sentinel_pool = object()
    captured_pools = []

    with patch("src.factor_pool.pool.get_factor_pool", return_value=sentinel_pool):
        with patch("src.agents.researcher.AlphaResearcher") as MockResearcher:
            def make_instance(island, **kwargs):
                captured_pools.append(kwargs.get("factor_pool"))
                instance = MagicMock()
                note = FactorResearchNote(
                    note_id=f"{island}_x",
                    island=island,
                    iteration=1,
                    hypothesis="test",
                    economic_intuition="test",
                    proposed_formula="Mean($close, 5) - Mean($close, 20)",
                    risk_factors=[],
                    market_context_date="2026-03-08",
                )
                instance.generate_batch = AsyncMock(
                    return_value=AlphaResearcherBatch(
                        island=island,
                        notes=[note],
                        generation_rationale="ok",
                    )
                )
                instance.last_generation_diagnostics = {
                    "generated_count": 1,
                    "delivered_count": 1,
                    "local_retry_count": 0,
                    "rejection_counts_by_filter": {},
                    "sample_rejections": [],
                }
                return instance

            MockResearcher.side_effect = make_instance
            result = hypothesis_gen_node(
                {"active_islands": ["momentum"], "market_context": None, "iteration": 1}
            )

    assert captured_pools
    assert all(pool is sentinel_pool for pool in captured_pools)
    assert "stage2_diagnostics" in result
    assert result["stage2_diagnostics"]["generated_count"] >= 1


def test_alpha_researcher_symbolic_path_runs_local_prescreen():
    from src.agents.researcher import AlphaResearcher

    safe_note = FactorResearchNote(
        note_id="safe_symbolic",
        island="momentum",
        iteration=1,
        hypothesis="safe",
        economic_intuition="safe",
        proposed_formula="Mean($close, 5) - Mean($close, 20)",
        risk_factors=[],
        market_context_date="2026-03-08",
        applicable_regimes=["bull_trend"],
        invalid_regimes=["range_bound"],
        exploration_subspace=ExplorationSubspace.SYMBOLIC_MUTATION,
    )
    unsafe_note = FactorResearchNote(
        note_id="unsafe_symbolic",
        island="momentum",
        iteration=1,
        hypothesis="unsafe",
        economic_intuition="unsafe",
        proposed_formula="Rank($close)",
        risk_factors=[],
        market_context_date="2026-03-08",
        applicable_regimes=["bull_trend"],
        invalid_regimes=["range_bound"],
        exploration_subspace=ExplorationSubspace.SYMBOLIC_MUTATION,
    )
    symbolic_batch = AlphaResearcherBatch(
        island="momentum",
        notes=[safe_note, unsafe_note],
        generation_rationale="symbolic",
    )

    mock_pool = MagicMock()
    mock_pool.get_island_factors.return_value = []

    researcher = AlphaResearcher(island="momentum", factor_pool=mock_pool)
    with patch.object(researcher, "_try_symbolic_mutation_batch", return_value=symbolic_batch):
        batch = asyncio.run(
            researcher.generate_batch(
                context=None,
                iteration=1,
                subspace_hint=ExplorationSubspace.SYMBOLIC_MUTATION,
            )
        )

    assert [note.note_id for note in batch.notes] == ["safe_symbolic"]
    assert researcher.last_generation_diagnostics["generated_count"] == 2
    assert researcher.last_generation_diagnostics["rejection_counts_by_filter"].get("validator", 0) >= 1
    grouped = researcher.last_generation_diagnostics.get("rejection_counts_by_filter_and_subspace", {})
    assert grouped.get("validator", {}).get("symbolic_mutation", 0) >= 1
    assert researcher.last_generation_diagnostics["sample_rejections"][0]["exploration_subspace"] == "symbolic_mutation"


def test_prefilter_diagnostics_include_rejection_subspace_breakdown():
    from src.agents.prefilter import PreFilter

    note = FactorResearchNote(
        note_id="reject_cross_market",
        island="momentum",
        iteration=1,
        hypothesis="test",
        economic_intuition="test",
        proposed_formula="Mean($close, 5)",
        risk_factors=[],
        market_context_date="2026-03-08",
        applicable_regimes=["bull_trend"],
        invalid_regimes=["range_bound"],
        exploration_subspace=ExplorationSubspace.CROSS_MARKET,
    )

    prefilter = PreFilter(factor_pool=MagicMock())
    with patch.object(prefilter.validator, "validate", return_value=(False, "bad formula")):
        approved, filtered = asyncio.run(prefilter.filter_batch([note], current_regime="bull_trend"))

    assert approved == []
    assert filtered == 1
    assert prefilter.last_diagnostics["rejection_counts_by_filter"]["validator"] == 1
    grouped = prefilter.last_diagnostics["rejection_counts_by_filter_and_subspace"]
    assert grouped["validator"]["cross_market"] == 1
    sample = prefilter.last_diagnostics["sample_rejections"][0]
    assert sample["exploration_subspace"] == "cross_market"


def test_alpha_researcher_injects_market_regime_skill_from_context():
    """当 generate_batch() 收到 market context 时，system prompt 应包含 regime skill。"""
    from src.agents.researcher import AlphaResearcher

    captured_messages = []

    async def capture_ainvoke(messages):
        captured_messages.append(messages)
        response = MagicMock()
        response.content = """{
            "notes": [{
                "note_id": "x",
                "island": "momentum",
                "iteration": 1,
                "hypothesis": "动量测试",
                "economic_intuition": "趋势延续",
                "proposed_formula": "Mean($close, 5) / Mean($close, 20) - 1",
                "risk_factors": [],
                "market_context_date": "2026-03-19"
            }],
            "generation_rationale": "测试"
        }"""
        return response

    context = MarketContextMemo(
        date="2026-03-19",
        northbound=None,
        macro_signals=[],
        hot_themes=["中字头"],
        historical_insights=[],
        suggested_islands=["momentum"],
        market_regime="bull_trend",
        raw_summary="市场趋势向上",
    )

    with patch('src.agents.researcher.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        mock_builder.return_value = mock_chat
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            researcher = AlphaResearcher(island="momentum")
            asyncio.run(researcher.generate_batch(context=context, iteration=1))

    assert captured_messages
    system_message = captured_messages[0][0]
    assert "市场状态识别规范" in system_message.content


def test_alpha_researcher_injects_island_skill_marker():
    """Researcher 应把当前 island 传给 SkillLoader，而不是只加载通用 researcher skills。"""
    from src.agents.researcher import AlphaResearcher

    captured_messages = []

    async def capture_ainvoke(messages):
        captured_messages.append(messages)
        response = MagicMock()
        response.content = """{
            "notes": [{
                "note_id": "x",
                "island": "volume",
                "iteration": 1,
                "hypothesis": "量能测试",
                "economic_intuition": "换手率异常",
                "proposed_formula": "Mean($volume, 5) / Mean($volume, 20) - 1",
                "risk_factors": [],
                "market_context_date": "2026-03-19"
            }],
            "generation_rationale": "测试"
        }"""
        return response

    with patch('src.agents.researcher.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        mock_builder.return_value = mock_chat
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            researcher = AlphaResearcher(island="volume")
            asyncio.run(researcher.generate_batch(context=None, iteration=1))

    assert captured_messages
    system_message = captured_messages[0][0]
    assert "<!-- SKILL:ISLAND_VOLUME -->" in system_message.content


# ─────────────────────────────────────────────────────────
# From test_researcher_hypothesis_generation.py
# ─────────────────────────────────────────────────────────

def test_research_note_to_hypothesis():
    """测试 FactorResearchNote 可以转换为 Hypothesis"""
    note = FactorResearchNote(
        note_id="momentum_20260313_001",
        island="momentum",
        iteration=1,
        hypothesis="短期价格动量延续效应",
        economic_intuition="市场参与者的追涨行为导致短期趋势延续",
        proposed_formula="Ref($close, -5) / Ref($close, -20) - 1",
        risk_factors=["市场反转", "流动性枯竭"],
        inspired_by="AlphaAgent论文",
        market_context_date="2026-03-13"
    )

    hypothesis = note.to_hypothesis()

    assert isinstance(hypothesis, Hypothesis)
    assert hypothesis.hypothesis_id == f"hyp_{note.note_id}"
    assert hypothesis.island == "momentum"
    assert hypothesis.mechanism == "短期价格动量延续效应"
    assert hypothesis.economic_rationale == "市场参与者的追涨行为导致短期趋势延续"
    assert "AlphaAgent论文" in hypothesis.inspirations
    assert "市场反转" in hypothesis.failure_priors


def test_research_note_to_strategy_spec():
    """测试 FactorResearchNote 可以转换为 StrategySpec"""
    note = FactorResearchNote(
        note_id="momentum_20260313_001",
        island="momentum",
        iteration=1,
        hypothesis="短期价格动量延续效应",
        economic_intuition="市场参与者的追涨行为导致短期趋势延续",
        proposed_formula="Ref($close, -5) / Ref($close, -20) - 1",
        risk_factors=["市场反转"],
        market_context_date="2026-03-13"
    )

    spec = note.to_strategy_spec()

    assert isinstance(spec, StrategySpec)
    assert spec.spec_id == f"spec_{note.note_id}"
    assert spec.hypothesis_id == f"hyp_{note.note_id}"
    assert spec.factor_expression == "Ref($close, -5) / Ref($close, -20) - 1"
    assert "$close" in spec.required_fields


def test_batch_notes_to_hypotheses():
    notes = [
        FactorResearchNote(
            note_id=f"momentum_001_{i}",
            island="momentum",
            iteration=1,
            hypothesis=f"动量效应{i}",
            economic_intuition=f"原理{i}",
            proposed_formula="$close",
            risk_factors=[],
            market_context_date="2026-03-13"
        )
        for i in range(3)
    ]

    batch = AlphaResearcherBatch(
        island="momentum",
        notes=notes,
        generation_rationale="测试批量生成"
    )

    hypotheses = [note.to_hypothesis() for note in batch.notes]

    assert len(hypotheses) == 3
    assert all(isinstance(h, Hypothesis) for h in hypotheses)
    assert all(h.island == "momentum" for h in hypotheses)
    assert hypotheses[0].mechanism == "动量效应0"
    assert hypotheses[1].mechanism == "动量效应1"
    assert hypotheses[2].mechanism == "动量效应2"


def test_batch_notes_to_strategy_specs():
    notes = [
        FactorResearchNote(
            note_id=f"vol_001_{i}",
            island="volatility",
            iteration=1,
            hypothesis=f"波动率假设{i}",
            economic_intuition=f"原理{i}",
            proposed_formula=f"Std($close, {10 + i * 5})",
            risk_factors=[],
            market_context_date="2026-03-13"
        )
        for i in range(3)
    ]

    batch = AlphaResearcherBatch(
        island="volatility",
        notes=notes,
        generation_rationale="测试批量生成"
    )

    specs = [note.to_strategy_spec() for note in batch.notes]

    assert len(specs) == 3
    assert all(isinstance(s, StrategySpec) for s in specs)
    assert specs[0].factor_expression == "Std($close, 10)"
    assert specs[1].factor_expression == "Std($close, 15)"
    assert specs[2].factor_expression == "Std($close, 20)"


def test_hypothesis_strategy_spec_linkage_in_batch():
    notes = [
        FactorResearchNote(
            note_id=f"test_{i}",
            island="momentum",
            iteration=1,
            hypothesis=f"假设{i}",
            economic_intuition=f"原理{i}",
            proposed_formula="$close",
            risk_factors=[],
            market_context_date="2026-03-13"
        )
        for i in range(2)
    ]

    batch = AlphaResearcherBatch(
        island="momentum",
        notes=notes,
        generation_rationale="测试"
    )

    pairs = [(note.to_hypothesis(), note.to_strategy_spec()) for note in batch.notes]

    for hyp, spec in pairs:
        assert spec.hypothesis_id == hyp.hypothesis_id
        assert hyp.hypothesis_id.startswith("hyp_")
        assert spec.spec_id.startswith("spec_")


def test_multi_island_batch_conversion():
    islands = ["momentum", "volatility", "valuation"]
    all_notes = []

    for island in islands:
        for i in range(2):
            note = FactorResearchNote(
                note_id=f"{island}_{i}",
                island=island,
                iteration=1,
                hypothesis=f"{island}假设{i}",
                economic_intuition=f"{island}原理{i}",
                proposed_formula="$close",
                risk_factors=[],
                market_context_date="2026-03-13"
            )
            all_notes.append(note)

    hypotheses = [note.to_hypothesis() for note in all_notes]
    specs = [note.to_strategy_spec() for note in all_notes]

    assert len(hypotheses) == 6
    assert len(specs) == 6

    for island in islands:
        island_hyps = [h for h in hypotheses if h.island == island]
        assert len(island_hyps) == 2


def test_note_with_final_formula_conversion():
    note = FactorResearchNote(
        note_id="test_001",
        island="momentum",
        iteration=1,
        hypothesis="测试假设",
        economic_intuition="测试原理",
        proposed_formula="$close",
        final_formula="Rank($close)",
        risk_factors=[],
        market_context_date="2026-03-13"
    )

    spec = note.to_strategy_spec()
    assert spec.factor_expression == "Rank($close)"


# ─────────────────────────────────────────────────────────
# From test_research_note_methods.py
# ─────────────────────────────────────────────────────────

def test_to_hypothesis_method():
    note = FactorResearchNote(
        note_id="momentum_20260313_001",
        island="momentum",
        iteration=1,
        hypothesis="价格动量延续效应",
        economic_intuition="市场参与者的追涨行为导致短期趋势延续",
        proposed_formula="Ref($close, -5) / Ref($close, -20) - 1",
        risk_factors=["市场反转", "流动性枯竭"],
        inspired_by="AlphaAgent论文",
        market_context_date="2026-03-13",
    )

    hyp = note.to_hypothesis()

    assert hyp.hypothesis_id == "hyp_momentum_20260313_001"
    assert hyp.island == "momentum"
    assert hyp.mechanism == "价格动量延续效应"
    assert hyp.economic_rationale == "市场参与者的追涨行为导致短期趋势延续"
    assert "AlphaAgent论文" in hyp.inspirations
    assert "市场反转" in hyp.failure_priors
    assert "流动性枯竭" in hyp.failure_priors


def test_to_strategy_spec_method():
    note = FactorResearchNote(
        note_id="vol_20260313_001",
        island="volatility",
        iteration=1,
        hypothesis="波动率均值回归",
        economic_intuition="极端波动后市场趋于平静",
        proposed_formula="Std($close, 20)",
        final_formula="Std($close, 20) / Mean(Std($close, 20), 60)",
        universe="csi300",
        holding_period=5,
        risk_factors=["持续高波动"],
        market_context_date="2026-03-13",
    )

    spec = note.to_strategy_spec()

    assert spec.spec_id == "spec_vol_20260313_001"
    assert spec.hypothesis_id == "hyp_vol_20260313_001"
    assert spec.factor_expression == "Std($close, 20) / Mean(Std($close, 20), 60)"
    assert spec.universe == "csi300"
    assert spec.benchmark == "SH000300"
    assert spec.freq == "day"
    assert spec.holding_period == 5
    assert "$close" in spec.required_fields


def test_to_strategy_spec_uses_proposed_formula_when_no_final():
    note = FactorResearchNote(
        note_id="test_001",
        island="momentum",
        iteration=1,
        hypothesis="测试假设",
        economic_intuition="测试原理",
        proposed_formula="$close / Ref($close, -1) - 1",
        risk_factors=[],
        market_context_date="2026-03-13",
    )

    spec = note.to_strategy_spec()

    assert spec.factor_expression == "$close / Ref($close, -1) - 1"
    assert "$close" in spec.required_fields


def test_extract_required_fields_single_field():
    note = FactorResearchNote(
        note_id="test_001",
        island="momentum",
        iteration=1,
        hypothesis="测试",
        economic_intuition="测试",
        proposed_formula="Ref($close, -5)",
        risk_factors=[],
        market_context_date="2026-03-13",
    )

    fields = note._extract_required_fields(note.proposed_formula)
    assert fields == ["$close"]


def test_extract_required_fields_multiple_fields():
    note = FactorResearchNote(
        note_id="test_001",
        island="volume",
        iteration=1,
        hypothesis="测试",
        economic_intuition="测试",
        proposed_formula="($volume / Mean($volume, 20)) * ($close / Ref($close, -5))",
        risk_factors=[],
        market_context_date="2026-03-13",
    )

    fields = note._extract_required_fields(note.proposed_formula)
    assert "$volume" in fields
    assert "$close" in fields
    assert len(fields) == 2


def test_extract_required_fields_deduplication():
    note = FactorResearchNote(
        note_id="test_001",
        island="momentum",
        iteration=1,
        hypothesis="测试",
        economic_intuition="测试",
        proposed_formula="$close / Ref($close, -1) + Ref($close, -5)",
        risk_factors=[],
        market_context_date="2026-03-13",
    )

    fields = note._extract_required_fields(note.proposed_formula)
    assert fields == ["$close"]


def test_extract_required_fields_no_fields():
    note = FactorResearchNote(
        note_id="test_001",
        island="momentum",
        iteration=1,
        hypothesis="测试",
        economic_intuition="测试",
        proposed_formula="1 + 1",
        risk_factors=[],
        market_context_date="2026-03-13",
    )

    fields = note._extract_required_fields(note.proposed_formula)
    assert fields == ["$close"]


def test_to_strategy_spec_custom_benchmark():
    note = FactorResearchNote(
        note_id="test_001",
        island="momentum",
        iteration=1,
        hypothesis="测试",
        economic_intuition="测试",
        proposed_formula="$close",
        risk_factors=[],
        market_context_date="2026-03-13",
    )

    spec = note.to_strategy_spec(benchmark="SH000905", freq="week")

    assert spec.benchmark == "SH000905"
    assert spec.freq == "week"


def test_note_without_inspired_by():
    note = FactorResearchNote(
        note_id="test_001",
        island="momentum",
        iteration=1,
        hypothesis="测试假设",
        economic_intuition="测试原理",
        proposed_formula="$close",
        risk_factors=["风险1"],
        market_context_date="2026-03-13",
    )

    hyp = note.to_hypothesis()

    assert hyp.inspirations == []
    assert len(hyp.failure_priors) == 1


def test_round_trip_conversion():
    note = FactorResearchNote(
        note_id="complete_001",
        island="valuation",
        iteration=2,
        hypothesis="低估值修复",
        economic_intuition="价值回归原理",
        proposed_formula="1 / $pe_ratio",
        final_formula="Rank(1 / $pe_ratio)",
        universe="csi300",
        holding_period=10,
        risk_factors=["估值陷阱", "行业轮动"],
        inspired_by="价值投资理论",
        market_context_date="2026-03-13",
    )

    hyp = note.to_hypothesis()
    spec = note.to_strategy_spec()

    assert spec.hypothesis_id == hyp.hypothesis_id
    assert hyp.hypothesis_id == f"hyp_{note.note_id}"
    assert spec.spec_id == f"spec_{note.note_id}"

    assert hyp.mechanism == note.hypothesis
    assert hyp.economic_rationale == note.economic_intuition
    assert spec.factor_expression == note.final_formula
    assert spec.holding_period == note.holding_period


# ─────────────────────────────────────────────────────────
# From test_research_note_hypothesis_bridge.py
# ─────────────────────────────────────────────────────────

def test_factor_research_note_to_hypothesis():
    note = FactorResearchNote(
        note_id="momentum_20260313_001",
        island="momentum",
        iteration=1,
        hypothesis="价格动量延续效应",
        economic_intuition="市场参与者的追涨行为导致短期趋势延续",
        proposed_formula="Ref($close, -5) / Ref($close, -20) - 1",
        risk_factors=["市场反转", "流动性枯竭"],
        inspired_by="AlphaAgent论文",
        market_context_date="2026-03-13",
    )

    hypothesis = Hypothesis(
        hypothesis_id=f"hyp_{note.note_id}",
        island=note.island,
        mechanism=note.hypothesis,
        economic_rationale=note.economic_intuition,
        inspirations=[note.inspired_by] if note.inspired_by else [],
        failure_priors=note.risk_factors,
    )

    assert hypothesis.hypothesis_id == "hyp_momentum_20260313_001"
    assert hypothesis.island == "momentum"
    assert hypothesis.mechanism == "价格动量延续效应"
    assert hypothesis.economic_rationale == "市场参与者的追涨行为导致短期趋势延续"
    assert "AlphaAgent论文" in hypothesis.inspirations
    assert "市场反转" in hypothesis.failure_priors


def test_factor_research_note_to_strategy_spec():
    note = FactorResearchNote(
        note_id="momentum_20260313_001",
        island="momentum",
        iteration=1,
        hypothesis="价格动量延续效应",
        economic_intuition="市场参与者的追涨行为导致短期趋势延续",
        proposed_formula="Ref($close, -5) / Ref($close, -20) - 1",
        final_formula="Ref($close, -5) / Ref($close, -20) - 1",
        universe="csi300",
        holding_period=5,
        risk_factors=["市场反转"],
        market_context_date="2026-03-13",
    )

    spec = StrategySpec(
        spec_id=f"spec_{note.note_id}",
        hypothesis_id=f"hyp_{note.note_id}",
        factor_expression=note.final_formula or note.proposed_formula,
        universe=note.universe,
        benchmark="SH000300",
        freq="day",
        holding_period=note.holding_period,
        required_fields=["$close"],
    )

    assert spec.spec_id == "spec_momentum_20260313_001"
    assert spec.hypothesis_id == "hyp_momentum_20260313_001"
    assert spec.factor_expression == "Ref($close, -5) / Ref($close, -20) - 1"
    assert spec.universe == "csi300"
    assert spec.holding_period == 5


def test_note_with_exploration_questions():
    note = FactorResearchNote(
        note_id="vol_20260313_001",
        island="volatility",
        iteration=1,
        hypothesis="波动率均值回归",
        economic_intuition="极端波动后市场趋于平静",
        proposed_formula="Std($close, 20)",
        exploration_questions=[
            ExplorationQuestion(
                question="波动率在不同市场环境下的表现如何？",
                suggested_analysis="ic_by_regime",
                required_fields=["$close", "$volume"],
            )
        ],
        risk_factors=["持续高波动"],
        market_context_date="2026-03-13",
    )

    assert len(note.exploration_questions) == 1
    assert note.exploration_questions[0].suggested_analysis == "ic_by_regime"
    assert note.status == "draft"


def test_note_lifecycle_status():
    note = FactorResearchNote(
        note_id="test_001",
        island="momentum",
        iteration=1,
        hypothesis="测试假设",
        economic_intuition="测试原理",
        proposed_formula="$close",
        risk_factors=[],
        market_context_date="2026-03-13",
    )

    assert note.status == "draft"

    note.status = "exploring"
    assert note.status == "exploring"

    note.final_formula = "$close / Ref($close, -1) - 1"
    note.status = "ready_for_backtest"
    assert note.status == "ready_for_backtest"
    assert note.final_formula is not None


def test_bridge_preserves_all_information():
    note = FactorResearchNote(
        note_id="complete_001",
        island="valuation",
        iteration=2,
        hypothesis="低估值修复",
        economic_intuition="价值回归原理",
        proposed_formula="$pe_ratio",
        final_formula="1 / $pe_ratio",
        universe="csi300",
        holding_period=10,
        backtest_start="2021-06-01",
        backtest_end="2025-03-31",
        expected_ic_min=0.03,
        risk_factors=["估值陷阱", "行业轮动"],
        inspired_by="价值投资理论",
        market_context_date="2026-03-13",
        status="ready_for_backtest",
    )

    hyp = Hypothesis(
        hypothesis_id=f"hyp_{note.note_id}",
        island=note.island,
        mechanism=note.hypothesis,
        economic_rationale=note.economic_intuition,
        inspirations=[note.inspired_by] if note.inspired_by else [],
        failure_priors=note.risk_factors,
    )

    spec = StrategySpec(
        spec_id=f"spec_{note.note_id}",
        hypothesis_id=hyp.hypothesis_id,
        factor_expression=note.final_formula or note.proposed_formula,
        universe=note.universe,
        benchmark="SH000300",
        freq="day",
        holding_period=note.holding_period,
        required_fields=["$pe_ratio"],
    )

    assert hyp.mechanism == note.hypothesis
    assert hyp.economic_rationale == note.economic_intuition
    assert spec.factor_expression == note.final_formula
    assert spec.holding_period == note.holding_period
    assert len(hyp.failure_priors) == len(note.risk_factors)


# ─────────────────────────────────────────────────────────
# From test_stage2_hypothesis_output.py
# ─────────────────────────────────────────────────────────

def _make_note_for_output(island: str, suffix: str) -> FactorResearchNote:
    return FactorResearchNote(
        note_id=f"{island}_2026_{suffix}",
        island=island,
        iteration=1,
        hypothesis=f"{island} 假设 {suffix}",
        economic_intuition=f"{island} 经济直觉 {suffix}",
        proposed_formula="Ref($close, -5) / Ref($close, -20) - 1",
        risk_factors=["市场反转"],
        market_context_date="2026-03-16",
        inspired_by=f"来源_{suffix}",
        exploration_subspace=ExplorationSubspace.FACTOR_ALGEBRA,
    )


def _make_batch_for_output(island: str) -> AlphaResearcherBatch:
    return AlphaResearcherBatch(
        island=island,
        notes=[_make_note_for_output(island, "aaa"), _make_note_for_output(island, "bbb")],
        generation_rationale=f"{island} 测试 batch",
    )


def _patch_researcher_and_run(active_islands: list[str]) -> dict:
    from src.agents.researcher import hypothesis_gen_node

    with patch("src.agents.researcher.AlphaResearcher") as MockResearcher:
        def make_instance(island, **kwargs):
            instance = MagicMock()
            instance.generate_batch = AsyncMock(return_value=_make_batch_for_output(island))
            return instance

        MockResearcher.side_effect = make_instance

        state = {
            "active_islands": active_islands,
            "market_context": None,
            "iteration": 1,
        }
        return hypothesis_gen_node(state)


class TestHypothesisGenNodeOutput:

    ISLANDS = ["momentum", "volatility"]

    def test_state_contains_all_three_keys(self):
        result = _patch_researcher_and_run(self.ISLANDS)
        assert "research_notes" in result
        assert "hypotheses" in result
        assert "strategy_specs" in result

    def test_counts_match(self):
        result = _patch_researcher_and_run(self.ISLANDS)
        n_notes = len(result["research_notes"])
        assert n_notes > 0
        assert len(result["hypotheses"]) == n_notes
        assert len(result["strategy_specs"]) == n_notes

    def test_hypothesis_types(self):
        result = _patch_researcher_and_run(self.ISLANDS)
        for hyp in result["hypotheses"]:
            assert isinstance(hyp, Hypothesis)

    def test_strategy_spec_types(self):
        result = _patch_researcher_and_run(self.ISLANDS)
        for spec in result["strategy_specs"]:
            assert isinstance(spec, StrategySpec)

    def test_hypothesis_id_format(self):
        result = _patch_researcher_and_run(self.ISLANDS)
        for hyp in result["hypotheses"]:
            assert hyp.hypothesis_id.startswith("hyp_")

    def test_strategy_spec_id_format(self):
        result = _patch_researcher_and_run(self.ISLANDS)
        for spec in result["strategy_specs"]:
            assert spec.spec_id.startswith("spec_")

    def test_hypothesis_links_to_spec(self):
        result = _patch_researcher_and_run(self.ISLANDS)
        for hyp, spec in zip(result["hypotheses"], result["strategy_specs"]):
            assert hyp.hypothesis_id == spec.hypothesis_id

    def test_research_notes_preserved(self):
        result = _patch_researcher_and_run(self.ISLANDS)
        for note in result["research_notes"]:
            assert isinstance(note, FactorResearchNote)

    def test_hypothesis_fields_populated(self):
        result = _patch_researcher_and_run(self.ISLANDS)
        for hyp, note in zip(result["hypotheses"], result["research_notes"]):
            assert hyp.island == note.island
            assert hyp.mechanism == note.hypothesis
            assert hyp.economic_rationale == note.economic_intuition

    def test_strategy_spec_fields_populated(self):
        result = _patch_researcher_and_run(self.ISLANDS)
        for spec, note in zip(result["strategy_specs"], result["research_notes"]):
            assert spec.factor_expression == note.proposed_formula
            assert spec.universe == note.universe

    def test_single_island(self):
        result = _patch_researcher_and_run(["momentum"])
        expected = SubspaceScheduler.TOTAL_QUOTA * 2
        assert len(result["research_notes"]) == expected
        assert len(result["hypotheses"]) == expected
        assert len(result["strategy_specs"]) == expected

    def test_many_islands(self):
        islands = ["momentum", "volatility", "volume", "value"]
        result = _patch_researcher_and_run(islands)
        expected = SubspaceScheduler.TOTAL_QUOTA * 2
        assert len(result["research_notes"]) == expected
        assert len(result["hypotheses"]) == expected
        assert len(result["strategy_specs"]) == expected

    def test_inspired_by_preserved_in_hypothesis(self):
        result = _patch_researcher_and_run(self.ISLANDS)
        for hyp, note in zip(result["hypotheses"], result["research_notes"]):
            if note.inspired_by:
                assert note.inspired_by in hyp.inspirations

    def test_risk_factors_preserved_in_hypothesis(self):
        result = _patch_researcher_and_run(self.ISLANDS)
        for hyp, note in zip(result["hypotheses"], result["research_notes"]):
            assert hyp.failure_priors == note.risk_factors

    def test_exploration_subspace_preserved_in_hypothesis(self):
        result = _patch_researcher_and_run(self.ISLANDS)
        for hyp, note in zip(result["hypotheses"], result["research_notes"]):
            assert hyp.exploration_subspace == note.exploration_subspace
