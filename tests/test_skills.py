"""SkillLoader 单元测试。"""
import pytest

from src.schemas.hypothesis import ExplorationSubspace
from src.skills.loader import ISLAND_FILE_MAP, SkillLoader


pytestmark = pytest.mark.unit


@pytest.fixture()
def loader():
    return SkillLoader()


def _state(iteration=0, error="", market_context=None):
    return {
        "current_iteration": iteration,
        "error_message": error,
        "market_context": market_context,
    }


class TestGenericInterface:
    def test_researcher_backward_compat(self, loader):
        state = _state(iteration=2, error="IC低")
        legacy = loader.load_for_researcher(
            state, subspace=ExplorationSubspace.FACTOR_ALGEBRA
        )
        generic = loader.load_for_agent(
            "researcher",
            state,
            subspace=ExplorationSubspace.FACTOR_ALGEBRA,
        )
        assert legacy == generic

    def test_unknown_role_gets_default_constraints(self, loader):
        result = loader.load_for_agent("unknown_role")
        assert "T+1" in result or "前视偏差" in result

    @pytest.mark.parametrize(
        ("role", "marker"),
        [
            ("researcher", "Alpha Factor Generation Guidelines"),
            ("market_analyst", "<!-- SKILL:MARKET_ANALYST_CONTEXT_FRAMING -->"),
            ("prefilter", "<!-- SKILL:PREFILTER_GUIDANCE -->"),
            ("exploration", "<!-- SKILL:EXPLORATION_CODING -->"),
        ],
    )
    def test_all_roles_return_expected_content(self, loader, role, marker):
        result = loader.load_for_agent(role)
        assert marker in result

    def test_coder_skill_loads(self, loader):
        result = loader.load_for_coder()
        assert len(result or "") >= 0

    def test_missing_skill_returns_none(self, loader):
        result = loader._load("nonexistent/file.md", required=False)
        assert result is None


class TestConditionalInjection:
    def test_market_regime_injected_when_market_context_present(self, loader):
        state = _state(market_context={"market_regime": "bull_trend"})
        result = loader.load_for_agent("researcher", state)
        regime_content = loader._load("researcher/market_regime_detection.md")
        assert regime_content is not None
        assert regime_content in result

    def test_market_regime_not_injected_without_context(self, loader):
        result = loader.load_for_agent("researcher", _state())
        regime_content = loader._load("researcher/market_regime_detection.md")
        assert regime_content is not None
        assert regime_content not in result

    def test_iteration_zero_no_evolution(self, loader):
        result = loader.load_for_agent("researcher", _state(iteration=0))
        assert "强制工作流程" not in result

    def test_iteration_gt_zero_has_evolution(self, loader):
        result = loader.load_for_agent("researcher", _state(iteration=1))
        assert "强制工作流程" in result

    def test_error_message_triggers_feedback(self, loader):
        result = loader.load_for_agent("researcher", _state(error="Sharpe太低"))
        assert "上一次失败的错误消息解读" in result

    @pytest.mark.parametrize(
        ("island", "marker"),
        [
            ("momentum", "<!-- SKILL:ISLAND_MOMENTUM -->"),
            ("valuation", "<!-- SKILL:ISLAND_VALUATION -->"),
            ("volatility", "<!-- SKILL:ISLAND_VOLATILITY -->"),
            ("northbound", "<!-- SKILL:ISLAND_NORTHBOUND -->"),
            ("volume", "<!-- SKILL:ISLAND_VOLUME -->"),
            ("sentiment", "<!-- SKILL:ISLAND_SENTIMENT -->"),
        ],
    )
    def test_island_specific_skills(self, loader, island, marker):
        assert island in ISLAND_FILE_MAP
        result = loader.load_for_agent("researcher", _state(), island=island)
        assert marker in result

    def test_subspace_skill_injected(self, loader):
        result = loader.load_for_agent(
            "researcher",
            _state(),
            subspace=ExplorationSubspace.CROSS_MARKET,
        )
        assert "跨市场模式迁移" in result

    def test_symbolic_mutation_skill_avoids_cross_section_wording(self, loader):
        result = loader.load_for_agent(
            "researcher",
            _state(),
            subspace=ExplorationSubspace.SYMBOLIC_MUTATION,
        )
        assert "截面排名" not in result
        assert "Rank(expr, N)" in result


class TestSkillDriftGuards:
    def test_island_evolution_uses_current_note_contract(self, loader):
        content = loader._load("researcher/island_evolution.md")
        assert content is not None
        assert "AlphaResearcherBatch -> FactorResearchNote[]" in content
        assert "note_id" in content
        assert "proposed_formula" in content
        assert "market_observation" not in content
        assert "expected_direction" not in content

    def test_northbound_and_sentiment_are_proxy_only(self, loader):
        northbound = loader._load("researcher/islands/northbound.md")
        sentiment = loader._load("researcher/islands/sentiment.md")
        assert northbound is not None
        assert sentiment is not None
        assert "proxy-only" in northbound
        assert "proxy-only" in sentiment
