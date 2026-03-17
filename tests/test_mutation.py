"""
tests/test_mutation.py

Unit + smoke tests for:
  - QlibFormulaParser  (AST 解析)
  - SymbolicMutator    (5 种算子确定性变异)
  - researcher SYMBOLIC_MUTATION 纯符号路径
"""
import pytest

from src.hypothesis.mutation import (
    FormulaNode,
    QlibFormulaParser,
    SymbolicMutator,
    MutationResult,
    try_all_mutations,
    build_mutation_record_dict,
)
from src.schemas.hypothesis import MutationOperator, ExplorationSubspace


# ─────────────────────────────────────────────────────────
# QlibFormulaParser — 基本解析
# ─────────────────────────────────────────────────────────

@pytest.mark.smoke
class TestQlibFormulaParserBasic:
    """解析器能正确解析常用 Qlib 公式格式。"""

    def setup_method(self):
        self.parser = QlibFormulaParser()

    def test_parse_field(self):
        node = self.parser.parse("$close")
        assert node is not None
        assert node.op == "$close"
        assert node.args == []

    def test_parse_simple_function(self):
        node = self.parser.parse("Rank($close)")
        assert node is not None
        assert node.op == "Rank"
        assert len(node.args) == 1
        assert node.args[0].op == "$close"

    def test_parse_function_with_window(self):
        node = self.parser.parse("Mean($close, 5)")
        assert node is not None
        assert node.op == "Mean"
        assert len(node.args) == 2
        assert node.args[0].op == "$close"
        assert node.args[1].op == "5"

    def test_parse_nested_function(self):
        node = self.parser.parse("Rank(Mean($close, 20))")
        assert node is not None
        assert node.op == "Rank"
        assert node.args[0].op == "Mean"

    def test_parse_corr_three_args(self):
        node = self.parser.parse("Corr($close, $volume, 10)")
        assert node is not None
        assert node.op == "Corr"
        assert len(node.args) == 3

    def test_roundtrip_simple(self):
        formula = "Mean($close, 5)"
        node = self.parser.parse(formula)
        assert node is not None
        assert node.to_formula() == formula

    def test_roundtrip_nested(self):
        formula = "Rank(Mean($close, 20))"
        node = self.parser.parse(formula)
        assert node is not None
        assert node.to_formula() == formula


# ─────────────────────────────────────────────────────────
# QlibFormulaParser — 中缀运算符快速检测
# ─────────────────────────────────────────────────────────

@pytest.mark.smoke
class TestQlibFormulaParserInfixDetection:
    """包含顶层中缀运算符的公式应返回 None，不 crash。"""

    def setup_method(self):
        self.parser = QlibFormulaParser()

    def test_infix_plus_returns_none(self):
        assert self.parser.parse("$close + $open") is None

    def test_infix_minus_returns_none(self):
        assert self.parser.parse("$close - $open") is None

    def test_infix_mul_returns_none(self):
        assert self.parser.parse("$close * $volume") is None

    def test_infix_div_returns_none(self):
        assert self.parser.parse("Mean($close, 5) / Mean($close, 20)") is None

    def test_nested_infix_inside_function_not_detected_as_toplevel(self):
        # 括号内的中缀运算符不应在顶层被检测到
        # 不过 v1 parser 不解析括号内的中缀，这里验证不 crash
        # 内部中缀会导致 parse 失败，但不应该因 has_toplevel_infix 而误判
        result = self.parser.parse("Rank($close)")
        assert result is not None  # 纯函数调用不含顶层中缀，正常解析

    def test_empty_string_returns_none(self):
        assert self.parser.parse("") is None

    def test_whitespace_only_returns_none(self):
        assert self.parser.parse("   ") is None


