"""
SubspaceRegistry 默认注册表测试

验证：
- 4 个子空间全部启用
- 原语词汇表非空且覆盖多个类别
- 机制模板非空
- 叙事类别非空
"""
import pytest
from src.schemas.exploration import (
    SubspaceRegistry,
    PrimitiveCategory,
    FactorPrimitive,
    MarketMechanismTemplate,
    NarrativeCategory,
    MutationRecord,
)
from src.schemas.hypothesis import ExplorationSubspace, MutationOperator


@pytest.mark.smoke
class TestSubspaceRegistryDefaults:
    """默认注册表应包含完整的结构化上下文数据。"""

    @pytest.fixture
    def registry(self):
        return SubspaceRegistry.get_default_registry()

    def test_four_subspaces_enabled(self, registry):
        enabled = registry.get_enabled_subspaces()
        assert len(enabled) == 4
        for ss in ExplorationSubspace:
            assert ss in enabled

    def test_primitives_non_empty(self, registry):
        assert len(registry.primitives) >= 15

    def test_primitives_cover_categories(self, registry):
        cats = {p.category for p in registry.primitives}
        assert PrimitiveCategory.PRICE_VOLUME in cats
        assert PrimitiveCategory.FUNDAMENTAL in cats
        assert PrimitiveCategory.TEMPORAL_TRANSFORM in cats

    def test_primitive_fields(self, registry):
        for p in registry.primitives:
            assert isinstance(p, FactorPrimitive)
            assert p.name
            assert p.qlib_syntax
            assert p.description

    def test_mechanism_templates_non_empty(self, registry):
        assert len(registry.mechanism_templates) >= 5

    def test_mechanism_template_fields(self, registry):
        for t in registry.mechanism_templates:
            assert isinstance(t, MarketMechanismTemplate)
            assert t.name
            assert t.source_market
            assert t.transmission_path
            assert t.skeleton

    def test_narrative_categories_non_empty(self, registry):
        assert len(registry.narrative_categories) >= 4

    def test_narrative_category_fields(self, registry):
        for c in registry.narrative_categories:
            assert isinstance(c, NarrativeCategory)
            assert c.category
            assert len(c.extraction_targets) > 0
            assert len(c.example_patterns) > 0


@pytest.mark.smoke
class TestMutationRecord:
    """MutationRecord schema 验证。"""

    def test_create_mutation_record(self):
        rec = MutationRecord(
            source_factor_id="f_001",
            operator=MutationOperator.SWAP_HORIZON,
            parameter_change="5日→20日",
            result_formula="Mean($close, 20) / Mean($close, 60) - 1",
        )
        assert rec.operator == MutationOperator.SWAP_HORIZON
        assert "20日" in rec.parameter_change
