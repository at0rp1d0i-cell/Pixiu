"""验收测试：结构化输出与 Critic 增强。"""
import json
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.schemas import FactorHypothesis, BacktestMetrics
from src.agents.critic import _parse_metrics, _evaluate, critic_node


# ── Schema 测试 ────────────────────────────────────────────────
class TestFactorHypothesis:
    def test_valid_construction(self):
        h = FactorHypothesis(
            name="northbound_mom_5d",
            formula="Mean($volume, 5) / Ref(Mean($volume, 5), 5)",
            hypothesis="北向资金5日动量因子",
            rationale="外资趋势性行为在A股有预测力",
        )
        assert h.name == "northbound_mom_5d"
        assert h.expected_direction == "unknown"  # 默认值

    def test_missing_required_field(self):
        with pytest.raises(Exception):
            FactorHypothesis(name="test")  # 缺少 formula、hypothesis、rationale


# ── Critic 解析测试 ──────────────────────────────────────────────
class TestMetricsParsing:
    def test_parse_json_format(self):
        log = """
训练完成。
BACKTEST_METRICS_JSON: {"sharpe": 3.12, "ic": 0.045, "icir": 0.58, "turnover": 22.3, "annualized_return": 18.5, "max_drawdown": -12.1, "win_rate": 54.2}
策略运行完毕。
"""
        metrics = _parse_metrics(log)
        assert metrics.parse_success is True
        assert metrics.sharpe == pytest.approx(3.12)
        assert metrics.ic == pytest.approx(0.045)
        assert metrics.icir == pytest.approx(0.58)

    def test_parse_regex_fallback(self):
        log = "夏普比率：2.91\nIC均值：0.038\nICIR：0.52\n换手率：18.5%"
        metrics = _parse_metrics(log)
        assert metrics.parse_success is True
        assert metrics.sharpe == pytest.approx(2.91)

    def test_parse_empty_log(self):
        metrics = _parse_metrics("")
        assert metrics.parse_success is False
        assert metrics.sharpe == 0.0

    def test_parse_no_sharpe(self):
        metrics = _parse_metrics("策略运行完毕，无有效输出。")
        assert metrics.parse_success is False


# ── Critic 评估逻辑测试 ──────────────────────────────────────────
class TestEvaluation:
    def test_all_pass(self):
        m = BacktestMetrics(sharpe=3.1, ic=0.05, icir=0.6, turnover=20.0, parse_success=True)
        route, reason = _evaluate(m, False)
        assert route == "end"
        assert "通过" in reason

    def test_sharpe_too_low(self):
        m = BacktestMetrics(sharpe=2.0, ic=0.05, icir=0.6, turnover=20.0, parse_success=True)
        route, _ = _evaluate(m, False)
        assert route == "loop"

    def test_high_turnover(self):
        m = BacktestMetrics(sharpe=3.5, ic=0.05, icir=0.6, turnover=80.0, parse_success=True)
        route, reason = _evaluate(m, False)
        assert route == "loop"
        assert "换手率" in reason

    def test_low_ic(self):
        m = BacktestMetrics(sharpe=3.5, ic=0.005, icir=0.6, turnover=20.0, parse_success=True)
        route, reason = _evaluate(m, False)
        assert route == "loop"
        assert "IC" in reason

    def test_error_always_loops(self):
        m = BacktestMetrics(sharpe=99.0, parse_success=True)
        route, _ = _evaluate(m, has_error=True)
        assert route == "loop"

    def test_parse_failure_loops(self):
        m = BacktestMetrics(parse_success=False)
        route, _ = _evaluate(m, False)
        assert route == "loop"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
