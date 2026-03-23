#!/usr/bin/env python
"""
Pixiu System Doctor: tiered pre-flight health check.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter
from typing import Awaitable, Callable

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from src.core.env import ResolvedEnv, resolve_and_apply_layered_env

console = Console()
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QLIB_DATA_DIR = PROJECT_ROOT / "data" / "qlib_bin"
CRITICAL_ENV_KEYS = ("TUSHARE_TOKEN", "QLIB_DATA_DIR")


DoctorRunner = Callable[[], bool | str | tuple[bool | str, str] | Awaitable[bool | str | tuple[bool | str, str]]]


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    tier: str
    domain: str
    runner: DoctorRunner


def _normalize_result(result) -> tuple[bool | str, str]:
    if isinstance(result, tuple) and len(result) == 2:
        return result
    if isinstance(result, bool):
        return result, ""
    if isinstance(result, str):
        return "WARN", result
    return False, str(result)


def _status_icon(status_code: bool | str) -> tuple[str, str]:
    if status_code is True:
        return "green", "PASS"
    if status_code == "WARN":
        return "yellow", "WARN"
    return "red", "FAIL"


def check_runtime_readiness() -> tuple[bool | str, str]:
    try:
        from src.formula.capabilities import get_runtime_formula_capabilities

        caps = get_runtime_formula_capabilities()
        qlib_env = os.getenv("QLIB_DATA_DIR")
        qlib_path = Path(qlib_env) if qlib_env else DEFAULT_QLIB_DATA_DIR
        if not qlib_path.is_absolute():
            qlib_path = PROJECT_ROOT / qlib_path
        if not qlib_path.exists():
            return False, f"Qlib bin dir not found: {qlib_path}"

        cal_file = qlib_path / "calendars" / "day.txt"
        last_date = "unknown"
        if cal_file.exists():
            lines = cal_file.read_text(encoding="utf-8").strip().splitlines()
            if lines:
                last_date = lines[-1].strip()

        return True, f"runtime fields={len(caps.available_fields)} | calendar={last_date}"
    except Exception as exc:
        return False, str(exc)


def _tushare_client():
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN missing")
    import tushare as ts

    ts.set_token(token)
    return ts.pro_api()


def check_moneyflow_hsgt() -> tuple[bool | str, str]:
    try:
        pro = _tushare_client()
        end_date = date.today().strftime("%Y%m%d")
        start_date = (date.today() - timedelta(days=30)).strftime("%Y%m%d")
        df = pro.moneyflow_hsgt(start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return False, "moneyflow_hsgt returned no rows"
        latest = df.sort_values("trade_date").iloc[-1]
        return True, f"rows={len(df)} | latest={latest['trade_date']}"
    except Exception as exc:
        return False, str(exc)


def check_margin_proxy() -> tuple[bool | str, str]:
    try:
        pro = _tushare_client()
        end_date = date.today().strftime("%Y%m%d")
        start_date = (date.today() - timedelta(days=30)).strftime("%Y%m%d")
        df = pro.margin(start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return False, "margin returned no rows"
        latest = df.sort_values("trade_date").iloc[-1]
        return True, f"rows={len(df)} | latest={latest['trade_date']}"
    except Exception as exc:
        return False, str(exc)


async def check_llm_layer() -> tuple[bool | str, str]:
    try:
        from langchain_core.messages import HumanMessage
        from src.llm.openai_compat import build_researcher_llm

        llm = build_researcher_llm(profile="alignment_checker")
        start = perf_counter()
        resp = await asyncio.wait_for(
            llm.ainvoke([HumanMessage(content="Reply 'OK' only.")]),
            timeout=10.0,
        )
        elapsed = perf_counter() - start
        model_name = getattr(llm, "model_name", "unknown")
        status: bool | str = True if elapsed <= 3.0 else "WARN"
        return status, f"latency={elapsed:.2f}s | model={model_name} | response={resp.content.strip()}"
    except Exception as exc:
        return False, str(exc)


def check_pool_knowledge() -> tuple[bool | str, str]:
    try:
        from src.factor_pool.pool import get_factor_pool

        pool = get_factor_pool()
        factors = pool.get_top_factors(limit=1000)
        constraints = pool.get_active_constraints() if hasattr(pool, "get_active_constraints") else []
        return True, f"passed_factors={len(factors)} | active_constraints={len(constraints)}"
    except Exception as exc:
        return False, str(exc)


def check_news_enrichment() -> tuple[bool | str, str]:
    try:
        pro = _tushare_client()
        today = date.today().strftime("%Y-%m-%d")
        df = pro.news(
            src="sina",
            start_date=f"{today} 09:00:00",
            end_date=f"{today} 23:59:59",
            limit=10,
        )
        if df is None or df.empty:
            return "WARN", "news returned no rows"
        return True, f"rows={len(df)}"
    except Exception as exc:
        return "WARN", str(exc)


def check_moneyflow_staging() -> tuple[bool | str, str]:
    moneyflow_dir = PROJECT_ROOT / "data" / "fundamental_staging" / "moneyflow"
    hsgt_file = PROJECT_ROOT / "data" / "fundamental_staging" / "moneyflow_hsgt" / "moneyflow_hsgt.parquet"
    moneyflow_files = list(moneyflow_dir.glob("*.parquet")) if moneyflow_dir.exists() else []
    if not hsgt_file.exists():
        return "WARN", "moneyflow_hsgt parquet missing"
    return True, f"moneyflow_hsgt=present | moneyflow_files={len(moneyflow_files)}"


def build_doctor_checks(mode: str = "core") -> list[DoctorCheck]:
    checks = [
        DoctorCheck("runtime_readiness", "blocking", "数据 (Data)", check_runtime_readiness),
        DoctorCheck("moneyflow_hsgt", "blocking", "工具 (Blocking API)", check_moneyflow_hsgt),
        DoctorCheck("margin_proxy", "blocking", "工具 (Blocking API)", check_margin_proxy),
        DoctorCheck("llm", "core_optional", "算力 (LLM)", check_llm_layer),
        DoctorCheck("factor_pool", "core_optional", "因子池 (Pool)", check_pool_knowledge),
    ]
    if mode == "full":
        checks.extend(
            [
                DoctorCheck("news_enrichment", "enrichment", "增强 (Enrichment)", check_news_enrichment),
                DoctorCheck("moneyflow_staging", "data_plane", "数据面 (Data Plane)", check_moneyflow_staging),
            ]
        )
    return checks


def resolve_doctor_env_truth(*, process_env: dict[str, str] | None = None) -> ResolvedEnv:
    return resolve_and_apply_layered_env(
        keys=CRITICAL_ENV_KEYS,
        process_env=process_env if process_env is not None else os.environ,
        target_env=os.environ,
        repo_env_path=PROJECT_ROOT / ".env",
        defaults={"QLIB_DATA_DIR": str(DEFAULT_QLIB_DATA_DIR)},
    )


def _doctor_env_trace_details(env_truth: ResolvedEnv) -> str:
    token_value = os.getenv("TUSHARE_TOKEN", "")
    token_status = "set" if token_value else "missing"
    token_source = env_truth.sources.get("TUSHARE_TOKEN", "unset")
    qlib_value = os.getenv("QLIB_DATA_DIR", "")
    qlib_source = env_truth.sources.get("QLIB_DATA_DIR", "default")
    return f"TUSHARE_TOKEN={token_status} ({token_source}) | QLIB_DATA_DIR={qlib_value} ({qlib_source})"


async def run_doctor(mode: str = "core", *, env_truth: ResolvedEnv | None = None) -> int:
    if env_truth is None:
        env_truth = resolve_doctor_env_truth()

    console.print(
        Panel(
            f"[bold cyan]Pixiu System Doctor[/bold cyan]\nmode={mode}",
            border_style="cyan",
        )
    )
    console.print(f"[dim]{_doctor_env_trace_details(env_truth)}[/dim]")

    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("检查项目", width=24)
    table.add_column("Tier", width=14)
    table.add_column("状态", width=10, justify="center")
    table.add_column("详情")

    failures = 0
    for check in build_doctor_checks(mode):
        result = check.runner()
        if asyncio.iscoroutine(result):
            result = await result
        status_code, details = _normalize_result(result)
        color, icon = _status_icon(status_code)
        table.add_row(check.domain, check.tier, f"[{color}]{icon}[/{color}]", details)
        if status_code is False and check.tier == "blocking":
            failures += 1

    console.print(table)
    if failures:
        console.print("[bold red]Blocking checks failed. Do not start evolve/experiment runs.[/bold red]")
        return 1
    console.print("[bold green]Doctor checks passed for the selected mode.[/bold green]")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pixiu tiered system doctor")
    parser.add_argument(
        "--mode",
        choices=["core", "full"],
        default="core",
        help="core = blocking + core_optional, full = add enrichment + data_plane",
    )
    return parser.parse_args(argv)


async def main_async(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    env_truth = resolve_doctor_env_truth()
    return await run_doctor(mode=args.mode, env_truth=env_truth)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())
