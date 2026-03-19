"""Shared environment helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def load_dotenv_if_available(dotenv_path: Optional[str | Path] = None) -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=dotenv_path)
    except ImportError:
        pass
