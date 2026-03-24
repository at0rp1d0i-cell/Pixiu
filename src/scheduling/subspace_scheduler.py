"""
Stage 2 子空间调度器 — 管理四个探索子空间的配额分配

冷启动阶段使用金融文献研究得出的固定权重；
暖启动阶段使用 Thompson Sampling 自适应调整权重。
"""

from __future__ import annotations

import os
import random
from typing import Dict, List, Tuple

from pydantic import BaseModel, Field

from src.schemas.hypothesis import ExplorationSubspace


class SubspaceAllocation(BaseModel):
    """单轮分配结果"""

    subspace: ExplorationSubspace
    quota: int  # 本轮分配的配额
    weight: float  # 当前权重


class SchedulerState(BaseModel):
    """调度器持久化状态"""

    round_number: int = 0
    total_generated: Dict[str, int] = Field(default_factory=dict)
    total_passed: Dict[str, int] = Field(default_factory=dict)
    consecutive_zeros: Dict[str, int] = Field(default_factory=dict)
    warm_start: bool = False


class SubspaceScheduler:
    """Stage 2 子空间调度器"""

    TOTAL_QUOTA = 12

    # 冷启动固定权重（来自金融文献研究）
    COLD_START_WEIGHTS: Dict[ExplorationSubspace, float] = {
        ExplorationSubspace.FACTOR_ALGEBRA: 0.33,
        ExplorationSubspace.NARRATIVE_MINING: 0.25,
        ExplorationSubspace.SYMBOLIC_MUTATION: 0.25,
        ExplorationSubspace.CROSS_MARKET: 0.17,
    }

    # 每个子空间最低保证配额
    MIN_QUOTA: Dict[ExplorationSubspace, int] = {
        ExplorationSubspace.FACTOR_ALGEBRA: 2,
        ExplorationSubspace.NARRATIVE_MINING: 1,
        ExplorationSubspace.SYMBOLIC_MUTATION: 1,
        ExplorationSubspace.CROSS_MARKET: 1,
    }

    WARM_START_THRESHOLD = 30  # 累计通过 30 个因子后切换（降低冷启动门槛）
    CONSECUTIVE_ZERO_WARNING = 3  # 连续 3 轮零通过触发警告

    # Thompson Sampling 采样次数
    _THOMPSON_SAMPLES = 1000

    def allocate(self, state: SchedulerState) -> List[SubspaceAllocation]:
        """
        根据当前状态分配各子空间配额。

        冷启动：使用固定权重。
        暖启动：使用 Thompson Sampling 自适应权重。
        """
        if not state.warm_start:
            weights = dict(self.COLD_START_WEIGHTS)
        else:
            weights = self._thompson_sampling_weights(state)

        enabled_subspaces = self._resolve_target_subspaces()
        if enabled_subspaces:
            weights = {
                subspace: weight
                for subspace, weight in weights.items()
                if subspace in enabled_subspaces
            }

        quotas = self._distribute_quota(weights)

        allocations = [
            SubspaceAllocation(
                subspace=subspace,
                quota=quotas[subspace],
                weight=weights[subspace],
            )
            for subspace in weights
        ]

        # 按权重降序排列
        allocations.sort(key=lambda a: a.weight, reverse=True)
        return allocations

    @staticmethod
    def _resolve_target_subspaces() -> List[ExplorationSubspace] | None:
        raw = os.getenv("PIXIU_TARGET_SUBSPACES", "").strip()
        if not raw:
            return None

        resolved: List[ExplorationSubspace] = []
        seen: set[ExplorationSubspace] = set()
        for item in raw.split(","):
            candidate = item.strip()
            if not candidate:
                continue
            try:
                subspace = ExplorationSubspace(candidate)
            except ValueError:
                continue
            if subspace not in seen:
                seen.add(subspace)
                resolved.append(subspace)
        return resolved or None

    def update_state(
        self,
        state: SchedulerState,
        results: Dict[ExplorationSubspace, Tuple[int, int]],
    ) -> SchedulerState:
        """
        根据本轮结果更新状态，返回新 state（不修改原 state）。

        results 格式: {subspace: (generated, passed)}
        """
        new_generated = dict(state.total_generated)
        new_passed = dict(state.total_passed)
        new_consecutive_zeros = dict(state.consecutive_zeros)

        for subspace in ExplorationSubspace:
            key = subspace.value
            generated, passed = results.get(subspace, (0, 0))

            new_generated[key] = new_generated.get(key, 0) + generated
            new_passed[key] = new_passed.get(key, 0) + passed

            if generated > 0 and passed == 0:
                new_consecutive_zeros[key] = new_consecutive_zeros.get(key, 0) + 1
            elif generated > 0:
                new_consecutive_zeros[key] = 0
            # generated == 0: keep consecutive_zeros unchanged

        total_passed_sum = sum(new_passed.values())
        warm_start = state.warm_start or (total_passed_sum >= self.WARM_START_THRESHOLD)

        return SchedulerState(
            round_number=state.round_number + 1,
            total_generated=new_generated,
            total_passed=new_passed,
            consecutive_zeros=new_consecutive_zeros,
            warm_start=warm_start,
        )

    def get_warnings(self, state: SchedulerState) -> List[str]:
        """检查连续零通过的子空间，返回警告消息列表。"""
        warnings: List[str] = []
        for subspace in ExplorationSubspace:
            key = subspace.value
            zeros = state.consecutive_zeros.get(key, 0)
            if zeros >= self.CONSECUTIVE_ZERO_WARNING:
                warnings.append(
                    f"子空间 {subspace.value} 已连续 {zeros} 轮零通过，建议检查假设生成质量"
                )
        return warnings

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _thompson_sampling_weights(
        self, state: SchedulerState
    ) -> Dict[ExplorationSubspace, float]:
        """使用 Thompson Sampling (Beta 分布) 计算自适应权重。

        当前实现通过 Monte Carlo 采样（_THOMPSON_SAMPLES 次）估计 Beta 均值。
        TODO (HIGH-4): 可替换为 Beta 分布解析解 E[X] = alpha / (alpha + beta)，
        消除随机性、提升性能，减少跨轮次权重抖动。
        替换后可移除 random 依赖和 _THOMPSON_SAMPLES 常量。
        """
        raw_weights: Dict[ExplorationSubspace, float] = {}

        for subspace in ExplorationSubspace:
            key = subspace.value
            generated = state.total_generated.get(key, 0)
            passed = state.total_passed.get(key, 0)

            alpha = passed + 1
            beta_param = (generated - passed) + 1

            # 采样多次取均值（解析解替换见上方 TODO）
            samples = [
                random.betavariate(alpha, beta_param)
                for _ in range(self._THOMPSON_SAMPLES)
            ]
            raw_weights[subspace] = sum(samples) / len(samples)

        # 归一化
        total = sum(raw_weights.values())
        if total == 0:
            # fallback to cold start weights
            return dict(self.COLD_START_WEIGHTS)

        return {s: w / total for s, w in raw_weights.items()}

    def _distribute_quota(
        self, weights: Dict[ExplorationSubspace, float]
    ) -> Dict[ExplorationSubspace, int]:
        """
        分配配额：先给每个子空间 MIN_QUOTA，剩余按权重比例分配。
        确保总和恒等于 TOTAL_QUOTA。
        """
        quotas: Dict[ExplorationSubspace, int] = {}
        enabled_subspaces = list(weights.keys()) or list(ExplorationSubspace)
        min_total = sum(self.MIN_QUOTA[subspace] for subspace in enabled_subspaces)
        remaining = self.TOTAL_QUOTA - min_total

        # 先分配最低配额
        for subspace in enabled_subspaces:
            quotas[subspace] = self.MIN_QUOTA[subspace]

        if remaining <= 0:
            return quotas

        # 按权重比例分配剩余配额（使用最大余数法确保总和精确）
        weight_total = sum(weights.values())
        if weight_total == 0:
            return quotas

        # 计算每个子空间的浮点配额
        fractional: Dict[ExplorationSubspace, float] = {}
        for subspace in enabled_subspaces:
            fractional[subspace] = (weights[subspace] / weight_total) * remaining

        # 先分配整数部分
        int_parts: Dict[ExplorationSubspace, int] = {}
        for subspace in enabled_subspaces:
            int_parts[subspace] = int(fractional[subspace])

        allocated = sum(int_parts.values())
        leftover = remaining - allocated

        # 按小数部分降序分配剩余的 1
        remainders = [
            (subspace, fractional[subspace] - int_parts[subspace])
            for subspace in enabled_subspaces
        ]
        remainders.sort(key=lambda x: x[1], reverse=True)

        for i, (subspace, _) in enumerate(remainders):
            if i < leftover:
                int_parts[subspace] += 1

        for subspace in enabled_subspaces:
            quotas[subspace] += int_parts[subspace]

        return quotas
