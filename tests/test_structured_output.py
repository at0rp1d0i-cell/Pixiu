"""验收测试：结构化输出与 Critic 增强（legacy v1 内联版）。"""
import json
import re
import sys
import os
import pytest
from dataclasses import dataclass, field

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.schemas.thresholds import THRESHOLDS


@dataclass
class FactorHypothesis:
    name: str
    formula: str
    hypothesis: str
    rationale: str
    expected_direction: str = "unknown"
    market_observation: str = ""


@dataclass
class BacktestMetrics:
    sharpe: float = 0.0
    annualized_return: float = 0.0
    max_drawdown: float = 0.0
    ic: float = 0.0
    icir: float = 0.0
    turnover: float = 0.0
    win_rate: float = 0.0
    parse_success: bool = False
    raw_log_tail: str = ""


def _parse_metrics(log: str) -> BacktestMetrics:
    if not log:
        return BacktestMetrics(parse_success=False)

    for line in log.splitlines():
        if not line.startswith("BACKTEST_METRICS_JSON:"):
            continue
        try:
            payload = json.loads(line.replace("BACKTEST_METRICS_JSON:", "", 1).strip())
            return BacktestMetrics(
                sharpe=payload.get("sharpe", 0.0),
                annualized_return=payload.get("annualized_return", 0.0),
                max_drawdown=payload.get("max_drawdown", 0.0),
                ic=payload.get("ic", payload.get("ic_mean", 0.0)),
                icir=payload.get("icir", 0.0),
                turnover=payload.get("turnover", payload.get("turnover_rate", 0.0)),
                win_rate=payload.get("win_rate", 0.0),
                parse_success=True,
                raw_log_tail=log[-500:],
            )
        except json.JSONDecodeError:
            break

    patterns = {
        "sharpe": r"(?:夏普比率|Sharpe)\s*[：:]\s*(-?\d+(?:\.\d+)?)",
        "ic": r"(?:IC均值|IC)\s*[：:]\s*(-?\d+(?:\.\d+)?)",
        "icir": r"(?:ICIR)\s*[：:]\s*(-?\d+(?:\.\d+)?)",
        "turnover": r"(?:换手率|Turnover)\s*[：:]\s*(-?\d+(?:\.\d+)?)%?",
    }
    values: dict[str, float] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, log, flags=re.IGNORECASE)
        if match:
            values[key] = float(match.group(1))

    if "sharpe" not in values:
        return BacktestMetrics(parse_success=False, raw_log_tail=log[-500:])

    return BacktestMetrics(
        sharpe=values.get("sharpe", 0.0),
        ic=values.get("ic", 0.0),
        icir=values.get("icir", 0.0),
        turnover=values.get("turnover", 0.0),
        parse_success=True,
        raw_log_tail=log[-500:],
    )


def _evaluate(metrics: BacktestMetrics, has_error: bool) -> tuple[str, str]:
    if has_error:
        return "loop", "执行异常，需要重试"
    if not metrics.parse_success:
        return "loop", "指标解析失败，需要重试"
    if metrics.sharpe < THRESHOLDS.min_sharpe:
        return "loop", "Sharpe 未通过"
    if metrics.ic < THRESHOLDS.min_ic_mean:
        return "loop", "IC 未通过"
    if metrics.icir < THRESHOLDS.min_icir:
        return "loop", "ICIR 未通过"
    if metrics.turnover > 50.0:
        return "loop", "换手率过高"
    return "end", "通过所有关键阈值检查"


def critic_node(state: dict) -> dict:
    log = state.get("backtest_log", "") or state.get("stdout", "")
    metrics = _parse_metrics(log)
    route, reason = _evaluate(metrics, bool(state.get("error_message")))
    return {
        "backtest_metrics": metrics,
        "route_decision": route,
        "critic_reason": reason,
    }


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
