"""Stage I/O typed output contracts for each LangGraph node.

TypedDict subclasses keep return types explicit and IDE-navigable
while remaining fully compatible with LangGraph's dict-based state reducer.
Nodes that can short-circuit (synthesis, note_refinement) use ``total=False``
so callers can safely return empty dicts.

每个 LangGraph 节点的类型化输出契约。
TypedDict 子类保持返回类型明确且 IDE 可导航，同时与 LangGraph
基于 dict 的 state reducer 完全兼容。
可短路的节点（synthesis、note_refinement）使用 total=False，
以便安全返回空字典。
"""

from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict

from src.schemas.market_context import MarketContextMemo
from src.schemas.research_note import FactorResearchNote, SynthesisInsight
from src.schemas.hypothesis import Hypothesis, StrategySpec
from src.schemas.backtest import BacktestReport
from src.schemas.exploration import ExplorationResult
from src.schemas.judgment import CriticVerdict, RiskAuditReport, PortfolioAllocation, CIOReport

StageTimings = dict[str, float]
StageStepTimings = dict[str, dict[str, float]]


# ── Stage 1 ────────────────────────────────────────────────────────────────────

class MarketContextOutput(TypedDict, total=False):
    """Output of market_context_node (Stage 1).

    On success: market_context is populated.
    On failure: last_error and error_stage are set instead.

    market_context_node（Stage 1）的输出类型。
    成功时填充 market_context；失败时设置 last_error 和 error_stage。
    """

    market_context: MarketContextMemo
    stage_timings: StageTimings
    stage_step_timings: StageStepTimings
    last_error: str
    error_stage: str


# ── Stage 2 ────────────────────────────────────────────────────────────────────

class HypothesisGenOutput(TypedDict, total=False):
    """Output of hypothesis_gen_node (Stage 2a).

    Parallel island calls populate research_notes, hypotheses, strategy_specs,
    and subspace_generated. Error fields are set on failure.

    hypothesis_gen_node（Stage 2a）的输出类型。
    并行 island 调用填充研究笔记、假设、策略规格和子空间生成计数。
    """

    research_notes: list[FactorResearchNote]
    hypotheses: list[Hypothesis]
    strategy_specs: list[StrategySpec]
    subspace_generated: dict[str, int]
    stage2_diagnostics: dict[str, Any]
    stage_timings: StageTimings
    stage_step_timings: StageStepTimings
    last_error: str
    error_stage: str


class SynthesisOutput(TypedDict, total=False):
    """Output of synthesis_node (Stage 2b).

    Returns an empty dict when skipped (<=1 candidate) or on failure,
    so the upstream research_notes pass through unchanged.

    synthesis_node（Stage 2b）的输出类型。
    候选数 <=1 或失败时返回空字典，上游 research_notes 原样透传。
    """

    research_notes: list[FactorResearchNote]
    synthesis_insights: list[SynthesisInsight]
    stage_timings: StageTimings
    stage_step_timings: StageStepTimings


class NoteRefinementOutput(TypedDict, total=False):
    """Output of note_refinement_node (Stage 4a→2).

    Returns an empty dict when there are no exploration_results,
    leaving approved_notes unchanged in state.

    note_refinement_node（Stage 4a→2）的输出类型。
    无探索结果时返回空字典，state 中的 approved_notes 保持不变。
    """

    approved_notes: list[FactorResearchNote]
    stage_timings: StageTimings
    stage_step_timings: StageStepTimings


# ── Stage 3 ────────────────────────────────────────────────────────────────────


class PrefilterRejectionSample(TypedDict):
    """Single Stage 3 rejection sample for diagnostics."""

    note_id: str
    filter: str
    reason: str


class PrefilterDiagnostics(TypedDict):
    """Compact Stage 3 diagnostics payload."""

    input_count: int
    approved_count: int
    rejection_counts_by_filter: dict[str, int]
    sample_rejections: list[PrefilterRejectionSample]


class PrefilterOutput(TypedDict):
    """Output of prefilter_node (Stage 3).

    approved_notes contains the subset that passed all hard gates.
    filtered_count records how many were rejected for diagnostics.
    prefilter_diagnostics stores compact rejection counters and samples.

    prefilter_node（Stage 3）的输出类型。
    approved_notes 包含通过所有硬 gate 的子集；filtered_count 记录淘汰数量。
    """

    approved_notes: list[FactorResearchNote]
    filtered_count: int
    prefilter_diagnostics: PrefilterDiagnostics
    stage_timings: StageTimings
    stage_step_timings: StageStepTimings


