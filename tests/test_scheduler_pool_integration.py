"""
Scheduler ↔ FactorPool 集成测试

验证 IslandScheduler 与真实 FactorPool 的联动行为：
- select_island() 基于 pool leaderboard 统计上偏向高 Sharpe island
- on_epoch_done() 触发 reset 后 active_islands 变化
- get_active_islands() 在 reset 后返回更新列表

注意：使用 _InMemoryClient 代替 PersistentClient，避免 ChromaDB 触发
ONNX embedding 模型网络下载（测试环境无网络/代理问题）。
"""
import pytest
from unittest.mock import patch

pytestmark = pytest.mark.unit

from src.factor_pool.pool import FactorPool, _InMemoryClient
from src.factor_pool.scheduler import (
    IslandScheduler,
    RESET_MIN_RUNS,
    VIRGIN_ISLAND_SHARPE,
)
from src.schemas.backtest import BacktestMetrics, BacktestReport
from src.schemas.judgment import CriticVerdict, RiskAuditReport


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def _make_report(island: str, factor_id: str, sharpe: float) -> BacktestReport:
    return BacktestReport(
        report_id=f"report-{factor_id}",
        note_id=factor_id,
        factor_id=factor_id,
        island=island,
        formula="$close",
        metrics=BacktestMetrics(
            sharpe=sharpe,
            annualized_return=0.1,
            max_drawdown=0.1,
            ic_mean=0.04,
            ic_std=0.03,
            icir=0.5,
            turnover_rate=0.2,
        ),
        passed=sharpe > 1.0,
        execution_time_seconds=1.0,
        qlib_output_raw="BACKTEST_RESULT_JSON:{}",
    )


def _make_verdict(factor_id: str, passed: bool) -> CriticVerdict:
    return CriticVerdict(
        report_id=f"report-{factor_id}",
        factor_id=factor_id,
        note_id=factor_id,
        overall_passed=passed,
        decision="promote" if passed else "archive",
        score=0.9 if passed else 0.3,
        checks=[],
        register_to_pool=True,
        pool_tags=[],
        reason_codes=[],
    )


def _make_risk_report(factor_id: str) -> RiskAuditReport:
    return RiskAuditReport(
        factor_id=factor_id,
        overfitting_score=0.0,
        overfitting_flag=False,
        correlation_flags=[],
        recommendation="clear",
        audit_notes="ok",
    )


def _register_n_factors(pool: FactorPool, island: str, sharpe: float, n: int):
    """向指定 island 写入 n 个因子（通过 v2 register_factor API）。"""
    for i in range(n):
        fid = f"{island}_factor_{i}"
        report = _make_report(island, fid, sharpe)
        verdict = _make_verdict(fid, passed=sharpe > 1.0)
        risk = _make_risk_report(fid)
        pool.register_factor(report=report, verdict=verdict, risk_report=risk, hypothesis="test")


# ─────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────

@pytest.fixture()
def pool(tmp_path):
    """使用 in-memory client 的 FactorPool，避免 ChromaDB 触发网络下载。"""
    with patch("src.factor_pool.pool.chromadb.PersistentClient", side_effect=RuntimeError("force in-memory")):
        return FactorPool(db_path=str(tmp_path / "test_db"))


@pytest.fixture()
def scheduler(pool):
    return IslandScheduler(pool, seed=42)


# ─────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────

def test_get_active_islands_returns_list(scheduler):
    """get_active_islands() 应返回非空列表。"""
    islands = scheduler.get_active_islands()
    assert isinstance(islands, list)
    assert len(islands) > 0


def test_get_active_islands_matches_internal_state(scheduler):
    """get_active_islands() 返回的列表应与 _active_islands 一致。"""
    assert scheduler.get_active_islands() == scheduler._active_islands


def test_get_active_islands_returns_copy(scheduler):
    """get_active_islands() 应返回副本，外部修改不影响内部状态。"""
    result = scheduler.get_active_islands()
    result.clear()
    assert len(scheduler._active_islands) > 0, "外部修改不应影响内部 _active_islands"


def test_scheduler_selects_based_on_real_pool_leaderboard(pool):
    """
    高 Sharpe island 在大量采样中被选中概率更高（基于真实 pool leaderboard）。
    """
    _register_n_factors(pool, "momentum", sharpe=3.5, n=3)
    _register_n_factors(pool, "northbound", sharpe=1.0, n=3)

    sched = IslandScheduler(pool, seed=0)
    sched._active_islands = ["momentum", "northbound"]
    sched._reserve_islands = []

    counts = {"momentum": 0, "northbound": 0}
    for _ in range(200):
        counts[sched.select_island()] += 1

    assert counts["momentum"] > counts["northbound"], (
        f"momentum({counts['momentum']}) 应 > northbound({counts['northbound']})"
    )


def test_get_active_islands_reflects_reset(pool):
    """
    reset 后 get_active_islands() 应返回更新后的列表（不再包含被淘汰的 island）。
    """
    sched = IslandScheduler(pool, seed=0)

    _register_n_factors(pool, "momentum", sharpe=1.0, n=RESET_MIN_RUNS)

    original_active = sched.get_active_islands()
    assert "momentum" in original_active

    sched._reset_island("momentum")

    new_active = sched.get_active_islands()
    assert "momentum" not in new_active, "reset 后 momentum 应从 active_islands 中移除"


def test_scheduler_virgin_island_uses_default_sharpe(pool, scheduler):
    """没有历史数据的 island 应使用 VIRGIN_ISLAND_SHARPE。"""
    sharpes = scheduler._get_island_sharpes()
    for island in scheduler.get_active_islands():
        assert sharpes[island] == VIRGIN_ISLAND_SHARPE


def test_scheduler_known_island_uses_real_sharpe(pool):
    """注册真实因子后，leaderboard 应反映真实 Sharpe。"""
    _register_n_factors(pool, "momentum", sharpe=2.9, n=1)
    sched = IslandScheduler(pool, seed=42)
    sharpes = sched._get_island_sharpes()
    assert sharpes["momentum"] == pytest.approx(2.9)


def test_on_epoch_done_triggers_anneal_after_n_rounds(pool, scheduler):
    """足够多轮后温度应下降。"""
    from src.factor_pool.scheduler import ANNEAL_EVERY

    initial_t = scheduler._temperature
    for i in range(ANNEAL_EVERY):
        scheduler.on_epoch_done("momentum", i)
    assert scheduler._temperature < initial_t
