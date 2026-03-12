"""
Stage 3 PreFilter TDD Tests
按照 `docs/design/stage-3-prefilter.md` 的测试要求编写。
"""
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from src.schemas.research_note import FactorResearchNote
from src.agents.prefilter import Validator, NoveltyFilter, AlignmentChecker, PreFilter


def _make_note(**kwargs) -> FactorResearchNote:
    defaults = dict(
        note_id="momentum_2026_test",
        island="momentum",
        iteration=1,
        hypothesis="价格动量因子假设，趋势延续效应",
        economic_intuition="过去表现良好的股票将继续表现良好",
        proposed_formula="Mean($close, 5) / Mean($close, 20) - 1",
        risk_factors=["市场反转"],
        market_context_date="2026-03-08",
    )
    defaults.update(kwargs)
    return FactorResearchNote(**defaults)


# ─────────────────────────────────────────────
# Validator Tests
# ─────────────────────────────────────────────

def test_validator_valid_formula():
    """合法公式应通过"""
    note = _make_note(proposed_formula="Mean($close, 5) / Mean($close, 20) - 1")
    v = Validator()
    passed, reason = v.validate(note)
    assert passed, reason


def test_validator_future_ref_rejected():
    """Ref($close, -N) 是未来数据，必须被拒绝"""
    note = _make_note(proposed_formula="Ref($close, -5) / $close - 1")
    v = Validator()
    passed, reason = v.validate(note)
    assert not passed
    assert "偏移量" in reason


def test_validator_invalid_field_rejected():
    """未注册字段名应被拒绝"""
    note = _make_note(proposed_formula="Mean($earnings_per_share, 5)")
    v = Validator()
    passed, reason = v.validate(note)
    assert not passed
    assert "字段" in reason


def test_validator_unmatched_parenthesis():
    """括号不匹配应被拒绝"""
    note = _make_note(proposed_formula="Mean($close, 5")
    v = Validator()
    passed, reason = v.validate(note)
    assert not passed
    assert "括号" in reason


def test_validator_invalid_operator():
    """未批准算子应被拒绝"""
    note = _make_note(proposed_formula="FancyNN($close, 10)")
    v = Validator()
    passed, reason = v.validate(note)
    assert not passed
    assert "算子" in reason


def test_validator_log_without_protection():
    """Log() 参数未添加 +1 保护应被拒绝"""
    note = _make_note(proposed_formula="Log($close / Ref($close, 5))")
    v = Validator()
    passed, reason = v.validate(note)
    assert not passed
    assert "Log" in reason


# ─────────────────────────────────────────────
# NoveltyFilter Tests
# ─────────────────────────────────────────────

def test_novelty_filter_identical_formula():
    """与 FactorPool 中完全相同的公式应被拒绝"""
    mock_pool = MagicMock()
    mock_pool.get_island_factors.return_value = [
        {"formula": "Mean($close, 5) / Mean($close, 20) - 1", "factor_id": "existing1"}
    ]
    note = _make_note(proposed_formula="Mean($close, 5) / Mean($close, 20) - 1")
    nf = NoveltyFilter(pool=mock_pool, threshold=0.3)
    passed, reason = nf.check(note)
    assert not passed
    assert "相似度过高" in reason


def test_novelty_filter_similar_formula():
    """相似度超过阈值的公式应被拒绝（细微变体）"""
    mock_pool = MagicMock()
    # 仅改了窗口参数，token 集合仍高度重叠
    mock_pool.get_island_factors.return_value = [
        {"formula": "Mean($close, 5) / Mean($close, 20) - 1", "factor_id": "existing1"}
    ]
    note = _make_note(proposed_formula="Mean($close, 10) / Mean($close, 20) - 1")
    nf = NoveltyFilter(pool=mock_pool, threshold=0.3)
    passed, reason = nf.check(note)
    assert not passed  # 共享了大部分 token