# ─────────────────────────────────────────────────────────
# SymbolicMutator — SWAP_HORIZON
# ─────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSwapHorizon:
    """SWAP_HORIZON 算子应将窗口参数替换为相邻候选值。"""

    def setup_method(self):
        self.mutator = SymbolicMutator()

    def test_swap_horizon_changes_window(self):
        result = self.mutator.mutate("Mean($close, 5)", MutationOperator.SWAP_HORIZON)
        assert result is not None
        assert result.result_formula != "Mean($close, 5)"
        # 结果中应包含 $close
        assert "$close" in result.result_formula

    def test_swap_horizon_20_to_larger(self):
        result = self.mutator.mutate("Mean($close, 20)", MutationOperator.SWAP_HORIZON)
        assert result is not None
        assert "40" in result.result_formula or "60" in result.result_formula

    def test_swap_horizon_no_window_returns_none(self):
        # $close 是叶节点，无窗口参数
        result = self.mutator.mutate("$close", MutationOperator.SWAP_HORIZON)
        assert result is None

    def test_swap_horizon_infix_returns_none(self):
        # 中缀公式无法解析，应返回 None
        result = self.mutator.mutate("$close / $open", MutationOperator.SWAP_HORIZON)
        assert result is None

    def test_swap_horizon_result_is_valid_formula(self):
        result = self.mutator.mutate("Std($close, 10)", MutationOperator.SWAP_HORIZON)
        assert result is not None
        # 结果公式应可被重新解析
        parser = QlibFormulaParser()
        re_parsed = parser.parse(result.result_formula)
        assert re_parsed is not None

    def test_swap_horizon_corr(self):
        result = self.mutator.mutate("Corr($close, $volume, 10)", MutationOperator.SWAP_HORIZON)
        assert result is not None
        assert "Corr" in result.result_formula


# ─────────────────────────────────────────────────────────
# SymbolicMutator — CHANGE_NORMALIZATION
# ─────────────────────────────────────────────────────────

@pytest.mark.unit
class TestChangeNormalization:
    """CHANGE_NORMALIZATION 应在 Rank / Zscore / Demean 之间切换。"""

    def setup_method(self):
        self.mutator = SymbolicMutator()

    def test_rank_to_zscore(self):
        result = self.mutator.mutate("Rank($close)", MutationOperator.CHANGE_NORMALIZATION)
        assert result is not None
        assert result.result_formula == "Zscore($close)"

    def test_zscore_to_rank(self):
        result = self.mutator.mutate("Zscore($close)", MutationOperator.CHANGE_NORMALIZATION)
        assert result is not None
        assert result.result_formula == "Rank($close)"

    def test_non_norm_op_returns_none(self):
        result = self.mutator.mutate("Mean($close, 5)", MutationOperator.CHANGE_NORMALIZATION)
        assert result is None

    def test_field_returns_none(self):
        result = self.mutator.mutate("$close", MutationOperator.CHANGE_NORMALIZATION)
        assert result is None


# ─────────────────────────────────────────────────────────
# SymbolicMutator — REMOVE_OPERATOR
# ─────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRemoveOperator:
    """REMOVE_OPERATOR 应剥除最外层函数算子。"""

    def setup_method(self):
        self.mutator = SymbolicMutator()

    def test_remove_rank(self):
        result = self.mutator.mutate("Rank($close)", MutationOperator.REMOVE_OPERATOR)
        assert result is not None
        assert result.result_formula == "$close"

    def test_remove_mean_keeps_inner(self):
        result = self.mutator.mutate("Mean($close, 5)", MutationOperator.REMOVE_OPERATOR)
        assert result is not None
        assert result.result_formula == "$close"

    def test_remove_nested(self):
        result = self.mutator.mutate("Rank(Mean($close, 20))", MutationOperator.REMOVE_OPERATOR)
        assert result is not None
        assert result.result_formula == "Mean($close, 20)"

    def test_remove_leaf_returns_none(self):
        result = self.mutator.mutate("$close", MutationOperator.REMOVE_OPERATOR)
        assert result is None


