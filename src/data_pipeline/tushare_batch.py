from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
import tushare as ts

from src.core.env import clear_localhost_proxy_env, load_dotenv_if_available


def bootstrap_tushare_script(
    *,
    project_root: Path,
    logger_name: str,
    log_filename: str,
) -> logging.Logger:
    """Load env, clear broken localhost proxies, and configure script logging."""
    load_dotenv_if_available()
    cleared_proxy_vars = clear_localhost_proxy_env()

    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_dir / log_filename, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if cleared_proxy_vars:
        logger.info(
            "Cleared localhost proxy vars for direct Tushare access: %s",
            ", ".join(cleared_proxy_vars),
        )

    return logger


def get_tushare_pro(logger: logging.Logger, token_env_var: str = "TUSHARE_TOKEN"):
    token = os.getenv(token_env_var)
    if not token:
        raise RuntimeError(
            f"{token_env_var} environment variable is not set. "
            f"Export it before running: export {token_env_var}=<your_token>"
        )
    logger.info("Tushare Pro API initialized.")
    return ts.pro_api(token)


def load_progress_file(
    progress_file: Path,
    *,
    track_empty_retries: bool,
    logger: Optional[logging.Logger] = None,
) -> dict:
    if progress_file.exists():
        with open(progress_file, encoding="utf-8") as handle:
            progress = json.load(handle)
        progress.setdefault("done", [])
        progress.setdefault("failed", {})
        if track_empty_retries:
            progress.setdefault("empty_counts", {})
            progress.setdefault("empty_done", [])
        if logger is not None:
            logger.info(
                "Loaded progress: %d done, %d failed",
                len(progress.get("done", [])),
                len(progress.get("failed", {})),
            )
        return progress

    progress = {
        "done": [],
        "failed": {},
        "started_at": datetime.now().isoformat(),
    }
    if track_empty_retries:
        progress["empty_counts"] = {}
        progress["empty_done"] = []
    return progress


def save_progress_file(progress_file: Path, progress: dict) -> None:
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    progress["updated_at"] = datetime.now().isoformat()
    with open(progress_file, "w", encoding="utf-8") as handle:
        json.dump(progress, handle, indent=2, ensure_ascii=False)


def fetch_listed_stock_codes(pro, logger: logging.Logger) -> list[str]:
    df = pro.stock_basic(list_status="L", fields="ts_code")
    if df is None or df.empty:
        raise RuntimeError("pro.stock_basic returned empty result — check token/connection")
    codes = df["ts_code"].tolist()
    logger.info("[Phase 1] Total listed stocks: %d", len(codes))
    return codes


def log_batch_banner(
    logger: logging.Logger,
    *,
    title: str,
    output_path: Path,
    progress_file: Path,
) -> None:
    logger.info("=" * 60)
    logger.info("%s", title)
    logger.info("Output: %s", output_path)
    logger.info("Progress: %s", progress_file)
    logger.info("=" * 60)


def run_per_stock_download(
    *,
    progress: dict,
    progress_file: Path,
    stock_codes: list[str],
    fetch_frame: Callable[[str], pd.DataFrame | None],
    persist_frame: Callable[[str, pd.DataFrame], None],
    logger: logging.Logger,
    checkpoint_every: int,
    sleep_between: float,
    empty_retry_limit: Optional[int],
) -> None:
    done_set = set(progress["done"])
    failed_dict: dict[str, str] = progress.get("failed", {})
    empty_counts: dict[str, int] = progress.get("empty_counts", {}) if empty_retry_limit is not None else {}
    empty_done_set = set(progress.get("empty_done", [])) if empty_retry_limit is not None else set()

    pending = [code for code in stock_codes if code not in done_set and code not in empty_done_set]
    logger.info(
        "[Phase 2] Pending: %d / %d (skipped %d already done)",
        len(pending),
        len(stock_codes),
        len(stock_codes) - len(pending),
    )

    for i, ts_code in enumerate(pending, 1):
        try:
            df = fetch_frame(ts_code)
            if df is not None and not df.empty:
                persist_frame(ts_code, df)
                done_set.add(ts_code)
                progress["done"] = list(done_set)
                failed_dict.pop(ts_code, None)
                empty_counts.pop(ts_code, None)
                empty_done_set.discard(ts_code)
            elif empty_retry_limit is None:
                logger.warning(
                    "[Phase 2] [%d/%d] %s — empty result, marking done",
                    i,
                    len(pending),
                    ts_code,
                )
                done_set.add(ts_code)
                progress["done"] = list(done_set)
                failed_dict.pop(ts_code, None)
            else:
                empty_attempts = empty_counts.get(ts_code, 0) + 1
                empty_counts[ts_code] = empty_attempts
                if empty_attempts >= empty_retry_limit:
                    empty_done_set.add(ts_code)
                    logger.warning(
                        "[Phase 2] [%d/%d] %s — empty result %d times, marking empty_done",
                        i,
                        len(pending),
                        ts_code,
                        empty_attempts,
                    )
                else:
                    logger.warning(
                        "[Phase 2] [%d/%d] %s — empty result, will retry on next run",
                        i,
                        len(pending),
                        ts_code,
                    )
        except Exception as exc:
            failed_dict[ts_code] = str(exc)
            progress["failed"] = failed_dict
            logger.error("[Phase 2] [%d/%d] FAILED %s: %s", i, len(pending), ts_code, exc)

        if i % checkpoint_every == 0:
            progress["failed"] = failed_dict
            if empty_retry_limit is not None:
                progress["empty_counts"] = empty_counts
                progress["empty_done"] = list(empty_done_set)
            save_progress_file(progress_file, progress)
            logger.info(
                "[Phase 2] Checkpoint %d/%d — done: %d, failed: %d, empty_done: %d",
                i,
                len(pending),
                len(done_set),
                len(failed_dict),
                len(empty_done_set),
            )

        time.sleep(sleep_between)

    progress["failed"] = failed_dict
    if empty_retry_limit is not None:
        progress["empty_counts"] = empty_counts
        progress["empty_done"] = list(empty_done_set)
    save_progress_file(progress_file, progress)
