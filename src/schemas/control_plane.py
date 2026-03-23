from datetime import datetime

from src.schemas import PixiuBase


class RunRecord(PixiuBase):
    run_id: str
    mode: str
    status: str
    current_round: int = 0
    current_stage: str = "pending"
    started_at: datetime
    finished_at: datetime | None = None
    last_error: str | None = None


class RunSnapshot(PixiuBase):
    run_id: str
    approved_notes_count: int = 0
    backtest_reports_count: int = 0
    verdicts_count: int = 0
    llm_calls: int = 0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    llm_total_tokens: int = 0
    llm_estimated_cost_usd: float = 0.0
    awaiting_human_approval: bool = False
    updated_at: datetime


class ArtifactRecord(PixiuBase):
    run_id: str
    kind: str
    ref_id: str
    path: str


class HumanDecisionRecord(PixiuBase):
    run_id: str
    action: str
