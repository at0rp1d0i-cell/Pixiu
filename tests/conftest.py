from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PRIMARY_TIER_MARKERS = {"smoke", "unit", "integration", "live", "e2e"}
LIVE_TIER_MARKERS = {"live", "e2e"}


def _has_marker(item: pytest.Item, marker_name: str) -> bool:
    return any(True for _ in item.iter_markers(name=marker_name))


def _has_primary_tier_marker(item: pytest.Item) -> bool:
    return any(_has_marker(item, marker_name) for marker_name in PRIMARY_TIER_MARKERS)


def _is_live_like_item(item: pytest.Item) -> bool:
    return any(_has_marker(item, marker_name) for marker_name in LIVE_TIER_MARKERS)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    missing_primary_markers: list[str] = []
    for item in items:
        if not _has_primary_tier_marker(item):
            missing_primary_markers.append(str(item.path.relative_to(PROJECT_ROOT)))

    if missing_primary_markers:
        raise pytest.UsageError(
            "tests under tests/ must declare an explicit primary tier marker; "
            f"missing markers in: {', '.join(sorted(missing_primary_markers))}"
        )


@pytest.fixture(autouse=True)
def _prepare_live_test_env(request, monkeypatch):
    if not _is_live_like_item(request.node):
        yield
        return

    from tests.helpers.live_env import clear_proxy_env, ensure_researcher_live_env_or_skip

    clear_proxy_env(monkeypatch)
    ensure_researcher_live_env_or_skip()
    yield


@pytest.fixture
def orchestrator_state_guard():
    from tests.helpers.orchestrator import isolated_orchestrator_state

    return isolated_orchestrator_state
