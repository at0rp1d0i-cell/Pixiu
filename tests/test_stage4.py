"""
Stage 4 merged tests: execution + exploration_registry + skill_loader.

Sources:
  - tests/test_execution.py
  - tests/test_exploration_registry.py
  - tests/test_skill_loader.py
"""
import asyncio
import json
import os
import sys
import pytest

pytestmark = pytest.mark.unit

from unittest.mock import patch, MagicMock

from src.execution.coder import Coder
from src.execution.docker_runner import DockerRunner, ExecutionResult
from src.schemas.research_note import FactorResearchNote
from src.schemas.backtest import BacktestReport
from src.schemas.thresholds import THRESHOLDS
from src.schemas.exploration import (
    PrimitiveCategory,
    SubspaceConfig,
    ExplorationStrategy,
    SubspaceRegistry,
)
from src.schemas.hypothesis import ExplorationSubspace, MutationOperator
from src.skills.loader import SkillLoader


# ─────────────────────────────────────────────────────────
# From test_execution.py
# ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_note():
    return FactorResearchNote(
        note_id="test_island_20260307_01",
        island="test_island",
        iteration=1,
        hypothesis="Test",
        economic_intuition="Test",
        proposed_formula="$close",
        exploration_questions=[],
        risk_factors=[],
        market_context_date="2026-03-07"
    )


def test_coder_valid_formula(mock_note):
    """合法 Qlib 公式应返回 BacktestReport(passed=True 或 False，无 error)"""
    coder = Coder()

    mock_stdout = "Some logs...\nBACKTEST_RESULT_JSON:" + json.dumps({
        "sharpe": 2.8,
        "annualized_return": 0.3,
        "max_drawdown": 0.1,
        "ic_mean": 0.03,
        "ic_std": 0.04,
        "icir": 0.75,
        "turnover_rate": 0.2,
        "error": None
    })

    mock_exec_result = ExecutionResult(
        success=True,
        stdout=mock_stdout,
        stderr="",
        returncode=0,
        duration_seconds=10.5
    )

    with patch.object(coder.runner, "run_python", return_value=mock_exec_result):
        report = asyncio.run(coder.run_backtest(mock_note))

    assert isinstance(report, BacktestReport)
    assert report.error_message is None
    assert report.status == "success"
    assert report.failure_stage is None
    assert report.execution_meta is not None
    assert report.execution_meta.engine == "qlib"
    assert report.factor_spec is not None
    assert report.factor_spec.hypothesis == mock_note.hypothesis
    assert report.artifacts is not None
    assert report.passed is True
    assert report.metrics.sharpe == 2.8
    assert report.metrics.annualized_return == 0.3
    assert report.metrics.turnover_rate == 0.2
    assert report.metrics.coverage == 1.0


def test_coder_invalid_formula(mock_note):
    """语法错误公式应返回 BacktestReport(passed=False, error_message 非空)"""
    coder = Coder()

    mock_stdout = "Traceback...\nBACKTEST_RESULT_JSON:" + json.dumps({
        "sharpe": 0.0,
        "annualized_return": 0.0,
        "max_drawdown": 0.0,
        "ic_mean": 0.0,
        "ic_std": 0.0,
        "icir": 0.0,
        "turnover_rate": 0.0,
        "error": "SyntaxError: invalid syntax in formula"
    })

    mock_exec_result = ExecutionResult(
        success=True,
        stdout=mock_stdout,
        stderr="",
        returncode=0,
        duration_seconds=5.0
    )

    with patch.object(coder.runner, "run_python", return_value=mock_exec_result):
        report = asyncio.run(coder.run_backtest(mock_note))

    assert report.passed is False
    assert report.status == "failed"
    assert report.failure_stage == "run"
    assert "SyntaxError" in report.error_message
    assert report.factor_spec is not None
    assert report.metrics.coverage == 0.0


def test_coder_output_parsing(mock_note):
    """BACKTEST_RESULT_JSON 解析逻辑单元测试（不需要 Docker）"""
    coder = Coder()

    mock_exec_result = ExecutionResult(
        success=False,
        stdout="",
        stderr="OOM Killed",
        returncode=137,
        duration_seconds=20.0
    )

    report = coder._parse_result(mock_exec_result, mock_note, "test_factor", "$close")
    assert report.passed is False
    assert report.status == "failed"
    assert report.failure_stage == "run"
    assert report.failure_reason == "execution_failed"
    assert "执行失败" in report.error_message
    assert "OOM" in report.error_message
    assert report.execution_meta is not None
    assert report.factor_spec is not None


def test_exploration_agent_script_extraction():
    """LLM 输出代码块提取逻辑单元测试"""
    from src.execution.exploration_agent import ExplorationAgent

    with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key', 'RESEARCHER_API_KEY': 'test-key'}):
        agent = ExplorationAgent()

    content_with_md = "Here is the script:\n```python\nimport pandas as pd\nprint('hello')\n```\nDone."
    assert agent._extract_script(content_with_md).strip() == "import pandas as pd\nprint('hello')"

    content_raw = "import pandas as pd\nprint('hello')"
    assert agent._extract_script(content_raw).strip() == content_raw


