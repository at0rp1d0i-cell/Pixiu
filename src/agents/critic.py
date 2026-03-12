"""
Compatibility shims for legacy Stage 5 imports.

Canonical deterministic Stage 5 runtime lives in `src.agents.judgment`.
This module remains only for old tests and historical scripts that still
expect `_parse_metrics`, `_evaluate`, `critic_node`, or `Critic` here.
"""

from __future__ import annotations

import json
import re

from src.agents.judgment import Critic as CanonicalCritic
from src.agents.schemas import BacktestMetrics as LegacyBacktestMetrics
from src.schemas.thresholds import THRESHOLDS


class Critic(CanonicalCritic):
    """Compatibility alias to the canonical Stage 5 critic."""


def _parse_metrics(log: str) -> LegacyBacktestMetrics:
    """
    Legacy helper kept for `tests/test_structured_output.py`.

    Supports:
    - `BACKTEST_METRICS_JSON: {...}`
    - simple regex fallback on human-readable logs
    """
    if not log:
        return LegacyBacktestMetrics(parse_success=False)

    for line in log.splitlines():
        if not line.startswith("BACKTEST_METRICS_JSON:"):
            continue
        try:
            payload = json.loads(line.replace("BACKTEST_METRICS_JSON:", "", 1).strip())
            return LegacyBacktestMetrics(
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
        return LegacyBacktestMetrics(parse_success=False, raw_log_tail=log[-500:])

    return LegacyBacktestMetrics(
        sharpe=values.get("sharpe", 0.0),
        ic=values.get("ic", 0.0),
        icir=values.get("icir", 0.0),
        turnover=values.get("turnover", 0.0),
        parse_success=True,
        raw_log_tail=log[-500:],
    )


def _evaluate(metrics: LegacyBacktestMetrics, has_error: bool) -> tuple[str, str]:
    """Legacy helper kept for compatibility with older structured-output tests."""
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
    """Legacy compatibility node for older state-dict based flows."""
    log = state.get("backtest_log", "") or state.get("stdout", "")
    metrics = _parse_metrics(log)
    route, reason = _evaluate(metrics, bool(state.get("error_message")))
    return {
        "backtest_metrics": metrics,
        "route_decision": route,
        "critic_reason": reason,
    }
