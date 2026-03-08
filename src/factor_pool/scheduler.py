"""
Pixiu: Island 调度器
实现 FunSearch Island 模型的 Pixiu 适配版：
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
