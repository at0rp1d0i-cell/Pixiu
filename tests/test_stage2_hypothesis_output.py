"""
Stage 2: hypothesis_gen_node 产出 Hypothesis + StrategySpec 验证测试

验证 hypothesis_gen_node 返回的 state 同时包含：
  - research_notes: list[FactorResearchNote]（原有，保持兼容）
  - hypotheses: list[Hypothesis]（新增，bridge 转换）
  - strategy_specs: list[StrategySpec]（新增，bridge 转换）
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.schemas.research_note import FactorResearchNote, AlphaResearcherBatch
from src.schemas.hypothesis import Hypothesis, StrategySpec, ExplorationSubspace
from src.scheduling.subspace_scheduler import SubspaceScheduler


# ─────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────

def _make_note(island: str, suffix: str) -> FactorResearchNote:
    """构造一个最小合法 FactorResearchNote。"""
    return FactorResearchNote(
        note_id=f"{island}_2026_{suffix}",
        island=island,
        iteration=1,
        hypothesis=f"{island} 假设 {suffix}",
        economic_intuition=f"{island} 经济直觉 {suffix}",
        proposed_formula=f"Ref($close, -5) / Ref($close, -20) - 1",
        risk_factors=["市场反转"],
        market_context_date="2026-03-16",
        inspired_by=f"来源_{suffix}",
        exploration_subspace=ExplorationSubspace.FACTOR_ALGEBRA,
    )


def _make_batch(island: str) -> AlphaResearcherBatch:
    """构造一个包含 2 个 notes 的 batch。"""
    return AlphaResearcherBatch(
        island=island,
        notes=[_make_note(island, "aaa"), _make_note(island, "bbb")],
        generation_rationale=f"{island} 测试 batch",
    )


def _patch_researcher_and_run(active_islands: list[str]) -> dict:
    """Mock AlphaResearcher，运行 hypothesis_gen_node 并返回结果 state。"""
    from src.agents.researcher import hypothesis_gen_node

    with patch("src.agents.researcher.AlphaResearcher") as MockResearcher:
        def make_instance(island, **kwargs):
            instance = MagicMock()
            instance.generate_batch = AsyncMock(return_value=_make_batch(island))
            return instance

        MockResearcher.side_effect = make_instance

        state = {
            "active_islands": active_islands,
            "market_context": None,
            "iteration": 1,
        }
        return hypothesis_gen_node(state)


# ─────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────

class TestHypothesisGenNodeOutput:
    """hypothesis_gen_node 应同时产出 research_notes, hypotheses, strategy_specs。"""

    ISLANDS = ["momentum", "volatility"]

    def test_state_contains_all_three_keys(self):
        """返回的 state 必须包含 research_notes, hypotheses, strategy_specs 三个 key。"""
        result = _patch_researcher_and_run(self.ISLANDS)

        assert "research_notes" in result, "缺少 research_notes key"
        assert "hypotheses" in result, "缺少 hypotheses key"
        assert "strategy_specs" in result, "缺少 strategy_specs key"

    def test_counts_match(self):
        """hypotheses 和 strategy_specs 的数量应与 research_notes 一致。"""
        result = _patch_researcher_and_run(self.ISLANDS)

        n_notes = len(result["research_notes"])
        assert n_notes > 0, "research_notes 不应为空"
        assert len(result["hypotheses"]) == n_notes, (
            f"hypotheses 数量 ({len(result['hypotheses'])}) != research_notes 数量 ({n_notes})"
        )
        assert len(result["strategy_specs"]) == n_notes, (
            f"strategy_specs 数量 ({len(result['strategy_specs'])}) != research_notes 数量 ({n_notes})"
        )

    def test_hypothesis_types(self):
        """hypotheses 列表中每个元素都是 Hypothesis 实例。"""
        result = _patch_researcher_and_run(self.ISLANDS)

        for hyp in result["hypotheses"]:
            assert isinstance(hyp, Hypothesis), f"期望 Hypothesis，得到 {type(hyp)}"

    def test_strategy_spec_types(self):
        """strategy_specs 列表中每个元素都是 StrategySpec 实例。"""
        result = _patch_researcher_and_run(self.ISLANDS)

        for spec in result["strategy_specs"]:
            assert isinstance(spec, StrategySpec), f"期望 StrategySpec，得到 {type(spec)}"

    def test_hypothesis_id_format(self):
        """每个 Hypothesis 的 hypothesis_id 应以 'hyp_' 开头。"""
        result = _patch_researcher_and_run(self.ISLANDS)

        for hyp in result["hypotheses"]:
            assert hyp.hypothesis_id.startswith("hyp_"), (
                f"hypothesis_id 格式错误：{hyp.hypothesis_id}，应以 'hyp_' 开头"
            )

    def test_strategy_spec_id_format(self):
        """每个 StrategySpec 的 spec_id 应以 'spec_' 开头。"""
        result = _patch_researcher_and_run(self.ISLANDS)

        for spec in result["strategy_specs"]:
            assert spec.spec_id.startswith("spec_"), (
                f"spec_id 格式错误：{spec.spec_id}，应以 'spec_' 开头"
            )

    def test_hypothesis_links_to_spec(self):
        """每个 Hypothesis 和对应 StrategySpec 的 hypothesis_id 应一致。"""
        result = _patch_researcher_and_run(self.ISLANDS)

        for hyp, spec in zip(result["hypotheses"], result["strategy_specs"]):
            assert hyp.hypothesis_id == spec.hypothesis_id, (
                f"Hypothesis.hypothesis_id ({hyp.hypothesis_id}) != "
                f"StrategySpec.hypothesis_id ({spec.hypothesis_id})"
            )

    def test_research_notes_preserved(self):
        """原有的 research_notes 应保持为 FactorResearchNote 实例列表。"""
        result = _patch_researcher_and_run(self.ISLANDS)

        for note in result["research_notes"]:
            assert isinstance(note, FactorResearchNote), (
                f"期望 FactorResearchNote，得到 {type(note)}"
            )

    def test_hypothesis_fields_populated(self):
        """Hypothesis 的关键字段应从 FactorResearchNote 正确转换。"""
        result = _patch_researcher_and_run(self.ISLANDS)

        for hyp, note in zip(result["hypotheses"], result["research_notes"]):
            assert hyp.island == note.island
            assert hyp.mechanism == note.hypothesis
            assert hyp.economic_rationale == note.economic_intuition

    def test_strategy_spec_fields_populated(self):
        """StrategySpec 的关键字段应从 FactorResearchNote 正确转换。"""
        result = _patch_researcher_and_run(self.ISLANDS)

        for spec, note in zip(result["strategy_specs"], result["research_notes"]):
            assert spec.factor_expression == note.proposed_formula
            assert spec.universe == note.universe

    def test_single_island(self):
        """单个 Island 场景：所有配额映射到同一 island。"""
        result = _patch_researcher_and_run(["momentum"])

        # scheduler 分配 TOTAL_QUOTA=12 个任务，每个 batch 2 notes
        expected = SubspaceScheduler.TOTAL_QUOTA * 2
        assert len(result["research_notes"]) == expected
        assert len(result["hypotheses"]) == expected
        assert len(result["strategy_specs"]) == expected

    def test_many_islands(self):
        """多 Island 场景：配额 round-robin 分配到各 island。"""
        islands = ["momentum", "volatility", "volume", "value"]
        result = _patch_researcher_and_run(islands)

        # scheduler 分配 TOTAL_QUOTA=12 个任务，每个 batch 2 notes
        expected = SubspaceScheduler.TOTAL_QUOTA * 2
        assert len(result["research_notes"]) == expected
        assert len(result["hypotheses"]) == expected
        assert len(result["strategy_specs"]) == expected

    def test_inspired_by_preserved_in_hypothesis(self):
        """FactorResearchNote 的 inspired_by 应传递到 Hypothesis.inspirations。"""
        result = _patch_researcher_and_run(self.ISLANDS)

        for hyp, note in zip(result["hypotheses"], result["research_notes"]):
            if note.inspired_by:
                assert note.inspired_by in hyp.inspirations

    def test_risk_factors_preserved_in_hypothesis(self):
        """FactorResearchNote 的 risk_factors 应传递到 Hypothesis.failure_priors。"""
        result = _patch_researcher_and_run(self.ISLANDS)

        for hyp, note in zip(result["hypotheses"], result["research_notes"]):
            assert hyp.failure_priors == note.risk_factors

    def test_exploration_subspace_preserved_in_hypothesis(self):
        """FactorResearchNote 的 exploration_subspace 应传递到 Hypothesis。"""
        result = _patch_researcher_and_run(self.ISLANDS)

        for hyp, note in zip(result["hypotheses"], result["research_notes"]):
            assert hyp.exploration_subspace == note.exploration_subspace
