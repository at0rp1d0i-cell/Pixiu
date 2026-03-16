from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any
from enum import Enum

class PixiuBase(BaseModel):
    """所有 Pixiu schema 的基类"""
    model_config = ConfigDict(extra="forbid")

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: str = Field(default="2.0")


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
    FactorPrimitive,
    MarketMechanismTemplate,
    NarrativeCategory,
    MutationRecord,
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
    "FactorPrimitive",
    "MarketMechanismTemplate",
    "NarrativeCategory",
    "MutationRecord",
]
