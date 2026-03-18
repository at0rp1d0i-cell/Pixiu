"""验收测试：Island 调度器。"""
import os
import sys
import math
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytestmark = pytest.mark.unit

from dataclasses import dataclass
from src.factor_pool.pool import FactorPool
from src.factor_pool.scheduler import IslandScheduler, VIRGIN_ISLAND_SHARPE, T_INIT, T_MIN
from src.schemas.backtest import BacktestMetrics


@dataclass
class FactorHypothesis:
    """Duck-type shim for pool.register() API."""
    name: str
    formula: str
    hypothesis: str
    rationale: str
    expected_direction: str = "unknown"
    market_observation: str = ""


@pytest.fixture()
def pool(tmp_path):
    return FactorPool(db_path=str(tmp_path / "test_db"))


@pytest.fixture()
def scheduler(pool):
    return IslandScheduler(pool, seed=42)


def _register(pool, island, name, sharpe):
    h = FactorHypothesis(name=name, formula=f"Mean($close,5)", hypothesis="test", rationale="test")
    m = BacktestMetrics(sharpe=sharpe, annualized_return=0.1, max_drawdown=-0.1,
                        ic_mean=0.03, ic_std=0.01, icir=0.4, turnover_rate=20.0)
    pool.register(h, m, island_name=island)


class TestSoftmax:
    def test_probabilities_sum_to_one(self, scheduler):
        probs = scheduler._softmax([2.0, 2.5, 3.0], temperature=1.0)
        assert abs(sum(probs) - 1.0) < 1e-9

    def test_higher_value_gets_higher_prob(self, scheduler):
        probs = scheduler._softmax([1.0, 2.0, 3.0], temperature=1.0)
        assert probs[2] > probs[1] > probs[0]

    def test_high_temperature_is_more_uniform(self, scheduler):
        probs_low = scheduler._softmax([1.0, 3.0], temperature=0.1)
        probs_high = scheduler._softmax([1.0, 3.0], temperature=10.0)
        # 低温时差距更大
        assert (probs_low[1] - probs_low[0]) > (probs_high[1] - probs_high[0])

    def test_low_temperature_approaches_argmax(self, scheduler):
        probs = scheduler._softmax([1.0, 1.0, 100.0], temperature=0.01)
        assert probs[2] > 0.999


class TestSelectIsland:
    def test_returns_active_island(self, scheduler):
        chosen = scheduler.select_island()
        assert chosen in scheduler._active_islands

    def test_virgin_islands_get_default_sharpe(self, pool, scheduler):
        # 无历史数据时，使用 VIRGIN_ISLAND_SHARPE
        sharpes = scheduler._get_island_sharpes()
        for island in scheduler._active_islands:
            assert sharpes[island] == VIRGIN_ISLAND_SHARPE

    def test_known_island_uses_historical_sharpe(self, pool, scheduler):
        _register(pool, "momentum", "factor_a", sharpe=2.9)
        sharpes = scheduler._get_island_sharpes()
        assert sharpes["momentum"] == pytest.approx(2.9)

    def test_statistical_selection_bias(self, pool):
        """高 Sharpe Island 在大量采样中被选中概率更高。"""
        _register(pool, "momentum", "high", sharpe=3.5)
        _register(pool, "northbound", "low", sharpe=1.5)

        sched = IslandScheduler(pool, seed=0)
        # 只保留这两个做测试
        sched._active_islands = ["momentum", "northbound"]
        sched._reserve_islands = []

        counts = {"momentum": 0, "northbound": 0}
        for _ in range(200):
            counts[sched.select_island()] += 1

        # momentum（高 Sharpe）应该被选中更多次
        assert counts["momentum"] > counts["northbound"]


class TestAnnealing:
    def test_temperature_decreases_after_anneal_every(self, scheduler):
        from src.factor_pool.scheduler import ANNEAL_EVERY
        initial_t = scheduler._temperature
        for i in range(ANNEAL_EVERY):
            scheduler.on_epoch_done("momentum", i)
        assert scheduler._temperature < initial_t

    def test_temperature_never_below_t_min(self, scheduler):
        for i in range(200):
            scheduler.on_epoch_done("momentum", i)
        assert scheduler._temperature >= T_MIN


class TestReset:
    def test_no_reset_if_too_few_runs(self, pool, scheduler):
        # 只跑了 1 次，低于 RESET_MIN_RUNS=3，不触发重置
        _register(pool, "momentum", "bad", sharpe=1.0)
        assert not scheduler._should_reset("momentum")

    def test_triggers_reset_when_conditions_met(self, pool, scheduler):
        from src.factor_pool.scheduler import RESET_MIN_RUNS
        for i in range(RESET_MIN_RUNS):
            _register(pool, "momentum", f"bad_{i}", sharpe=1.0)
        assert scheduler._should_reset("momentum")

    def test_no_reset_if_no_reserve(self, pool):
        sched = IslandScheduler(pool, seed=0)
        sched._reserve_islands = []  # 清空备用池
        from src.factor_pool.scheduler import RESET_MIN_RUNS
        for i in range(RESET_MIN_RUNS):
            _register(pool, "momentum", f"f_{i}", sharpe=1.0)
        assert not sched._should_reset("momentum")

    def test_reset_swaps_islands(self, pool):
        sched = IslandScheduler(pool, seed=0)
        original_active = set(sched._active_islands)
        original_reserve = set(sched._reserve_islands)

        from src.factor_pool.scheduler import RESET_MIN_RUNS
        for i in range(RESET_MIN_RUNS):
            _register(pool, "momentum", f"f_{i}", sharpe=1.0)

        sched._reset_island("momentum")

        new_active = set(sched._active_islands)
        new_reserve = set(sched._reserve_islands)

        assert "momentum" not in new_active
        assert "momentum" in new_reserve
        assert len(new_active) == len(original_active)  # 数量不变


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