# ── Stage 4 ────────────────────────────────────────────────────────────────────

class ExplorationOutput(TypedDict):
    """Output of exploration_node (Stage 4a).

    exploration_results is always a list (may be empty if nothing needed exploration).

    exploration_node（Stage 4a）的输出类型。
    exploration_results 始终为列表（无需探索时为空列表）。
    """

    exploration_results: list[ExplorationResult]
    stage_timings: StageTimings
    stage_step_timings: StageStepTimings


class CoderOutput(TypedDict):
    """Output of coder_node (Stage 4b).

    backtest_reports accumulates across rounds (prepended to state's existing list).
    approved_notes reflects status='completed' for each executed note.

    coder_node（Stage 4b）的输出类型。
    backtest_reports 跨轮次累积；approved_notes 中每个执行完成的 note 状态更新为 completed。
    """

    backtest_reports: list[BacktestReport]
    approved_notes: list[FactorResearchNote]
    stage_timings: StageTimings
    stage_step_timings: StageStepTimings


# ── Stage 5 ────────────────────────────────────────────────────────────────────

class JudgmentOutput(TypedDict):
    """Output of judgment_node (Stage 5a).

    critic_verdicts and risk_audit_reports are parallel arrays indexed by backtest report.

    judgment_node（Stage 5a）的输出类型。
    critic_verdicts 和 risk_audit_reports 是与 backtest_reports 并行对齐的数组。
    """

    critic_verdicts: list[CriticVerdict]
    risk_audit_reports: list[RiskAuditReport]
    stage_timings: StageTimings
    stage_step_timings: StageStepTimings


class PortfolioOutput(TypedDict, total=False):
    """Output of portfolio_node (Stage 5b).

    On success: portfolio_allocation is populated.
    On failure: last_error and error_stage are set instead.

    portfolio_node（Stage 5b）的输出类型。
    成功时填充 portfolio_allocation；失败时设置 last_error 和 error_stage。
    """

    portfolio_allocation: PortfolioAllocation
    stage_timings: StageTimings
    stage_step_timings: StageStepTimings
    last_error: str
    error_stage: str


class ReportOutput(TypedDict, total=False):
    """Output of report_node (Stage 5c).

    On success: cio_report, awaiting_human_approval=True, human_decision=None.
    On failure: last_error and error_stage are set; awaiting_human_approval is still True
    so the human gate is not bypassed.

    report_node（Stage 5c）的输出类型。
    成功时填充 cio_report，awaiting_human_approval=True，human_decision=None。
    失败时设置 last_error 和 error_stage；awaiting_human_approval 仍为 True，不绕过人工审批门。
    """

    cio_report: CIOReport
    awaiting_human_approval: bool
    human_decision: Optional[str]
    stage_timings: StageTimings
    stage_step_timings: StageStepTimings
    last_error: str
    error_stage: str


# ── Control nodes ──────────────────────────────────────────────────────────────

class HumanGateOutput(TypedDict, total=False):
    """Output of human_gate_node.

    human_gate_node 从 control plane 读取最新的人类决策，并将其写回 state。
    """

    human_decision: Optional[str]
    awaiting_human_approval: bool
    stage_timings: StageTimings
    stage_step_timings: StageStepTimings


class LoopControlOutput(TypedDict):
    """Output of loop_control_node — resets all per-round mutable state.

    Advances current_round and persists updated SubspaceScheduler state;
    all ephemeral per-round lists are reset to empty.

    loop_control_node 的输出类型，重置所有每轮可变状态。
    递增 current_round 并持久化更新后的 SubspaceScheduler 状态；
    所有每轮临时列表重置为空。
    """

    current_round: int
    scheduler_state: dict
    research_notes: list[FactorResearchNote]
    approved_notes: list[FactorResearchNote]
    subspace_generated: dict[str, int]
    stage2_diagnostics: dict[str, Any]
    stage1_reliability: dict[str, Any]
    filtered_count: int
    prefilter_diagnostics: PrefilterDiagnostics
    exploration_results: list[ExplorationResult]
    backtest_reports: list[BacktestReport]
    critic_verdicts: list[CriticVerdict]
    risk_audit_reports: list[RiskAuditReport]
    awaiting_human_approval: bool
    human_decision: Optional[str]
    last_error: Optional[str]
    error_stage: Optional[str]
    stage_timings: StageTimings
    stage_step_timings: StageStepTimings
