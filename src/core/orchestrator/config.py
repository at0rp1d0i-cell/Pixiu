"""Orchestrator runtime configuration.

Keep process-level configuration in one place so the package root no longer
needs to own mutable runtime constants.
"""
from __future__ import annotations

import os
from pathlib import Path


def resolve_reports_dir() -> Path:
    configured = os.getenv("PIXIU_REPORTS_DIR")
    return Path(configured) if configured else Path(__file__).resolve().parents[3] / "data" / "reports"


MAX_ROUNDS: int = int(os.getenv("MAX_ROUNDS", "100"))
ACTIVE_ISLANDS: list[str] = os.getenv(
    "ACTIVE_ISLANDS",
    "momentum,northbound,valuation,volatility,volume,sentiment",
).split(",")
REPORT_EVERY_N_ROUNDS: int = int(os.getenv("REPORT_EVERY_N_ROUNDS", "5"))
MAX_CONCURRENT_BACKTESTS: int = int(os.getenv("MAX_CONCURRENT_BACKTESTS", "2"))

REPORTS_DIR = resolve_reports_dir()
