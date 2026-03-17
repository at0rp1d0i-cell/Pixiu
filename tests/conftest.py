from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PRIMARY_TIER_MARKERS = {"smoke", "unit", "integration", "live", "e2e"}
FILE_TIER_MARKERS = {
    "test_schemas.py": ("smoke",),
    "test_prefilter.py": ("smoke",),
    "test_stage2_batch.py": ("smoke",),
    "test_execution.py": ("integration",),
    "test_stage45_golden_path.py": ("integration",),
    "test_factor_pool.py": ("integration",),
    "test_scheduler.py": ("integration",),
    "test_state_store.py": ("integration",),
    "test_orchestrator_state_store.py": ("integration",),
    "test_api_state_store.py": ("integration",),
    "test_scheduler_pool_integration.py": ("integration",),
    "test_orchestrator_routing.py": ("integration",),
    "test_judgment_pool_writeback.py": ("integration",),
    "test_pipeline_stage3_to_stage5.py": ("integration",),
    "test_akshare_mcp.py": ("live",),
    "test_stage1_live.py": ("live",),
    "test_stage1_market_context.py": ("integration",),
}


def _has_marker(item: pytest.Item, marker_name: str) -> bool:
    return any(True for _ in item.iter_markers(name=marker_name))


def _has_primary_tier_marker(item: pytest.Item) -> bool:
    return any(_has_marker(item, marker_name) for marker_name in PRIMARY_TIER_MARKERS)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        tier_markers = FILE_TIER_MARKERS.get(item.path.name, ())
        for marker_name in tier_markers:
            if not _has_marker(item, marker_name):
                item.add_marker(getattr(pytest.mark, marker_name))

        if not _has_primary_tier_marker(item):
            item.add_marker(pytest.mark.unit)
