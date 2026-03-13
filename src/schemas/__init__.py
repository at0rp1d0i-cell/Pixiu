from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

class PixiuBase(BaseModel):
    """所有 Pixiu schema 的基类"""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    version: str = Field(default="2.0")

    class Config:
        extra = "forbid"  # 禁止额外字段，强制接口显式


from src.schemas.control_plane import (
    ArtifactRecord,
    HumanDecisionRecord,
    RunRecord,
    RunSnapshot,
)

from src.schemas.hypothesis import (
    Hypothesis,
    StrategySpec,
    ExplorationSubspace,
    MutationOperator,
    RegimeCondition,
)

from src.schemas.exploration import (
    PrimitiveCategory,
    SubspaceConfig,
    ExplorationStrategy,
    SubspaceRegistry,
)

__all__ = [
    "PixiuBase",
    "RunRecord",
    "RunSnapshot",
    "ArtifactRecord",
    "HumanDecisionRecord",
    "Hypothesis",
    "StrategySpec",
    "ExplorationSubspace",
    "MutationOperator",
    "RegimeCondition",
    "PrimitiveCategory",
    "SubspaceConfig",
    "ExplorationStrategy",
    "SubspaceRegistry",
]