def test_novelty_filter_novel_formula():
    """全新公式（使用完全不同字段）应通过"""
    mock_pool = MagicMock()
    mock_pool.get_island_factors.return_value = [
        {"formula": "Mean($close, 5) / Mean($close, 20) - 1", "factor_id": "existing1"}
    ]
    note = _make_note(proposed_formula="Corr($volume, $close, 30)")
    nf = NoveltyFilter(pool=mock_pool, threshold=0.3)
    passed, reason = nf.check(note)
    assert passed


def test_novelty_filter_empty_pool():
    """FactorPool 为空时应直接通过"""
    mock_pool = MagicMock()
    mock_pool.get_island_factors.return_value = []
    note = _make_note()
    nf = NoveltyFilter(pool=mock_pool)
    passed, reason = nf.check(note)
    assert passed


# ─────────────────────────────────────────────
# AlignmentChecker Tests
# ─────────────────────────────────────────────

def test_alignment_checker_consistent():
    """公式与假设一致时应返回 aligned=True"""
    mock_response = MagicMock()
    mock_response.content = '{"aligned": true, "reason": "公式捕捉了价格动量"}'

    with patch('src.agents.prefilter.ChatOpenAI') as MockLLM:
        mock_chat = MockLLM.return_value
        mock_chat.ainvoke = AsyncMock(return_value=mock_response)
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            checker = AlignmentChecker()
            note = _make_note()
            passed, reason = asyncio.run(checker.check(note))

    assert passed


def test_alignment_checker_failure_graceful():
    """AlignmentChecker LLM 调用失败时应放行（不阻塞流程）"""
    with patch('src.agents.prefilter.ChatOpenAI') as MockLLM:
        mock_chat = MockLLM.return_value
        mock_chat.ainvoke = AsyncMock(side_effect=Exception("网络错误"))
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            checker = AlignmentChecker()
            note = _make_note()
            passed, reason = asyncio.run(checker.check(note))

    assert passed  # 失败时放行
    assert "失败" in reason


# ─────────────────────────────────────────────
# PreFilter Integration Tests
# ─────────────────────────────────────────────

def test_prefilter_top_k_limit():
    """通过的候选数量不超过 THRESHOLDS.stage3_top_k"""
    from src.schemas.thresholds import THRESHOLDS

    mock_pool = MagicMock()
    mock_pool.get_island_factors.return_value = []  # 空 pool，全部过新颖性

    notes = [
        _make_note(
            note_id=f"test_{i}",
            proposed_formula=f"Mean($close, {i+2}) / Mean($close, {i+10}) - 1",
        )
        for i in range(THRESHOLDS.stage3_top_k + 3)  # 产生 8 个，超过 top_k=5
    ]

    mock_response = MagicMock()
    mock_response.content = '{"aligned": true, "reason": "一致"}'

    with patch('src.agents.prefilter.ChatOpenAI') as MockLLM:
        mock_chat = MockLLM.return_value
        mock_chat.ainvoke = AsyncMock(return_value=mock_response)
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            prefilter = PreFilter(factor_pool=mock_pool)
            approved, filtered = asyncio.run(prefilter.filter_batch(notes))

    assert len(approved) <= THRESHOLDS.stage3_top_k


def test_prefilter_empty_result():
    """全部被过滤时（公式使用未来数据），返回空列表不报错"""
    mock_pool = MagicMock()
    mock_pool.get_island_factors.return_value = []

    # 所有 notes 都有 Ref(-N) ← 未来数据，Filter A 必然拒绝
    notes = [
        _make_note(
            note_id=f"bad_{i}",
            proposed_formula=f"Ref($close, -{i+1}) / $close - 1",
        )
        for i in range(3)
    ]

    with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
        prefilter = PreFilter(factor_pool=mock_pool)
        approved, filtered = asyncio.run(prefilter.filter_batch(notes))

    assert approved == []
    assert filtered == 3
