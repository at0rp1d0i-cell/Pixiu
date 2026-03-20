"""
Graph builder: build_graph, routing condition functions, and graph wiring.
"""
import logging

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from . import config as _config
from . import runtime as _runtime
from src.schemas.state import AgentState
from src.core.orchestrator._context import (
    NODE_MARKET_CONTEXT,
    NODE_HYPOTHESIS_GEN,
    NODE_SYNTHESIS,
    NODE_PREFILTER,
    NODE_EXPLORATION,
    NODE_NOTE_REFINEMENT,
    NODE_CODER,
    NODE_JUDGMENT,
    NODE_PORTFOLIO,
    NODE_REPORT,
    NODE_HUMAN_GATE,
    NODE_LOOP_CONTROL,
)
from src.core.orchestrator.nodes import (
    market_context_node,
    hypothesis_gen_node,
    synthesis_node,
    prefilter_node,
    exploration_node,
    note_refinement_node,
    coder_node,
    judgment_node,
    portfolio_node,
    report_node,
    human_gate_node,
    loop_control_node,
)

logger = logging.getLogger(__name__)
# ─────────────────────────────────────────────────────────
# 条件路由函数
# ─────────────────────────────────────────────────────────
def route_after_prefilter(state: AgentState) -> str:
    if not state.approved_notes:
        logger.info("[Route] prefilter → loop_control（无通过候选）")
        return NODE_LOOP_CONTROL
    has_exploration = any(
        note.exploration_questions
        for note in state.approved_notes
        if note.final_formula is None
    )
    target = NODE_EXPLORATION if has_exploration else NODE_CODER
    logger.info("[Route] prefilter → %s", target)
    return target


def route_after_judgment(state: AgentState) -> str:
    new_passes = [v for v in state.critic_verdicts if v.overall_passed]
    if new_passes:
        target = NODE_PORTFOLIO
    else:
        target = NODE_LOOP_CONTROL
    logger.info("[Route] judgment → %s（%d 个通过）", target, len(new_passes))
    return target


def route_after_portfolio(state: AgentState) -> str:
    """每 N 轮或有重大新发现时生成报告。"""
    report_every = _config.REPORT_EVERY_N_ROUNDS
    if state.current_round > 0 and state.current_round % report_every == 0:
        return NODE_REPORT
    from src.schemas.thresholds import THRESHOLDS
    has_breakthrough = any(
        r.metrics.sharpe > THRESHOLDS.min_sharpe * THRESHOLDS.breakthrough_sharpe_multiplier
        for r in state.backtest_reports
        if r.passed
    )
    if has_breakthrough:
        return NODE_REPORT
    return NODE_LOOP_CONTROL


def route_after_human(state: AgentState) -> str:
    decision = state.human_decision or "approve"
    if decision == "stop":
        logger.info("[Route] human_gate → END（用户停止）")
        return END
    if decision.startswith("redirect:"):
        logger.info("[Route] human_gate → hypothesis_gen（重定向）")
        return NODE_HYPOTHESIS_GEN
    logger.info("[Route] human_gate → loop_control（批准继续）")
    return NODE_LOOP_CONTROL


def route_loop(state: AgentState) -> str:
    max_rounds = _config.MAX_ROUNDS
    if state.current_round >= max_rounds:
        logger.info("[Route] loop_control → END（达到最大轮次 %d）", max_rounds)
        return END
    return NODE_MARKET_CONTEXT


# ─────────────────────────────────────────────────────────
# 图构建
# ─────────────────────────────────────────────────────────
def build_graph():
    """构建完整 v2 LangGraph 图。"""
    graph = StateGraph(AgentState)

    graph.add_node(NODE_MARKET_CONTEXT,  market_context_node)
    graph.add_node(NODE_HYPOTHESIS_GEN,  hypothesis_gen_node)
    graph.add_node(NODE_SYNTHESIS,       synthesis_node)
    graph.add_node(NODE_PREFILTER,       prefilter_node)
    graph.add_node(NODE_EXPLORATION,     exploration_node)
    graph.add_node(NODE_NOTE_REFINEMENT, note_refinement_node)
    graph.add_node(NODE_CODER,           coder_node)
    graph.add_node(NODE_JUDGMENT,        judgment_node)
    graph.add_node(NODE_PORTFOLIO,       portfolio_node)
    graph.add_node(NODE_REPORT,          report_node)
    graph.add_node(NODE_HUMAN_GATE,      human_gate_node)
    graph.add_node(NODE_LOOP_CONTROL,    loop_control_node)

    graph.add_edge(START,               NODE_MARKET_CONTEXT)
    graph.add_edge(NODE_MARKET_CONTEXT, NODE_HYPOTHESIS_GEN)
    graph.add_edge(NODE_HYPOTHESIS_GEN, NODE_SYNTHESIS)
    graph.add_edge(NODE_SYNTHESIS,      NODE_PREFILTER)
    graph.add_edge(NODE_EXPLORATION,    NODE_NOTE_REFINEMENT)
    graph.add_edge(NODE_NOTE_REFINEMENT,NODE_CODER)
    graph.add_edge(NODE_CODER,          NODE_JUDGMENT)

    graph.add_conditional_edges(NODE_PREFILTER, route_after_prefilter, {
        NODE_EXPLORATION:  NODE_EXPLORATION,
        NODE_CODER:        NODE_CODER,
        NODE_LOOP_CONTROL: NODE_LOOP_CONTROL,
    })
    graph.add_conditional_edges(NODE_JUDGMENT, route_after_judgment, {
        NODE_PORTFOLIO:    NODE_PORTFOLIO,
        NODE_LOOP_CONTROL: NODE_LOOP_CONTROL,
    })
    graph.add_conditional_edges(NODE_PORTFOLIO, route_after_portfolio, {
        NODE_REPORT:       NODE_REPORT,
        NODE_LOOP_CONTROL: NODE_LOOP_CONTROL,
    })
    graph.add_edge(NODE_REPORT, NODE_HUMAN_GATE)
    graph.add_conditional_edges(NODE_HUMAN_GATE, route_after_human, {
        NODE_LOOP_CONTROL:   NODE_LOOP_CONTROL,
        NODE_HYPOTHESIS_GEN: NODE_HYPOTHESIS_GEN,
        END:                 END,
    })
    graph.add_conditional_edges(NODE_LOOP_CONTROL, route_loop, {
        NODE_MARKET_CONTEXT: NODE_MARKET_CONTEXT,
        END:                 END,
    })

    return graph.compile(checkpointer=MemorySaver())


def get_graph():
    """获取编译好的图单例（供 CLI 的 approve/redirect/stop 注入状态）。"""
    graph = _runtime.get_graph()
    if graph is None:
        graph = build_graph()
        _runtime.set_graph(graph)
    return graph


def get_latest_config() -> dict:
    """获取最近一次 run 的 LangGraph config（供 CLI 注入 human_decision）。"""
    return _runtime.get_graph_config()
