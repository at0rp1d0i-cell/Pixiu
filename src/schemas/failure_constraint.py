"""
Pixiu v2: FailureConstraint — 结构化失败经验约束

将 Stage 5 产生的失败经验从自然语言提升为可检索、可度量的结构化对象。
消费者：Stage 2（AlphaResearcher）、Stage 3（PreFilter ConstraintChecker）
生产者：Stage 5（ConstraintExtractor）
"""
from __future__ import annotations

import uuid
from datetime import datetime, UTC
from enum import Enum
from typing import Optional

from pydantic import Field

from src.schemas import PixiuBase


class FailureMode(str, Enum):
    """标准化失败模式分类"""
    LOW_SHARPE = "low_sharpe"
    HIGH_TURNOVER = "high_turnover"
    NO_IC = "no_ic"
    NEGATIVE_IC = "negative_ic"
    HIGH_DRAWDOWN = "high_drawdown"
    OVERFITTING = "overfitting"
    LOW_COVERAGE = "low_coverage"
    EXECUTION_ERROR = "execution_error"
    DUPLICATE = "duplicate"


class FailureConstraint(PixiuBase):
    """一条结构化的失败经验约束"""

    # 标识
    constraint_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_note_id: str
    source_verdict_id: str

    # 分类
    failure_mode: FailureMode
    island: str
    subspace: Optional[str] = None

    # 约束内容
    formula_pattern: str
    constraint_rule: str
    severity: str = "warning"  # "hard" | "warning"

    # 元数据 — override PixiuBase.created_at with str for ChromaDB compatibility
    created_at: str = Field(  # type: ignore[assignment]
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    times_violated: int = 0
    times_checked: int = 0
    last_violated_at: Optional[str] = None
