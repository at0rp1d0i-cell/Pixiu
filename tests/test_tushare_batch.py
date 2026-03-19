from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pytest

from src.data_pipeline.tushare_batch import load_progress_file, run_per_stock_download

pytestmark = pytest.mark.unit


def _logger() -> logging.Logger:
    logger = logging.getLogger("test_tushare_batch")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def test_load_progress_file_defaults_with_empty_retry_tracking(tmp_path: Path):
    progress = load_progress_file(
        tmp_path / "progress.json",
        track_empty_retries=True,
        logger=None,
    )

    assert progress["done"] == []
    assert progress["failed"] == {}
    assert progress["empty_counts"] == {}
    assert progress["empty_done"] == []
    assert "started_at" in progress


def test_run_per_stock_download_marks_empty_done_when_empty_retry_disabled(tmp_path: Path):
    progress_file = tmp_path / "progress.json"
    progress = load_progress_file(progress_file, track_empty_retries=False, logger=None)

    run_per_stock_download(
        progress=progress,
        progress_file=progress_file,
        stock_codes=["000001.SZ"],
        fetch_frame=lambda ts_code: pd.DataFrame(),
        persist_frame=lambda ts_code, df: (_ for _ in ()).throw(AssertionError("should not persist empty frame")),
        logger=_logger(),
        checkpoint_every=1,
        sleep_between=0,
        empty_retry_limit=None,
    )

    assert progress["done"] == ["000001.SZ"]
    assert progress["failed"] == {}
    assert "empty_counts" not in progress


def test_run_per_stock_download_retries_empty_then_marks_empty_done(tmp_path: Path):
    progress_file = tmp_path / "progress.json"
    progress = load_progress_file(progress_file, track_empty_retries=True, logger=None)

    for _ in range(2):
        run_per_stock_download(
            progress=progress,
            progress_file=progress_file,
            stock_codes=["000001.SZ"],
            fetch_frame=lambda ts_code: pd.DataFrame(),
            persist_frame=lambda ts_code, df: (_ for _ in ()).throw(AssertionError("should not persist empty frame")),
            logger=_logger(),
            checkpoint_every=1,
            sleep_between=0,
            empty_retry_limit=2,
        )

    assert progress["done"] == []
    assert progress["failed"] == {}
    assert progress["empty_counts"]["000001.SZ"] == 2
    assert progress["empty_done"] == ["000001.SZ"]