# ─────────────────────────────────────────────────────────
# SymbolicMutator — ADD_OPERATOR
# ─────────────────────────────────────────────────────────

@pytest.mark.unit
class TestAddOperator:
    """ADD_OPERATOR 应在公式外包裹截面算子。"""

    def setup_method(self):
        self.mutator = SymbolicMutator()

    def test_add_rank_wrapper(self):
        result = self.mutator.mutate("Mean($close, 5)", MutationOperator.ADD_OPERATOR)
        assert result is not None
        assert result.result_formula.startswith("Rank(")
        assert "Mean($close, 5)" in result.result_formula

    def test_rank_wrapped_in_zscore(self):
        # 已有 Rank，再包一层应改为 Zscore
        result = self.mutator.mutate("Rank($close)", MutationOperator.ADD_OPERATOR)
        assert result is not None
        assert result.result_formula == "Zscore($close)"

    def test_add_operator_changes_formula(self):
        result = self.mutator.mutate("$close", MutationOperator.ADD_OPERATOR)
        assert result is not None
        assert result.result_formula != "$close"


# ─────────────────────────────────────────────────────────
# SymbolicMutator — ALTER_INTERACTION
# ─────────────────────────────────────────────────────────

@pytest.mark.unit
class TestAlterInteraction:
    """ALTER_INTERACTION 应添加与成交量的交叉项。"""

    def setup_method(self):
        self.mutator = SymbolicMutator()

    def test_add_volume_interaction(self):
        result = self.mutator.mutate("Mean($close, 5)", MutationOperator.ALTER_INTERACTION)
        assert result is not None
        assert "Mul" in result.result_formula
        assert "$volume" in result.result_formula

    def test_interaction_wraps_in_mul(self):
        result = self.mutator.mutate("Rank($close)", MutationOperator.ALTER_INTERACTION)
        assert result is not None
        assert result.result_formula.startswith("Mul(")

    def test_existing_mul_replaces_second_arg(self):
        result = self.mutator.mutate("Mul($close, $open)", MutationOperator.ALTER_INTERACTION)
        assert result is not None
        assert "$volume" in result.result_formula
        assert result.result_formula != "Mul($close, $open)"


# ─────────────────────────────────────────────────────────
# try_all_mutations 工具函数
# ─────────────────────────────────────────────────────────

@pytest.mark.unit
class TestTryAllMutations:
    """try_all_mutations 应对支持的算子返回非空结果。"""

    def test_rank_produces_multiple_mutations(self):
        results = try_all_mutations("Rank($close)")
        assert len(results) >= 2  # 至少 CHANGE_NORMALIZATION + ADD_OPERATOR + REMOVE_OPERATOR

    def test_mean_with_window_produces_mutations(self):
        results = try_all_mutations("Mean($close, 20)")
        # 至少 SWAP_HORIZON + ADD_OPERATOR + REMOVE_OPERATOR + ALTER_INTERACTION
        assert len(results) >= 3

    def test_infix_formula_produces_no_mutations(self):
        results = try_all_mutations("$close + $open")
        assert len(results) == 0

    def test_all_results_are_mutation_result_type(self):
        results = try_all_mutations("Mean($close, 5)")
        for r in results:
            assert isinstance(r, MutationResult)

    def test_results_have_valid_operators(self):
        results = try_all_mutations("Rank($close)")
        for r in results:
            assert isinstance(r.operator, MutationOperator)
            assert r.source_formula == "Rank($close)"
            assert r.result_formula != r.source_formula


# ─────────────────────────────────────────────────────────
# build_mutation_record_dict
# ─────────────────────────────────────────────────────────

@pytest.mark.unit
class TestBuildMutationRecordDict:
    """build_mutation_record_dict 应生成符合 mutation_record 字段格式的 dict。"""

    def test_dict_has_required_keys(self):
        results = try_all_mutations("Rank($close)")
        assert results, "需要至少一个变异结果"
        d = build_mutation_record_dict(results[0])
        assert "operator" in d
        assert "source_formula" in d
        assert "result_formula" in d
        assert "description" in d

    def test_operator_is_string(self):
        results = try_all_mutations("Mean($close, 5)")
        assert results
        d = build_mutation_record_dict(results[0])
        assert isinstance(d["operator"], str)


