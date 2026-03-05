# Island 调度器 — 实施规格说明书

> 面向 Gemini 的执行文档
> 版本：1.0 | 日期：2026-03-05
> 前置条件：FactorPool ChromaDB 数据层任务已完成

---

## 任务背景

当前 `orchestrator.py` 的 `run_layer1_ab_test(island_name="momentum")` 是硬编码单 Island 运行。
每次只在一个方向上迭代，容易陷入局部最优。

本任务目标：
1. 实现 `IslandScheduler`，用 **softmax 采样 + 温度退火** 选择每轮激活的 Island
2. 实现 **Island 重置机制**：长期表现差的方向被新方向替代
3. 改造 `orchestrator.py`，用 `N` 轮大循环替代单次运行
4. 让 Researcher 在 System Prompt 中收到 Island 上下文（历史最优 + 排行榜）

**本任务不做：** 并发回测、多进程 Researcher

---

## 交付物清单

1. `src/factor_pool/scheduler.py` — IslandScheduler 核心类
2. `src/core/orchestrator.py` — 改造，加入大循环 + 调度器
3. `tests/test_scheduler.py` — 验收测试

**不要动的文件：** `researcher.py`、`critic.py`、`coder.py`、`pool.py`、`islands.py`

---

## 任务 1：创建 `src/factor_pool/scheduler.py`

**完整文件内容：**