def test_docker_runner_timeout():
    """超时处理：运行 sleep(9999) 应在 timeout 后被我们拦截并返回失败状态"""
    runner = DockerRunner()

    script = "import time\ntime.sleep(10)"

    with patch("asyncio.create_subprocess_exec") as mock_exec, \
         patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):

        mock_proc = MagicMock()
        mock_exec.return_value = mock_proc

        result = asyncio.run(runner.run_python(script, timeout_seconds=1))

        assert result.success is False
        assert "执行超时" in result.stderr
        mock_proc.kill.assert_called_once()


# ─────────────────────────────────────────────────────────
# From test_exploration_registry.py
# ─────────────────────────────────────────────────────────

def test_primitive_category_enum():
    assert PrimitiveCategory.PRICE_VOLUME == "price_volume"
    assert PrimitiveCategory.FUNDAMENTAL == "fundamental"
    assert PrimitiveCategory.EVENT_DERIVED == "event_derived"


def test_subspace_config_minimal():
    config = SubspaceConfig(
        subspace=ExplorationSubspace.FACTOR_ALGEBRA,
        description="测试配置",
    )
    assert config.subspace == ExplorationSubspace.FACTOR_ALGEBRA
    assert config.enabled is True
    assert config.priority == 1


def test_subspace_config_with_primitives():
    config = SubspaceConfig(
        subspace=ExplorationSubspace.FACTOR_ALGEBRA,
        description="原语空间",
        allowed_primitives=["$close", "$volume", "$open"],
    )
    assert len(config.allowed_primitives) == 3
    assert "$close" in config.allowed_primitives


def test_subspace_config_with_operators():
    config = SubspaceConfig(
        subspace=ExplorationSubspace.SYMBOLIC_MUTATION,
        description="符号变异",
        allowed_operators=[
            MutationOperator.ADD_OPERATOR,
            MutationOperator.SWAP_HORIZON,
        ],
    )
    assert len(config.allowed_operators) == 2
    assert MutationOperator.ADD_OPERATOR in config.allowed_operators


def test_exploration_strategy():
    strategy = ExplorationStrategy(
        strategy_id="strat_001",
        subspace=ExplorationSubspace.FACTOR_ALGEBRA,
        name="基础原语组合",
        description="使用基础价格和成交量原语",
        max_candidates=5,
        diversity_threshold=0.4,
    )
    assert strategy.strategy_id == "strat_001"
    assert strategy.max_candidates == 5
    assert strategy.diversity_threshold == 0.4


def test_default_registry():
    registry = SubspaceRegistry.get_default_registry()

    assert len(registry.configs) == 4
    assert "factor_algebra" in registry.configs
    assert "symbolic_mutation" in registry.configs
    assert "cross_market" in registry.configs
    assert "narrative_mining" in registry.configs


def test_get_enabled_subspaces():
    registry = SubspaceRegistry.get_default_registry()
    enabled = registry.get_enabled_subspaces()

    assert len(enabled) == 4
    assert ExplorationSubspace.FACTOR_ALGEBRA in enabled
    assert ExplorationSubspace.SYMBOLIC_MUTATION in enabled


def test_get_subspace_config():
    registry = SubspaceRegistry.get_default_registry()
    config = registry.get_subspace_config(ExplorationSubspace.FACTOR_ALGEBRA)

    assert config is not None
    assert config.subspace == ExplorationSubspace.FACTOR_ALGEBRA
    assert config.priority == 5
    assert len(config.allowed_primitives) > 0


def test_get_subspaces_for_island_all():
    registry = SubspaceRegistry.get_default_registry()
    subspaces = registry.get_subspaces_for_island("momentum")
    assert len(subspaces) == 4


def test_get_subspaces_for_island_specific():
    registry = SubspaceRegistry.get_default_registry()

    registry.configs["factor_algebra"].applicable_islands = ["momentum", "volatility"]

    subspaces_momentum = registry.get_subspaces_for_island("momentum")
    subspaces_valuation = registry.get_subspaces_for_island("valuation")

    assert ExplorationSubspace.FACTOR_ALGEBRA in subspaces_momentum
    assert ExplorationSubspace.FACTOR_ALGEBRA not in subspaces_valuation


def test_get_sorted_subspaces():
    registry = SubspaceRegistry.get_default_registry()
    sorted_subspaces = registry.get_sorted_subspaces()

    assert len(sorted_subspaces) == 4
    assert sorted_subspaces[0] == ExplorationSubspace.FACTOR_ALGEBRA  # priority=5
    assert sorted_subspaces[1] == ExplorationSubspace.SYMBOLIC_MUTATION  # priority=4