# ─────────────────────────────────────────────────────────
# AlphaResearcher 纯符号路径集成测试
# ─────────────────────────────────────────────────────────

@pytest.mark.unit
class TestResearcherSymbolicPath:
    """AlphaResearcher._try_symbolic_mutation_batch 有 seed 时应纯符号生成。"""

    def test_symbolic_batch_with_seeds(self):
        """当 FactorPool 中有种子因子时，应返回非空 batch，不调 LLM。"""
        from unittest.mock import MagicMock
        from src.agents.researcher import AlphaResearcher

        # Mock FactorPool：返回两个已知公式
        mock_pool = MagicMock()
        mock_pool.get_island_best_factors.return_value = [
            {"formula": "Mean($close, 5)"},
            {"formula": "Rank($close)"},
        ]

        researcher = AlphaResearcher(island="momentum", factor_pool=mock_pool)
        batch = researcher._try_symbolic_mutation_batch(iteration=1)

        assert batch is not None
        assert len(batch.notes) > 0
        assert batch.island == "momentum"
        # 所有 note 的 exploration_subspace 应为 SYMBOLIC_MUTATION
        for note in batch.notes:
            assert note.exploration_subspace == ExplorationSubspace.SYMBOLIC_MUTATION
            assert note.mutation_record is not None

    def test_symbolic_batch_no_seeds_returns_none(self):
        """当 FactorPool 无种子时，应返回 None（触发 LLM fallback）。"""
        from unittest.mock import MagicMock
        from src.agents.researcher import AlphaResearcher

        mock_pool = MagicMock()
        mock_pool.get_island_best_factors.return_value = []

        researcher = AlphaResearcher(island="momentum", factor_pool=mock_pool)
        batch = researcher._try_symbolic_mutation_batch(iteration=1)

        assert batch is None

    def test_symbolic_batch_pool_exception_returns_none(self):
        """FactorPool 抛异常时应 graceful fallback（返回 None）。"""
        from unittest.mock import MagicMock
        from src.agents.researcher import AlphaResearcher

        mock_pool = MagicMock()
        mock_pool.get_island_best_factors.side_effect = RuntimeError("db error")

        researcher = AlphaResearcher(island="momentum", factor_pool=mock_pool)
        batch = researcher._try_symbolic_mutation_batch(iteration=1)

        assert batch is None

    def test_symbolic_batch_infix_seeds_returns_none(self):
        """当所有种子公式均为中缀表达式（无法变异）时，应返回 None。"""
        from unittest.mock import MagicMock
        from src.agents.researcher import AlphaResearcher

        mock_pool = MagicMock()
        mock_pool.get_island_best_factors.return_value = [
            {"formula": "$close + $open"},
            {"formula": "$high - $low"},
        ]

        researcher = AlphaResearcher(island="momentum", factor_pool=mock_pool)
        batch = researcher._try_symbolic_mutation_batch(iteration=1)

        assert batch is None

    def test_mutation_record_fields_in_note(self):
        """生成的 note 的 mutation_record 应包含必要字段。"""
        from unittest.mock import MagicMock
        from src.agents.researcher import AlphaResearcher

        mock_pool = MagicMock()
        mock_pool.get_island_best_factors.return_value = [
            {"formula": "Mean($close, 20)"},
        ]

        researcher = AlphaResearcher(island="value", factor_pool=mock_pool)
        batch = researcher._try_symbolic_mutation_batch(iteration=2)

        assert batch is not None
        for note in batch.notes:
            rec = note.mutation_record
            assert rec is not None
            assert "operator" in rec
            assert "source_formula" in rec
            assert "result_formula" in rec