```python
"""
EvoQuant: Island 调度器
实现 FunSearch Island 模型的 EvoQuant 适配版：
  - softmax 采样（偏向优秀 Island，保留探索性）
  - 温度退火（初期探索，后期利用）
  - Island 重置（淘汰长期无效方向，补充新方向）
"""
import logging
import math
import random
from typing import Optional

from .islands import ISLANDS, DEFAULT_ACTIVE_ISLANDS
from .pool import FactorPool

logger = logging.getLogger(__name__)

# ── 调度参数 ────────────────────────────────────────────────────
T_INIT = 1.0          # 初始温度（高 = 探索为主）
T_MIN = 0.3           # 最低温度（不完全退化为 argmax，保留探索性）
ANNEAL_EVERY = 10     # 每隔多少轮降一次温度
ANNEAL_FACTOR = 0.85  # 每次降温的倍率（T_new = T * factor）

RESET_MIN_RUNS = 3    # 触发重置的最少实验次数（跑太少不算数据）
RESET_SHARPE_THRESHOLD = 1.5  # best_sharpe 低于此值 → 候选重置

# Island 的"新人"初始 Sharpe（没有历史数据时用于 softmax）
VIRGIN_ISLAND_SHARPE = 2.0  # 略低于基线，鼓励先探索旧方向，但不完全排斥新方向


class IslandScheduler:
    """Island 选择与生命周期管理。

    使用方式：
        scheduler = IslandScheduler(pool)
        for round_n in range(MAX_ROUNDS):
            island = scheduler.select_island()
            run_one_epoch(island)          # 外部调用
            scheduler.on_epoch_done(island, round_n)
    """

    def __init__(self, pool: FactorPool, seed: Optional[int] = None):
        self._pool = pool
        self._temperature = T_INIT
        self._round = 0
        self._active_islands: list[str] = list(DEFAULT_ACTIVE_ISLANDS)
        # 所有可用但当前未激活的 Island（作为重置补充池）
        self._reserve_islands: list[str] = [
            name for name in ISLANDS if name not in self._active_islands
        ]
        if seed is not None:
            random.seed(seed)

        logger.info(
            "[Scheduler] 初始化完成。激活 Islands: %s | 备用 Islands: %s | T=%.2f",
            self._active_islands, self._reserve_islands, self._temperature,
        )

    # ─────────────────────────────────────────────
    # 公共接口
    # ─────────────────────────────────────────────

    def select_island(self) -> str:
        """用 softmax 采样选择本轮激活的 Island。

        概率 ∝ exp(best_sharpe / T)
        T 高→各 Island 概率接近均匀（探索）
        T 低→最优 Island 概率远高于其他（利用）

        Returns:
            island_name: 选中的 Island 代号
        """
        sharpes = self._get_island_sharpes()
        probs = self._softmax(list(sharpes.values()), self._temperature)
        islands = list(sharpes.keys())

        chosen = random.choices(islands, weights=probs, k=1)[0]
        logger.info(
            "[Scheduler] 第 %d 轮选中 Island: %s（T=%.2f, Sharpe=%.2f, 概率=%.1f%%）",
            self._round + 1, chosen, self._temperature,
            sharpes[chosen], probs[islands.index(chosen)] * 100,
        )
        return chosen

    def on_epoch_done(self, island_name: str, round_n: int) -> None:
        """每轮结束后调用：退火 + 检查是否需要重置。

        Args:
            island_name: 本轮运行的 Island
            round_n: 当前轮次（从 0 开始）
        """
        self._round = round_n + 1

        # 退火
        if (round_n + 1) % ANNEAL_EVERY == 0:
            old_t = self._temperature
            self._temperature = max(self._temperature * ANNEAL_FACTOR, T_MIN)
            logger.info(
                "[Scheduler] 温度退火：%.2f → %.2f（第 %d 轮）",
                old_t, self._temperature, round_n + 1,
            )

        # 检查重置
        if self._should_reset(island_name):
            self._reset_island(island_name)

    def get_status(self) -> dict:
        """返回调度器当前状态（用于日志和 CIO 面板）。"""
        sharpes = self._get_island_sharpes()
        return {
            "round": self._round,
            "temperature": self._temperature,
            "active_islands": self._active_islands,
            "island_sharpes": sharpes,
            "reserve_islands": self._reserve_islands,
        }

    # ─────────────────────────────────────────────
    # 内部方法
    # ─────────────────────────────────────────────

    def _get_island_sharpes(self) -> dict[str, float]:
        """从 FactorPool 获取各 Island 的历史最优 Sharpe。

        没有历史数据的 Island 用 VIRGIN_ISLAND_SHARPE 填充。
        """
        leaderboard = self._pool.get_island_leaderboard()
        known = {item["island"]: item["best_sharpe"] for item in leaderboard}

        return {
            island: known.get(island, VIRGIN_ISLAND_SHARPE)
            for island in self._active_islands
        }

    @staticmethod
    def _softmax(values: list[float], temperature: float) -> list[float]:
        """数值稳定的 softmax，带温度参数。"""
        scaled = [v / temperature for v in values]
        max_val = max(scaled)
        exp_vals = [math.exp(v - max_val) for v in scaled]  # 减 max 防数值溢出
        total = sum(exp_vals)
        return [v / total for v in exp_vals]

    def _should_reset(self, island_name: str) -> bool:
        """判断一个 Island 是否应该被重置（淘汰）。

        条件：best_sharpe < 阈值 AND 该 Island 已跑过足够多次实验
        """
        if not self._reserve_islands:
            return False  # 没有备用 Island，无法重置

        leaderboard = self._pool.get_island_leaderboard()
        for item in leaderboard:
            if item["island"] == island_name:
                runs = item["factor_count"]
                best = item["best_sharpe"]
                if runs >= RESET_MIN_RUNS and best < RESET_SHARPE_THRESHOLD:
                    logger.info(
                        "[Scheduler] Island '%s' 触发重置条件：best_sharpe=%.2f < %.2f，已跑 %d 次",
                        island_name, best, RESET_SHARPE_THRESHOLD, runs,
                    )
                    return True
        return False

    def _reset_island(self, old_island: str) -> None:
        """淘汰一个 Island，从备用池中补充新方向。"""
        if not self._reserve_islands:
            logger.warning("[Scheduler] 备用 Island 池已空，无法重置 '%s'", old_island)
            return

        new_island = self._reserve_islands.pop(0)
        self._active_islands.remove(old_island)
        self._active_islands.append(new_island)
        self._reserve_islands.append(old_island)  # 把旧的放回备用（未来可能再激活）

        logger.info(
            "[Scheduler] Island 重置：'%s' → '%s'（%s 移入备用池）",
            old_island, new_island, old_island,
        )
```

---

## 任务 2：改造 `src/core/orchestrator.py`

这是本任务最重要的改动——把单次运行改成带调度的大循环。

