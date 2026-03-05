"""
EvoQuant: LangGraph Orchestrator
Role: Wires Researcher, Coder, and Critic nodes into a stateful cyclic graph.
"""
import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
from langgraph.graph import StateGraph, START, END
from src.agents.state import AgentState
from src.agents.researcher import research_node
from src.agents.validator import validator_node, route_validation
from src.agents.coder import coder_node
from src.agents.critic import critic_node, route_eval
from src.factor_pool.pool import get_factor_pool
from src.agents.schemas import FactorHypothesis, BacktestMetrics
from src.factor_pool.scheduler import IslandScheduler

def build_graph() -> StateGraph:
    logging.info("[EvoQuant Orchestrator] 构建 LangGraph 引擎...")
    
    # 1. Initialize StateGraph
    workflow = StateGraph(AgentState)
    
    # 2. Add Nodes
    workflow.add_node("researcher", research_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("coder", coder_node)
    workflow.add_node("critic", critic_node)
    
    # 3. Add Edges (Linear Path)
    workflow.add_edge(START, "researcher")
    workflow.add_edge("researcher", "validator")
    
    workflow.add_conditional_edges(
        "validator",
        route_validation,
        {
            "proceed_to_coder": "coder",
            "loop_to_researcher": "researcher"
        }
    )
    
    workflow.add_edge("coder", "critic")
    
    # 4. Add Conditional Routing (A/B Test loops)
    workflow.add_conditional_edges(
        "critic",
        route_eval,
        {
            "loop": "researcher",
            "end": END
        }
    )
    
    # 5. Compile the graph
    app = workflow.compile()
    return app

def run_layer1_ab_test(island_name: str = "momentum"):
    """
    运行基于 Layer 1 (quant_factors_dictionary) 的控制变量测试实验

    Args:
        island_name: 本轮激活的 Island（因子研究方向），默认 'momentum'
    """
    app = build_graph()
    pool = get_factor_pool()
    
    # 初始化状态（新增 factor_hypothesis、backtest_metrics、island_name）
    initial_state = {
        "messages": [],
        "factor_proposal": "",
        "factor_hypothesis": None,
        "code_snippet": "",
        "backtest_result": "",
        "backtest_metrics": None,
        "error_message": "",
        "current_iteration": 0,
        "max_iterations": 3,
        # Island 信息（注入给 Researcher 的上下文）
        "island_name": island_name,
    }
    
    logging.info("\n" + "=" * 60)
    logging.info("🚀 启动大逃杀: Agent (Layer 1) vs Alpha158 Baseline (Sharpe: 2.67)")
    logging.info("=" * 60)
    
    try:
        final_state = app.invoke(initial_state)
        logging.info("\n=== 回测探索结束 ===")
        logging.info(f"最终状态迭代次数: {final_state['current_iteration']}")

        # ── 注册最终因子到 FactorPool ───────────────────────────
        hypothesis = final_state.get("factor_hypothesis")
        metrics = final_state.get("backtest_metrics")

        if hypothesis and metrics and metrics.parse_success:
            pool.register(
                hypothesis=hypothesis,
                metrics=metrics,
                island_name=island_name,
            )
            logging.info(
                "[Orchestrator] 因子已注册到 FactorPool → Island=%s, Sharpe=%.2f",
                island_name, metrics.sharpe,
            )
        else:
            logging.info("[Orchestrator] 本轮无有效回测结果，跳过 FactorPool 注册")

        # 打印排行榜
        leaderboard = pool.get_island_leaderboard()
        if leaderboard:
            logging.info("\n=== Island 排行榜 ===")
            for rank, item in enumerate(leaderboard, 1):
                logging.info(
                    "  #%d %s（%s）: best_sharpe=%.2f, 已实验=%d 个因子",
                    rank, item["island_display_name"], item["island"],
                    item["best_sharpe"], item["factor_count"],
                )

    except Exception as e:
        logging.info(f"执行引擎异常退出: {e}")

def run_evolution_loop(max_rounds: int = 20):
    """
    Island 进化大循环：多方向轮换搜索，直到找到超越基线的因子或达到最大轮次。

    Args:
        max_rounds: 最大大轮次数（每轮 = 一次完整 Researcher→Coder→Critic epoch）
                    建议：测试用 5，正式搜索用 20-50
    """
    app = build_graph()
    pool = get_factor_pool()
    scheduler = IslandScheduler(pool)

    logging.info("\n" + "=" * 60)
    logging.info("🧬 启动 Island 进化搜索（最大 %d 轮）", max_rounds)
    logging.info("=" * 60)

    best_sharpe_ever = 0.0
    best_factor_ever = None

    for round_n in range(max_rounds):
        logging.info("\n─── 第 %d / %d 大轮 ───────────────────────────────", round_n + 1, max_rounds)

        # 1. 选 Island
        island_name = scheduler.select_island()
        island_display = __import__(
            "src.factor_pool.islands", fromlist=["ISLANDS"]
        ).ISLANDS.get(island_name, {}).get("name", island_name)
        logging.info("[Orchestrator] 激活 Island: %s（%s）", island_name, island_display)

        # 2. 构建本轮初始状态
        initial_state = {
            "messages": [],
            "factor_proposal": "",
            "factor_hypothesis": None,
            "code_snippet": "",
            "backtest_result": "",
            "backtest_metrics": None,
            "error_message": "",
            "current_iteration": 0,
            "max_iterations": 3,
            "island_name": island_name,
        }

        # 3. 跑一个 epoch（Researcher → Validator → Coder → Critic，最多 3 次内循环）
        try:
            final_state = app.invoke(initial_state)
        except Exception as e:
            logging.error("[Orchestrator] 第 %d 轮 epoch 异常：%s", round_n + 1, e)
            scheduler.on_epoch_done(island_name, round_n)
            continue

        # 4. 注册结果到 FactorPool
        hypothesis = final_state.get("factor_hypothesis")
        metrics = final_state.get("backtest_metrics")

        if hypothesis and metrics and metrics.parse_success:
            pool.register(
                hypothesis=hypothesis,
                metrics=metrics,
                island_name=island_name,
            )
            sharpe = metrics.sharpe
            logging.info(
                "[Orchestrator] 注册因子 '%s'：Sharpe=%.2f, IC=%.4f, ICIR=%.2f",
                hypothesis.name, sharpe, metrics.ic, metrics.icir,
            )

            # 追踪全局最优
            if sharpe > best_sharpe_ever:
                best_sharpe_ever = sharpe
                best_factor_ever = hypothesis
                logging.info(
                    "🌟 新全局最优！Sharpe=%.2f，因子：%s",
                    best_sharpe_ever, best_factor_ever.name,
                )

            # 突破基线 → 提前终止
            if sharpe > 2.67 and metrics.ic > 0.02 and metrics.icir > 0.3:
                logging.info("\n🎉 基线突破！终止进化搜索。")
                break
        else:
            logging.info("[Orchestrator] 第 %d 轮无有效回测结果", round_n + 1)

        # 5. 调度器后处理（退火 + 重置检查）
        scheduler.on_epoch_done(island_name, round_n)

        # 6. 打印当前排行榜（每 5 轮一次）
        if (round_n + 1) % 5 == 0:
            _print_leaderboard(pool, scheduler)

    # 最终汇报
    _print_final_report(pool, best_sharpe_ever, best_factor_ever, round_n + 1)


def _print_leaderboard(pool: object, scheduler: "IslandScheduler") -> None:
    """打印 Island 排行榜。"""
    status = scheduler.get_status()
    logging.info("\n=== Island 排行榜（第 %d 轮，T=%.2f）===", status["round"], status["temperature"])
    leaderboard = pool.get_island_leaderboard()
    for rank, item in enumerate(leaderboard, 1):
        active_mark = "✓" if item["island"] in status["active_islands"] else " "
        logging.info(
            "  [%s] #%d %-12s best=%.2f  avg=%.2f  n=%d  最优因子: %s",
            active_mark, rank,
            item["island_display_name"],
            item["best_sharpe"],
            item["avg_sharpe"],
            item["factor_count"],
            item["best_factor_name"],
        )


def _print_final_report(pool: object, best_sharpe: float, best_factor: object, total_rounds: int) -> None:
    """打印最终汇报。"""
    stats = pool.get_stats()
    logging.info("\n" + "=" * 60)
    logging.info("🏁 进化搜索结束")
    logging.info("  总轮次: %d", total_rounds)
    logging.info("  总实验因子数: %d", stats["total_factors"])
    logging.info("  突破基线因子数: %d", stats["beats_baseline_count"])
    logging.info("  全局最优 Sharpe: %.2f", best_sharpe)
    if best_factor:
        logging.info("  最优因子: %s", best_factor.name)
        logging.info("  最优公式: %s", best_factor.formula)
    logging.info("=" * 60)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="EvoQuant Orchestrator")
    parser.add_argument("--mode", choices=["single", "evolve"], default="evolve",
                        help="single: 单 Island 单次运行；evolve: Island 进化大循环")
    parser.add_argument("--island", default="momentum",
                        help="single 模式下指定 Island")
    parser.add_argument("--rounds", type=int, default=20,
                        help="evolve 模式下的最大大轮次数")
    args = parser.parse_args()

    if args.mode == "single":
        run_layer1_ab_test(island_name=args.island)
    else:
        run_evolution_loop(max_rounds=args.rounds)
