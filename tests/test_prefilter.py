"""
Stage 3 PreFilter TDD Tests
按照 `docs/design/stage-3-prefilter.md` 的测试要求编写。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import asyncio
import pytest

from src.schemas.research_note import FactorResearchNote
from src.agents.prefilter import Validator, NoveltyFilter, AlignmentChecker, PreFilter
from src.formula.capabilities import get_runtime_formula_capabilities

pytestmark = pytest.mark.unit

_TEST_ALLOWED_FIELDS = {"$close", "$open", "$high", "$low", "$volume", "$vwap", "$amount", "$factor", "$roe"}
_TEST_APPROVED_OPERATORS = {"Mean", "Ref", "Log", "Corr", "If", "Gt", "Abs", "Std", "Div", "Sub"}


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


def _make_validator() -> Validator:
    return Validator(
        allowed_fields=set(_TEST_ALLOWED_FIELDS),
        approved_operators=set(_TEST_APPROVED_OPERATORS),
    )


# ─────────────────────────────────────────────
# Validator Tests
# ─────────────────────────────────────────────

def test_validator_valid_formula():
    """合法公式应通过"""
    note = _make_note(proposed_formula="Mean($close, 5) / Mean($close, 20) - 1")
    v = _make_validator()
    passed, reason = v.validate(note)
    assert passed, reason


def test_validator_future_ref_rejected():
    """Ref($close, -N) 是未来数据，必须被拒绝"""
    note = _make_note(proposed_formula="Ref($close, -5) / $close - 1")
    v = _make_validator()
    passed, reason = v.validate(note)
    assert not passed
    assert "偏移量" in reason


def test_validator_invalid_field_rejected():
    """未注册字段名应被拒绝"""
    note = _make_note(proposed_formula="Mean($earnings_per_share, 5)")
    v = _make_validator()
    passed, reason = v.validate(note)
    assert not passed
    assert "字段" in reason


def test_validator_unmatched_parenthesis():
    """括号不匹配应被拒绝"""
    note = _make_note(proposed_formula="Mean($close, 5")
    v = _make_validator()
    passed, reason = v.validate(note)
    assert not passed
    assert "括号" in reason


def test_validator_invalid_operator():
    """未批准算子应被拒绝"""
    note = _make_note(proposed_formula="FancyNN($close, 10)")
    v = _make_validator()
    passed, reason = v.validate(note)
    assert not passed
    assert "FancyNN" in reason


def test_validator_rejects_missing_mean_window():
    """Mean() 少参数时应被拒绝"""
    note = _make_note(proposed_formula="Mean($close)")
    v = _make_validator()
    passed, reason = v.validate(note)
    assert not passed
    assert "Mean" in reason or "参数数量" in reason


def test_validator_rejects_corr_with_wrong_arity():
    """Corr() 少参数时应被拒绝"""
    note = _make_note(proposed_formula="Corr($close, 5)")
    v = _make_validator()
    passed, reason = v.validate(note)
    assert not passed
    assert "Corr" in reason or "参数数量" in reason


def test_validator_rejects_ref_with_non_numeric_offset():
    """Ref() 第二个参数必须是正整数"""
    note = _make_note(proposed_formula="Ref($close, foo)")
    v = _make_validator()
    passed, reason = v.validate(note)
    assert not passed
    assert not passed


def test_validator_rejects_if_with_wrong_arity():
    """If() 少参数时应被拒绝"""
    note = _make_note(proposed_formula="If($close)")
    v = _make_validator()
    passed, reason = v.validate(note)
    assert not passed
    assert "If" in reason or "参数数量" in reason


def test_validator_log_without_protection():
    """Log() 参数未添加 +1 保护应被拒绝"""
    note = _make_note(proposed_formula="Log($close - Ref($close, 5))")
    v = _make_validator()
    passed, reason = v.validate(note)
    assert not passed
    assert "Log" in reason


def test_validator_accepts_positive_ratio_log():
    """由正值字段构成的比例表达式应允许直接进入 Log()."""
    note = _make_note(proposed_formula="Log($close / Ref($close, 5))")
    v = _make_validator()
    passed, reason = v.validate(note)
    assert passed, reason


def test_validator_accepts_corr_with_window():
    note = _make_note(proposed_formula="Corr($close, $volume, 30)")
    v = _make_validator()
    passed, reason = v.validate(note)
    assert passed, reason


def test_validator_accepts_runtime_available_experimental_field():
    note = _make_note(proposed_formula="Mean($roe, 4)")
    v = _make_validator()
    passed, reason = v.validate(note)
    assert passed, reason


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

    with patch('src.agents.prefilter.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(return_value=mock_response)
        mock_builder.return_value = mock_chat
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            checker = AlignmentChecker()
            note = _make_note()
            passed, reason = asyncio.run(checker.check(note))

    assert passed


def test_alignment_checker_failure_graceful():
    """AlignmentChecker LLM 调用失败时应放行（不阻塞流程）"""
    with patch('src.agents.prefilter.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(side_effect=Exception("网络错误"))
        mock_builder.return_value = mock_chat
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            checker = AlignmentChecker()
            note = _make_note()
            passed, reason = asyncio.run(checker.check(note))

    assert passed  # 失败时放行
    assert "失败" in reason


def test_alignment_checker_injects_prefilter_skill_into_system_prompt():
    """AlignmentChecker 的 LLM system prompt 应包含 prefilter guidance skill。"""
    captured_messages = []

    async def capture_ainvoke(messages):
        captured_messages.append(messages)
        response = MagicMock()
        response.content = '{"aligned": true, "reason": "一致"}'
        return response

    with patch('src.agents.prefilter.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        mock_builder.return_value = mock_chat
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            checker = AlignmentChecker()
            note = _make_note()
            asyncio.run(checker.check(note))

    assert captured_messages
    system_message = captured_messages[0][0]
    assert "<!-- SKILL:PREFILTER_GUIDANCE -->" in system_message.content


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

    with patch('src.agents.prefilter.build_researcher_llm') as mock_builder:
        mock_chat = MagicMock()
        mock_chat.ainvoke = AsyncMock(return_value=mock_response)
        mock_builder.return_value = mock_chat
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'RESEARCHER_API_KEY': 'test'}):
            prefilter = PreFilter(factor_pool=mock_pool, validator=_make_validator())
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
        prefilter = PreFilter(factor_pool=mock_pool, validator=_make_validator())
        approved, filtered = asyncio.run(prefilter.filter_batch(notes))

    assert approved == []
    assert filtered == 3


def test_prefilter_tracks_rejection_diagnostics():
    """PreFilter 应聚合每个过滤器的拒绝计数和样本。"""
    prefilter = PreFilter(factor_pool=MagicMock(), validator=_make_validator())
    notes = [
        _make_note(note_id="reject_validator"),
        _make_note(note_id="reject_alignment"),
        _make_note(note_id="reject_constraint"),
        _make_note(note_id="pass_candidate"),
    ]

    with patch.object(prefilter.validator, "validate") as mock_validate, \
         patch.object(prefilter.novelty, "check") as mock_novelty, \
         patch.object(prefilter.alignment, "check", new_callable=AsyncMock) as mock_alignment, \
         patch.object(prefilter.constraint_checker, "check") as mock_constraint, \
         patch.object(prefilter.regime_filter, "check") as mock_regime:
        mock_validate.side_effect = lambda note: (
            (False, "future ref") if note.note_id == "reject_validator" else (True, "ok")
        )
        mock_novelty.side_effect = lambda note: (True, "ok")
        mock_alignment.side_effect = lambda note: (
            (False, "semantic mismatch") if note.note_id == "reject_alignment" else (True, "ok")
        )
        mock_constraint.side_effect = lambda note: (
            (False, "matched historical failure") if note.note_id == "reject_constraint" else (True, "ok")
        )
        mock_regime.side_effect = lambda note, current_regime: (True, "ok")

        approved, filtered = asyncio.run(
            prefilter.filter_batch(notes, current_regime="bull_trend")
        )

    assert filtered == 3
    assert [note.note_id for note in approved] == ["pass_candidate"]
    assert prefilter.last_diagnostics["input_count"] == 4
    assert prefilter.last_diagnostics["approved_count"] == 1
    assert prefilter.last_diagnostics["rejection_counts_by_filter"] == {
        "validator": 1,
        "alignment": 1,
        "constraint_checker": 1,
    }
    assert len(prefilter.last_diagnostics["sample_rejections"]) == 3
    assert prefilter.last_diagnostics["sample_rejections"][0]["note_id"] == "reject_validator"


def test_prefilter_tracks_top_k_truncation_in_diagnostics(monkeypatch):
    """超过 Top-K 的候选应计入单独的截断拒绝统计。"""
    from src.schemas.thresholds import THRESHOLDS

    monkeypatch.setattr(THRESHOLDS, "stage3_top_k", 2)
    prefilter = PreFilter(factor_pool=MagicMock())
    notes = [
        _make_note(note_id=f"candidate_{i}")
        for i in range(4)
    ]

    with patch.object(prefilter.validator, "validate", return_value=(True, "ok")), \
         patch.object(prefilter.novelty, "check", return_value=(True, "ok")), \
         patch.object(prefilter.alignment, "check", new_callable=AsyncMock, return_value=(True, "ok")), \
         patch.object(prefilter.constraint_checker, "check", return_value=(True, "ok")), \
         patch.object(prefilter.regime_filter, "check", return_value=(True, "ok")):
        approved, filtered = asyncio.run(
            prefilter.filter_batch(notes, current_regime="bull_trend")
        )

    assert filtered == 2
    assert [note.note_id for note in approved] == ["candidate_0", "candidate_1"]
    assert prefilter.last_diagnostics["approved_count"] == 2
    assert prefilter.last_diagnostics["rejection_counts_by_filter"]["top_k_truncation"] == 2
    assert [s["note_id"] for s in prefilter.last_diagnostics["sample_rejections"]] == [
        "candidate_2",
        "candidate_3",
    ]


def test_prefilter_uses_provided_capabilities_without_runtime_rescan():
    capabilities = get_runtime_formula_capabilities()

    with patch("src.agents.prefilter.get_runtime_formula_capabilities", side_effect=AssertionError("should not rescan")):
        prefilter = PreFilter(
            factor_pool=MagicMock(),
            capabilities=capabilities,
        )

    assert set(prefilter.validator.allowed_fields) == set(capabilities.available_fields)
    assert set(prefilter.validator.approved_operators) == set(capabilities.approved_operators)