### 2.1 在文件顶部 import 块末尾追加

```python
from src.factor_pool.scheduler import IslandScheduler
```

### 2.2 新增 `run_evolution_loop()` 函数（在 `run_layer1_ab_test` 之后新增，不要删除旧函数）

```python
def run_evolution_loop(max_rounds: int = 20):
    """
    Island 进化大循环：多方向轮换搜索，直到找到超越基线的因子或达到最大轮次。

    Args:
        max_rounds: 最大大轮次数（每轮 = 一次完整 Researcher→Coder→Critic epoch）
                    建议：测试用 5，正式搜索用 20-50
    """
    app = build_graph()
    pool = get_factor_pool()
    scheduler = IslandScheduler(pool)

    logging.info("\n" + "=" * 60)
    logging.info("🧬 启动 Island 进化搜索（最大 %d 轮）", max_rounds)
    logging.info("=" * 60)

    best_sharpe_ever = 0.0
    best_factor_ever = None

    for round_n in range(max_rounds):
        logging.info("\n─── 第 %d / %d 大轮 ───────────────────────────────", round_n + 1, max_rounds)

        # 1. 选 Island
        island_name = scheduler.select_island()
        island_display = __import__(
            "src.factor_pool.islands", fromlist=["ISLANDS"]
        ).ISLANDS.get(island_name, {}).get("name", island_name)
        logging.info("[Orchestrator] 激活 Island: %s（%s）", island_name, island_display)

        # 2. 构建本轮初始状态
        initial_state = {
            "messages": [],
            "factor_proposal": "",
            "factor_hypothesis": None,
            "code_snippet": "",
            "backtest_result": "",
            "backtest_metrics": None,
            "error_message": "",
            "current_iteration": 0,
            "max_iterations": 3,
            "island_name": island_name,
        }

        # 3. 跑一个 epoch（Researcher → Validator → Coder → Critic，最多 3 次内循环）
        try:
            final_state = app.invoke(initial_state)
        except Exception as e:
            logging.error("[Orchestrator] 第 %d 轮 epoch 异常：%s", round_n + 1, e)
            scheduler.on_epoch_done(island_name, round_n)
            continue

        # 4. 注册结果到 FactorPool
        hypothesis = final_state.get("factor_hypothesis")
        metrics = final_state.get("backtest_metrics")

        if hypothesis and metrics and metrics.parse_success:
            pool.register(
                hypothesis=hypothesis,
                metrics=metrics,
                island_name=island_name,
            )
            sharpe = metrics.sharpe
            logging.info(
                "[Orchestrator] 注册因子 '%s'：Sharpe=%.2f, IC=%.4f, ICIR=%.2f",
                hypothesis.name, sharpe, metrics.ic, metrics.icir,
            )

            # 追踪全局最优
            if sharpe > best_sharpe_ever:
                best_sharpe_ever = sharpe
                best_factor_ever = hypothesis
                logging.info(
                    "🌟 新全局最优！Sharpe=%.2f，因子：%s",
                    best_sharpe_ever, best_factor_ever.name,
                )

            # 突破基线 → 提前终止
            if sharpe > 2.67 and metrics.ic > 0.02 and metrics.icir > 0.3:
                logging.info("\n🎉 基线突破！终止进化搜索。")
                break
        else:
            logging.info("[Orchestrator] 第 %d 轮无有效回测结果", round_n + 1)

        # 5. 调度器后处理（退火 + 重置检查）
        scheduler.on_epoch_done(island_name, round_n)

        # 6. 打印当前排行榜（每 5 轮一次）
        if (round_n + 1) % 5 == 0:
            _print_leaderboard(pool, scheduler)

    # 最终汇报
    _print_final_report(pool, best_sharpe_ever, best_factor_ever, round_n + 1)


def _print_leaderboard(pool: object, scheduler: "IslandScheduler") -> None:
    """打印 Island 排行榜。"""
    status = scheduler.get_status()
    logging.info("\n=== Island 排行榜（第 %d 轮，T=%.2f）===", status["round"], status["temperature"])
    leaderboard = pool.get_island_leaderboard()
    for rank, item in enumerate(leaderboard, 1):
        active_mark = "✓" if item["island"] in status["active_islands"] else " "
        logging.info(
            "  [%s] #%d %-12s best=%.2f  avg=%.2f  n=%d  最优因子: %s",
            active_mark, rank,
            item["island_display_name"],
            item["best_sharpe"],
            item["avg_sharpe"],
            item["factor_count"],
            item["best_factor_name"],
        )


def _print_final_report(pool: object, best_sharpe: float, best_factor: object, total_rounds: int) -> None:
    """打印最终汇报。"""
    stats = pool.get_stats()
    logging.info("\n" + "=" * 60)
    logging.info("🏁 进化搜索结束")
    logging.info("  总轮次: %d", total_rounds)
    logging.info("  总实验因子数: %d", stats["total_factors"])
    logging.info("  突破基线因子数: %d", stats["beats_baseline_count"])
    logging.info("  全局最优 Sharpe: %.2f", best_sharpe)
    if best_factor:
        logging.info("  最优因子: %s", best_factor.name)
        logging.info("  最优公式: %s", best_factor.formula)
    logging.info("=" * 60)
```

