# src/execution/templates/qlib_backtest.py.tpl
# 此模板在运行时由 Coder 用字符串格式化填充

import json
import warnings
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import qlib
from pathlib import Path
from qlib.constant import REG_CN
from qlib.data import D

warnings.filterwarnings("ignore")

# ── 由 Coder 填充的参数 ──────────────────────────────────────
FORMULA = "{formula}"
UNIVERSE = "{universe}"       # "csi300" 或 "csi500"
UNIVERSE_NAME = (
    UNIVERSE if Path(f"/data/qlib_bin/instruments/{UNIVERSE}.txt").exists() else "all"
)
START_DATE = "{start_date}"   # "2021-06-01"
END_DATE = "{end_date}"       # "2025-03-31"
TOPK = {topk}                 # 持仓数量，默认 50
# ─────────────────────────────────────────────────────────────

TWELVE_MONTHS = timedelta(days=365)

ZERO_METRICS = {
    "sharpe": 0.0,
    "annualized_return": 0.0,
    "max_drawdown": 0.0,
    "ic_mean": 0.0,
    "ic_std": 0.0,
    "icir": 0.0,
    "turnover_rate": 0.0,
    "coverage": 0.0,
}


def parse_date(date_str: str) -> datetime.date:
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def format_date(date_obj: datetime.date) -> str:
    return date_obj.strftime("%Y-%m-%d")


def build_window(start: str, end: str, coverage: float, notes: str) -> dict:
    return {
        "start_date": start,
        "end_date": end,
        "coverage": coverage,
        "notes": notes,
    }


def compute_metrics(window_start: str, window_end: str) -> dict:
    fields = [FORMULA]
    factor_df = (
        D.features(
            D.instruments(market=UNIVERSE_NAME),
            fields,
            start_time=window_start,
            end_time=window_end,
        )
        .reset_index()
        .rename(columns={fields[0]: "factor"})
    )

    if factor_df.empty:
        return ZERO_METRICS.copy()

    df = factor_df.dropna()
    df["rank"] = df.groupby("datetime")["factor"].rank(ascending=False)

    ret_fields = ["$close/Ref($close,1)-1"]
    ret_df = (
        D.features(
            D.instruments(market=UNIVERSE_NAME),
            ret_fields,
            start_time=window_start,
            end_time=window_end,
        )
        .reset_index()
        .rename(columns={ret_fields[0]: "ret"})
    )
    merged = df.merge(ret_df, on=["instrument", "datetime"], how="left")
    merged["fwd_ret"] = merged.groupby("instrument")["ret"].shift(-1)
    merged = merged.dropna(subset=["fwd_ret"])

    factor_coverage = (
        factor_df.groupby("datetime")["factor"].count()
        / ret_df.groupby("datetime")["ret"].count().replace(0, np.nan)
    ).replace([np.inf, -np.inf], np.nan).dropna()
    coverage = float(factor_coverage.mean()) if len(factor_coverage) > 0 else 0.0

    ic_series = merged.groupby("datetime").apply(lambda x: x["factor"].corr(x["fwd_ret"])).dropna()
    ic_mean = float(ic_series.mean()) if len(ic_series) > 0 else 0.0
    ic_std = float(ic_series.std()) if len(ic_series) > 0 else 0.0
    icir = float(ic_mean / ic_std) if ic_std > 0 else 0.0

    daily_returns = []
    for dt, group in merged.groupby("datetime"):
        top = group.nsmallest(TOPK, "rank")["fwd_ret"]
        daily_returns.append(top.mean())

    daily_ret = pd.Series(daily_returns).dropna()
    annualized_return = float(daily_ret.mean() * 252) if len(daily_ret) > 0 else 0.0
    annualized_std = float(daily_ret.std() * (252 ** 0.5)) if len(daily_ret) > 1 else 0.0
    sharpe = float(annualized_return / annualized_std) if annualized_std > 0 else 0.0
    max_drawdown = float((daily_ret.cumsum() - daily_ret.cumsum().cummax()).min()) if len(daily_ret) > 0 else 0.0

    dates = sorted(merged["datetime"].unique())
    turnovers = []
    prev_set = set()
    for dt in dates:
        curr_set = set(merged[merged["datetime"] == dt].nsmallest(TOPK, "rank")["instrument"])
        if prev_set:
            changed = len(curr_set.symmetric_difference(prev_set)) / (2 * TOPK)
            turnovers.append(changed)
        prev_set = curr_set
    turnover_rate = float(np.mean(turnovers)) if turnovers else 0.0

    return {
        "sharpe": round(sharpe, 4),
        "annualized_return": round(annualized_return, 4),
        "max_drawdown": round(max_drawdown, 4),
        "ic_mean": round(ic_mean, 4),
        "ic_std": round(ic_std, 4),
        "icir": round(icir, 4),
        "turnover_rate": round(turnover_rate, 4),
        "coverage": round(coverage, 4),
    }


try:
    qlib.init(provider_uri="/data/qlib_bin/", region=REG_CN)

    start_date_obj = parse_date(START_DATE)
    end_date_obj = parse_date(END_DATE)
    total_days = (end_date_obj - start_date_obj).days
    has_oos_split = total_days > 365
    oos_start_obj = None
    discovery_end_obj = end_date_obj
    if has_oos_split:
        oos_start_obj = end_date_obj - TWELVE_MONTHS
        discovery_end_obj = oos_start_obj - timedelta(days=1)
        if discovery_end_obj < start_date_obj:
            has_oos_split = False
            discovery_end_obj = end_date_obj
            oos_start_obj = None

    discovery_end_str = format_date(discovery_end_obj)
    discovery_metrics = compute_metrics(START_DATE, discovery_end_str)
    oos_metrics = None
    metrics_scope = "full"
    oos_window = None
    oos_degradation = None
    if has_oos_split and oos_start_obj is not None:
        oos_start_str = format_date(oos_start_obj)
        oos_metrics = compute_metrics(oos_start_str, END_DATE)
        metrics_scope = "discovery"
        oos_window = build_window(
            oos_start_str,
            END_DATE,
            oos_metrics["coverage"],
            "Out-of-sample validation window",
        )
        oos_degradation = round(discovery_metrics["sharpe"] - oos_metrics["sharpe"], 4)

    discovery_window = build_window(
        START_DATE,
        discovery_end_str,
        discovery_metrics["coverage"],
        "Discovery validation window" if has_oos_split else "Full backtest window",
    )
    result = {
        "metrics_scope": metrics_scope,
        "metrics": discovery_metrics,
        "oos_metrics": oos_metrics,
        "discovery_window": discovery_window,
        "oos_window": oos_window,
        "oos_degradation": oos_degradation,
        "error": None,
    }

except Exception as e:
    discovery_window = build_window(
        START_DATE,
        END_DATE,
        ZERO_METRICS["coverage"],
        "Discovery validation window (failure)",
    )
    result = {
        "metrics_scope": "full",
        "metrics": ZERO_METRICS.copy(),
        "oos_metrics": None,
        "discovery_window": discovery_window,
        "oos_window": None,
        "oos_degradation": None,
        "error": str(e),
    }

print("BACKTEST_RESULT_JSON:" + json.dumps(result))