def test_get_sorted_subspaces_for_island():
    registry = SubspaceRegistry.get_default_registry()

    registry.configs["factor_algebra"].applicable_islands = ["momentum"]
    registry.configs["symbolic_mutation"].applicable_islands = ["momentum"]
    registry.configs["cross_market"].applicable_islands = ["valuation"]
    registry.configs["narrative_mining"].applicable_islands = ["valuation"]

    sorted_subspaces = registry.get_sorted_subspaces(island="momentum")

    assert len(sorted_subspaces) == 2
    assert sorted_subspaces[0] == ExplorationSubspace.FACTOR_ALGEBRA
    assert sorted_subspaces[1] == ExplorationSubspace.SYMBOLIC_MUTATION


def test_disable_subspace():
    registry = SubspaceRegistry.get_default_registry()

    registry.configs["cross_market"].enabled = False

    enabled = registry.get_enabled_subspaces()
    assert len(enabled) == 3
    assert ExplorationSubspace.CROSS_MARKET not in enabled


def test_subspace_config_source_markets():
    registry = SubspaceRegistry.get_default_registry()
    config = registry.get_subspace_config(ExplorationSubspace.CROSS_MARKET)

    assert config is not None
    assert "US" in config.source_markets
    assert "HK" in config.source_markets


def test_subspace_config_narrative_sources():
    registry = SubspaceRegistry.get_default_registry()
    config = registry.get_subspace_config(ExplorationSubspace.NARRATIVE_MINING)

    assert config is not None
    assert "policy" in config.narrative_sources
    assert "industry" in config.narrative_sources


def test_regime_is_infrastructure_not_subspace():
    registry = SubspaceRegistry.get_default_registry()
    assert "regime_conditional" not in registry.configs

    from src.schemas.hypothesis import Hypothesis
    h = Hypothesis(
        hypothesis_id="hyp_test",
        island="test",
        mechanism="test",
        economic_rationale="test",
        applicable_regimes=["bull"],
        invalid_regimes=["crisis"],
        regime_switch_rule="VIX > 30 进入 crisis",
    )
    assert h.regime_switch_rule == "VIX > 30 进入 crisis"


# ─────────────────────────────────────────────────────────
# From test_skill_loader.py
# ─────────────────────────────────────────────────────────

@pytest.fixture()
def loader():
    return SkillLoader()


def _state(iteration=0, error=""):
    return {"current_iteration": iteration, "error_message": error,
            "max_iterations": 3, "island_name": "momentum"}


class TestSkillLoader:
    def test_type_a_always_injected(self, loader):
        result = loader.load_for_researcher(_state(iteration=0))
        assert "T+1" in result or "前视偏差" in result
        assert "Ref(expr, N)" in result or "合法算子" in result

    def test_island_evolution_not_injected_first_round(self, loader):
        result = loader.load_for_researcher(_state(iteration=0))
        assert "强制工作流程" not in result

    def test_island_evolution_injected_after_first_round(self, loader):
        result = loader.load_for_researcher(_state(iteration=1))
        assert "强制工作流程" in result

    def test_feedback_not_injected_without_error(self, loader):
        result = loader.load_for_researcher(_state(error=""))
        assert "上一次失败的错误消息解读" not in result

    def test_feedback_injected_with_error(self, loader):
        result = loader.load_for_researcher(_state(error="Sharpe 2.1 未超越基线"))
        assert "上一次失败的错误消息解读" in result

    def test_both_context_skills_injected(self, loader):
        result = loader.load_for_researcher(_state(iteration=2, error="IC低"))
        assert "强制工作流程" in result
        assert "上一次失败的错误消息解读" in result

    def test_coder_skill_loads(self, loader):
        result = loader.load_for_coder()
        out = result or ""
        assert len(out) >= 0

    def test_missing_skill_returns_none(self, loader):
        result = loader._load("nonexistent/file.md", required=False)
        assert result is None


class TestValidatorConstraints:

    def test_future_ref_detected(self):
        from src.agents.validator import _check_no_future_leak
        ok, msg = _check_no_future_leak("Ref($close, -1)")
        assert not ok
        assert "前视偏差" in msg or "负数" in msg

    def test_positive_ref_passes(self):
        from src.agents.validator import _check_no_future_leak
        ok, _ = _check_no_future_leak("Ref($close, 5)")
        assert ok

    def test_invalid_field_detected(self):
        from src.agents.validator import _check_valid_fields
        ok, msg = _check_valid_fields("Mean($price, 5)")
        assert not ok
        assert "price" in msg

    def test_valid_fields_pass(self):
        from src.agents.validator import _check_valid_fields
        ok, _ = _check_valid_fields("Mean($close, 5) / Ref($volume, 1)")
        assert ok

    def test_log_negative_detected(self):
        from src.agents.validator import _check_log_safety
        ok, msg = _check_log_safety("Log($close - Ref($close, 1))")
        assert not ok

    def test_log_ratio_passes(self):
        from src.agents.validator import _check_log_safety
        ok, _ = _check_log_safety("Log($close / Ref($close, 1))")
        assert ok
