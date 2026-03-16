"""
Subspace Context Builders 测试

验证：
- 4 个 context builder 输出非空结构化字符串
- dispatcher 路由正确
- 输出包含关键内容标记
"""
import pytest
from src.schemas.exploration import SubspaceRegistry
from src.schemas.hypothesis import ExplorationSubspace
from src.scheduling.subspace_context import (
    build_factor_algebra_context,
    build_symbolic_mutation_context,
    build_cross_market_context,
    build_narrative_mining_context,
    build_subspace_context,
)


@pytest.fixture
def registry():
    return SubspaceRegistry.get_default_registry()


@pytest.mark.smoke
class TestContextBuilders:

    def test_factor_algebra_non_empty(self, registry):
        ctx = build_factor_algebra_context(registry, "momentum")
        assert len(ctx) > 100
        assert "原语" in ctx or "primitive" in ctx.lower()
        assert "$close" in ctx

    def test_symbolic_mutation_non_empty(self, registry):
        ctx = build_symbolic_mutation_context(registry, None, "momentum")
        assert len(ctx) > 100
        assert "变异" in ctx or "mutation" in ctx.lower()

    def test_cross_market_non_empty(self, registry):
        ctx = build_cross_market_context(registry)
        assert len(ctx) > 100
        assert "跨市场" in ctx or "cross" in ctx.lower()
        # 应包含至少一个模板名称
        assert "库存周期" in ctx or "利率" in ctx

    def test_narrative_mining_non_empty(self, registry):
        ctx = build_narrative_mining_context(registry)
        assert len(ctx) > 100
        assert "叙事" in ctx or "narrative" in ctx.lower()
        assert "政策" in ctx


@pytest.mark.smoke
class TestDispatcher:

    def test_routes_all_subspaces(self, registry):
        for ss in ExplorationSubspace:
            ctx = build_subspace_context(ss, registry, island="momentum")
            assert len(ctx) > 50, f"{ss.value} context too short"

    def test_factor_algebra_route(self, registry):
        ctx = build_subspace_context(ExplorationSubspace.FACTOR_ALGEBRA, registry, island="momentum")
        assert "因子代数" in ctx

    def test_symbolic_mutation_route(self, registry):
        ctx = build_subspace_context(ExplorationSubspace.SYMBOLIC_MUTATION, registry, island="momentum")
        assert "符号变异" in ctx

    def test_cross_market_route(self, registry):
        ctx = build_subspace_context(ExplorationSubspace.CROSS_MARKET, registry, island="momentum")
        assert "跨市场" in ctx

    def test_narrative_mining_route(self, registry):
        ctx = build_subspace_context(ExplorationSubspace.NARRATIVE_MINING, registry, island="momentum")
        assert "叙事" in ctx
