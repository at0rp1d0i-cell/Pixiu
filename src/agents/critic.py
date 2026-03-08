"""
Pixiu: Critic Agent（结构化增强版）
Role: 从回测日志解析多维度指标，评估因子质量，决定路由。
评估标准：Sharpe > 基线 AND IC > 0.02 AND ICIR > 0.3 AND 换手率 < 50%
"""
import logging
import re
from .state import AgentState
from .schemas import BacktestMetrics

logger = logging.getLogger(__name__)

# ── 基线与阈值 ──────────────────────────────────────────────────
BASELINE_SHARPE = 2.67   # Phase 1 Alpha158+LightGBM 基线
MIN_IC = 0.02            # IC 均值最低门槛（低于此 = 无效因子）
MIN_ICIR = 0.3           # ICIR 稳定性门槛
MAX_TURNOVER = 50.0      # 日均换手率上限（%），超过手续费会吃掉收益


def _parse_metrics(log: str) -> BacktestMetrics:
    """从回测日志中提取结构化指标。

    优先尝试解析 JSON 格式输出；回退到正则解析自由文本。
    """
    import json

    if not log:
        return BacktestMetrics()

    # ── 优先路径：解析 JSON ──────────────────────────────────────
    json_match = re.search(r"BACKTEST_METRICS_JSON:\s*(\{.*?\})", log, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return BacktestMetrics(
                sharpe=float(data.get("sharpe", 0.0)),
                annualized_return=float(data.get("annualized_return", 0.0)),
                max_drawdown=float(data.get("max_drawdown", 0.0)),
                ic=float(data.get("ic", 0.0)),
                icir=float(data.get("icir", 0.0)),
                turnover=float(data.get("turnover", 0.0)),
                win_rate=float(data.get("win_rate", 0.0)),
                parse_success=True,
                raw_log_tail=log[-500:],
            )
        except Exception:
            pass  # 降级到正则

    # ── 降级路径：正则解析 ──────────────────────────────────────
    def _find(pattern, default=0.0):
        m = re.search(pattern, log)
        try:
            return float(m.group(1)) if m else default
        except (ValueError, AttributeError):
            return default

    sharpe   = _find(r"夏普比率[:：]\s*([-\d\.]+)")
    ann_ret  = _find(r"年化收益率?[:：]\s*([-\d\.]+)")
    max_dd   = _find(r"最大回撤[:：]\s*([-\d\.]+)")
    ic       = _find(r"\bIC均值?[:：]\s*([-\d\.]+)")
    icir     = _find(r"\bICIR[:：]\s*([-\d\.]+)")
    turnover = _find(r"换手率[:：]\s*([-\d\.]+)")

    parse_success = sharpe != 0.0  # 至少解析到 Sharpe 才算成功

    return BacktestMetrics(
        sharpe=sharpe,
        annualized_return=ann_ret,
        max_drawdown=max_dd,
        ic=ic,
        icir=icir,
        turnover=turnover,
        parse_success=parse_success,
        raw_log_tail=log[-500:],
    )


def _evaluate(metrics: BacktestMetrics, has_error: bool) -> tuple[str, str]:
    """
    多维度评估，返回 (route, reason)。
    route: "end"（成功）| "loop"（继续迭代）
    reason: 给 Researcher 下一轮参考的中文反馈
    """
    if has_error:
        return "loop", "代码执行报错，请检查 Qlib 表达式语法和数据列名。"

    if not metrics.parse_success:
        return "loop", "未能从回测日志解析到有效指标，请确认 Coder 输出格式正确。"

    reasons = []

    # ── 核心指标检查 ─────────────────────────────────────────────
    if metrics.sharpe <= BASELINE_SHARPE:
        reasons.append(f"Sharpe {metrics.sharpe:.2f} 未超越基线 {BASELINE_SHARPE}")

    if metrics.ic != 0.0 and metrics.ic < MIN_IC:
        reasons.append(f"IC均值 {metrics.ic:.4f} 低于门槛 {MIN_IC}（因子预测能力不足）")

    if metrics.icir != 0.0 and metrics.icir < MIN_ICIR:
        reasons.append(f"ICIR {metrics.icir:.2f} 低于门槛 {MIN_ICIR}（因子不够稳定）")

    if metrics.turnover != 0.0 and metrics.turnover > MAX_TURNOVER:
        reasons.append(f"日均换手率 {metrics.turnover:.1f}% 过高（手续费将吃掉大部分收益）")

    if reasons:
        feedback = "；".join(reasons) + "。请考虑：(1) 换一个方向的因子，(2) 降低因子换手（加长均线周期），(3) 检查因子是否存在前视偏差。"
        return "loop", feedback

    # ── 全部通过 ─────────────────────────────────────────────────
    return "end", (
        f"因子通过全部评估！Sharpe={metrics.sharpe:.2f}, "
        f"IC={metrics.ic:.4f}, ICIR={metrics.icir:.2f}, "
        f"换手率={metrics.turnover:.1f}%"
    )


def critic_node(state: AgentState) -> dict:
    logger.info("[Critic] 开始多维度因子评估...")

    log = state.get("backtest_result", "")
    error = state.get("error_message", "")
    current_iter = state.get("current_iteration", 0) + 1

    metrics = _parse_metrics(log)
    route, reason = _evaluate(metrics, bool(error))

    # 日志输出
    if route == "end":
        logger.info("[Critic] ✅ %s", reason)
    else:
        logger.info("[Critic] 🔄 第 %d/%d 轮未达标：%s",
                    current_iter, state.get("max_iterations", 3), reason)

    return {
        "current_iteration": current_iter,
        "backtest_metrics": metrics,
        # 把评估原因写入 error_message，Researcher 下一轮可以读到
        "error_message": reason if route == "loop" else "",
    }


def route_eval(state: AgentState) -> str:
    """LangGraph 路由函数。"""
    current_iter = state.get("current_iteration", 0)
    max_iter = state.get("max_iterations", 3)

    if current_iter >= max_iter:
        logger.info("[Critic] ⚠️ 达到最大迭代次数 %d，强制终止。", current_iter)
        return "end"

    metrics = state.get("backtest_metrics")
    error = state.get("error_message", "")

    # 如果 backtest_metrics 存在，用已解析的结果路由
    if metrics and isinstance(metrics, BacktestMetrics):
        if error:  # critic_node 把失败原因写入 error_message
            return "loop"
        route, _ = _evaluate(metrics, False)
        return route

    # 兼容旧路径：backtest_metrics 为空时降级到正则
    backtest = state.get("backtest_result", "")
    if backtest:
        m = re.search(r"夏普比率[:：]\s*([-\d\.]+)", backtest)
        if m and float(m.group(1)) > BASELINE_SHARPE:
            return "end"

    return "loop"
