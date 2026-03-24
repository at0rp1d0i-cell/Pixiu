from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _load_doctor_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "doctor.py"
    module_name = "doctor_test_module"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_core_mode_skips_enrichment_and_data_plane_checks():
    module = _load_doctor_module()

    checks = module.build_doctor_checks(mode="core")
    names = [check.name for check in checks]
    tiers = {check.name: check.tier for check in checks}

    assert "moneyflow_hsgt" in names
    assert "margin_proxy" in names
    assert "runtime_readiness" in names
    assert "llm" in names
    assert "news_enrichment" not in names
    assert "moneyflow_staging" not in names
    assert tiers["moneyflow_hsgt"] == "blocking"
    assert tiers["margin_proxy"] == "blocking"
    assert tiers["llm"] == "core_optional"


def test_full_mode_includes_enrichment_and_data_plane_checks():
    module = _load_doctor_module()

    checks = module.build_doctor_checks(mode="full")
    names = [check.name for check in checks]
    tiers = {check.name: check.tier for check in checks}

    assert "news_enrichment" in names
    assert "moneyflow_staging" in names
    assert tiers["news_enrichment"] == "enrichment"
    assert tiers["moneyflow_staging"] == "data_plane"


def test_fast_feedback_mode_skips_live_blocking_api_checks():
    module = _load_doctor_module()

    checks = module.build_doctor_checks(mode="fast_feedback")
    names = [check.name for check in checks]
    tiers = {check.name: check.tier for check in checks}

    assert "runtime_readiness" in names
    assert "llm" in names
    assert "factor_pool" in names
    assert "moneyflow_hsgt" not in names
    assert "margin_proxy" not in names
    assert "news_enrichment" not in names
    assert tiers["runtime_readiness"] == "blocking"
    assert tiers["llm"] == "core_optional"
