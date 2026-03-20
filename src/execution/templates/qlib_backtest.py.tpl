# src/execution/templates/qlib_backtest.py.tpl
# 此模板在运行时由 Coder 用字符串格式化填充

import qlib
import json
import sys
from qlib.constant import REG_CN
from qlib.data import D
from qlib.contrib.evaluate import risk_analysis
from qlib.contrib.strategy import TopkDropoutStrategy
from qlib.backtest import backtest, executor
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

# ── 由 Coder 填充的参数 ──────────────────────────────────────
FORMULA = "{formula}"
UNIVERSE = "{universe}"       # "csi300" 或 "csi500"
START_DATE = "{start_date}"   # "2021-06-01"
END_DATE = "{end_date}"       # "2025-03-31"
TOPK = {topk}                 # 持仓数量，默认 50
# ─────────────────────────────────────────────────────────────

try:
    qlib.init(provider_uri="/data/qlib_bin/", region=REG_CN)

    # 计算因子值
    instruments = D.instruments(market=UNIVERSE)
    fields = [FORMULA]
    field_names = ["factor"]
    factor_df = D.features(instruments, fields, field_names,
                           start_time=START_DATE, end_time=END_DATE)
    df = factor_df.dropna()

    # 按日排名（截面）
    df["rank"] = df.groupby("datetime")["factor"].rank(ascending=False)

    # IC 计算
    df["ret_1d"] = df.groupby("instrument")["factor"].shift(-1)  # 用真实收益率替代
    # 加载真实收益率
    ret_fields = ["$close/Ref($close,1)-1"]
    ret_df = D.features(instruments, ret_fields, ["ret"],
                        start_time=START_DATE, end_time=END_DATE)
    df = df.join(ret_df, how="left")
    factor_coverage = (
        factor_df["factor"].groupby("datetime").count()
        / ret_df["ret"].groupby("datetime").count().replace(0, np.nan)
    ).replace([np.inf, -np.inf], np.nan).dropna()
    coverage = float(factor_coverage.mean()) if len(factor_coverage) > 0 else 0.0

    ic_series = df.groupby("datetime").apply(
        lambda x: x["factor"].corr(x["ret"])
    ).dropna()

    ic_mean = float(ic_series.mean())
    ic_std = float(ic_series.std())
    icir = float(ic_mean / ic_std) if ic_std > 0 else 0.0

    # 简化回测：Top K 等权
    daily_returns = []
    for dt, group in df.groupby("datetime"):
        top = group.nsmallest(TOPK, "rank")["ret"]
        daily_returns.append(top.mean())

    daily_ret = pd.Series(daily_returns).dropna()
    annualized_return = float(daily_ret.mean() * 252) if len(daily_ret) > 0 else 0.0
    annualized_std = float(daily_ret.std() * (252 ** 0.5)) if len(daily_ret) > 1 else 0.0
    sharpe = float(annualized_return / annualized_std) if annualized_std > 0 else 0.0
    max_drawdown = float((daily_ret.cumsum() - daily_ret.cumsum().cummax()).min()) if len(daily_ret) > 0 else 0.0

    # 换手率（相邻两日 Top K 集合的变化率）
    dates = sorted(df["datetime"].unique())
    turnovers = []
    prev_set = set()
    for dt in dates:
        curr_set = set(df[df["datetime"] == dt].nsmallest(TOPK, "rank").index.get_level_values("instrument"))
        if prev_set:
            changed = len(curr_set.symmetric_difference(prev_set)) / (2 * TOPK)
            turnovers.append(changed)
        prev_set = curr_set
    turnover_rate = float(np.mean(turnovers)) if turnovers else 0.0

    result = {
        "sharpe": round(sharpe, 4),
        "annualized_return": round(annualized_return, 4),
        "max_drawdown": round(max_drawdown, 4),
        "ic_mean": round(ic_mean, 4),
        "ic_std": round(ic_std, 4),
        "icir": round(icir, 4),
        "turnover_rate": round(turnover_rate, 4),
        "coverage": round(coverage, 4),
        "error": None,
    }

except Exception as e:
    result = {
        "sharpe": 0.0,
        "annualized_return": 0.0,
        "max_drawdown": 0.0,
        "ic_mean": 0.0,
        "ic_std": 0.0,
        "icir": 0.0,
        "turnover_rate": 0.0,
        "coverage": 0.0,
        "error": str(e),
    }

print("BACKTEST_RESULT_JSON:" + json.dumps(result))