### 2.3 修改 `if __name__ == "__main__":` 入口

**找到：**
```python
if __name__ == "__main__":
    run_layer1_ab_test()
```

**替换为：**
```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="EvoQuant Orchestrator")
    parser.add_argument("--mode", choices=["single", "evolve"], default="evolve",
                        help="single: 单 Island 单次运行；evolve: Island 进化大循环")
    parser.add_argument("--island", default="momentum",
                        help="single 模式下指定 Island")
    parser.add_argument("--rounds", type=int, default=20,
                        help="evolve 模式下的最大大轮次数")
    args = parser.parse_args()

    if args.mode == "single":
        run_layer1_ab_test(island_name=args.island)
    else:
        run_evolution_loop(max_rounds=args.rounds)
```

---

## 任务 3：创建 `tests/test_scheduler.py`

```python
"""验收测试：Island 调度器。"""
import os
import sys
import math
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.schemas import BacktestMetrics, FactorHypothesis
from src.factor_pool.pool import FactorPool
from src.factor_pool.scheduler import IslandScheduler, VIRGIN_ISLAND_SHARPE, T_INIT, T_MIN


@pytest.fixture()
def pool(tmp_path):
    return FactorPool(db_path=str(tmp_path / "test_db"))


@pytest.fixture()
def scheduler(pool):
    return IslandScheduler(pool, seed=42)


def _register(pool, island, name, sharpe):
    h = FactorHypothesis(name=name, formula=f"Mean($close,5)", hypothesis="test", rationale="test")
    m = BacktestMetrics(sharpe=sharpe, parse_success=True, ic=0.03, icir=0.4, turnover=20.0)
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
```

---

## 验收清单

```bash
# Step 1: 跑调度器测试
cd EvoQuant
python3 -m pytest tests/test_scheduler.py -v
# 预期：全部 PASSED

# Step 2: 测试单 Island 模式（快速验证入口）
python3 EvoQuant/src/core/orchestrator.py --mode single --island momentum

# Step 3: 测试进化模式（5 轮，观察 Island 轮换日志）
python3 EvoQuant/src/core/orchestrator.py --mode evolve --rounds 5
# 确认日志中出现：
#   🧬 启动 Island 进化搜索
#   [Scheduler] 第 N 轮选中 Island: XXX（T=X.XX, 概率=XX%）
#   [FactorPool] 注册因子 ...
#   === Island 排行榜 ===（第 5 轮出现）
```

---

## 注意事项

1. `run_layer1_ab_test()` **保留不删除**，`--mode single` 仍然调用它，用于快速调试单个 Island
2. `IslandScheduler` 的随机性依赖 `random.seed()`，生产环境不传 seed（真随机），测试环境传固定 seed（可重复）
3. `_get_island_sharpes()` 每次都实时查 FactorPool，不缓存——Island 状态随时更新，保证调度决策基于最新数据
4. 温度退火是按**大轮次**计算的（`round_n`），不是内循环的 `current_iteration`
5. Island 重置后旧 Island 进入备用池，未来仍可重新激活——不是永久淘汰
