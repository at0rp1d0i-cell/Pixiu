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
