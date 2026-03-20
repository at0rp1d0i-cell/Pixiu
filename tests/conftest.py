from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PRIMARY_TIER_MARKERS = {"smoke", "unit", "integration", "live", "e2e"}
LIVE_TIER_MARKERS = {"live", "e2e"}


def _has_marker(item: pytest.Item, marker_name: str) -> bool:
    return any(True for _ in item.iter_markers(name=marker_name))


def _has_primary_tier_marker(item: pytest.Item) -> bool:
    return any(_has_marker(item, marker_name) for marker_name in PRIMARY_TIER_MARKERS)


def _is_live_like_item(item: pytest.Item) -> bool:
    return any(_has_marker(item, marker_name) for marker_name in LIVE_TIER_MARKERS)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    from tests.helpers.live_env import researcher_api_key_available

    live_like_items = [item for item in items if _is_live_like_item(item)]
    live_api_key_available = True
    if live_like_items:
        live_api_key_available = researcher_api_key_available()

    missing_primary_markers: list[str] = []
    for item in items:
        if not _has_primary_tier_marker(item):
            missing_primary_markers.append(str(item.path.relative_to(PROJECT_ROOT)))

        if _is_live_like_item(item) and not live_api_key_available:
            item.add_marker(pytest.mark.skip(reason="RESEARCHER_API_KEY 未设置，跳过真实场景测试"))

    if missing_primary_markers:
        raise pytest.UsageError(
            "tests under tests/ must declare an explicit primary tier marker; "
            f"missing markers in: {', '.join(sorted(missing_primary_markers))}"
        )


@pytest.fixture(autouse=True)
def _clear_live_proxy_env(request, monkeypatch):
    if not _is_live_like_item(request.node):
        yield
        return

    from tests.helpers.live_env import clear_proxy_env

    clear_proxy_env(monkeypatch)
    yield


@pytest.fixture
def orchestrator_state_guard():
    from tests.helpers.orchestrator import isolated_orchestrator_state

    return isolated_orchestrator_state
