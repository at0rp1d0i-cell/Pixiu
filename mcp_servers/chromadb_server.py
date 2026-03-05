"""
EvoQuant ChromaDB MCP Server
工具：FactorPool 查询（Island 最优、相似失败、排行榜）
注意：只读查询工具，写入通过 orchestrator 直接调用 pool.register()
启动：python mcp_servers/chromadb_server.py
"""
import json
import logging
import sys
import os

# 把项目根目录加入 path（MCP Server 作为独立进程启动）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp.server.fastmcp import FastMCP
from src.factor_pool.pool import get_factor_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("chromadb-mcp")

app = FastMCP("chromadb-mcp")
_pool = get_factor_pool()


@app.tool()
def get_island_best_factors(island_name: str, top_k: int = 3) -> str:
    """获取指定 Island 中历史 Sharpe 最高的因子（供 Researcher 参考）。

    Args:
        island_name: Island 名称，可选值：momentum / northbound / valuation /
                     volatility / volume / sentiment
        top_k: 返回数量，默认 3，最大 5

    返回：JSON 数组，每项包含因子名、公式、Sharpe、IC、ICIR、换手率。
    用途：Researcher 在提新因子前，先了解该方向前人已达到的水平。
    """
    top_k = min(max(top_k, 1), 5)
    try:
        results = _pool.get_island_best_factors(island_name, top_k)
        # 精简返回字段，避免 context 过长
        slim = [
            {
                "factor_name": r["factor_name"],
                "formula": r["formula"],
                "sharpe": r["sharpe"],
                "ic": r["ic"],
                "icir": r["icir"],
                "turnover": r["turnover"],
                "hypothesis": r["hypothesis"],
            }
            for r in results
        ]
        return json.dumps(slim, ensure_ascii=False)
    except Exception as e:
        logger.error("get_island_best_factors error: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@app.tool()
def get_similar_failures(formula: str, top_k: int = 3) -> str:
    """根据当前因子公式，检索历史上相似的失败案例及其原因。

    Args:
        formula: 当前计划提出的 Qlib 因子公式
        top_k: 返回数量，默认 3

    返回：JSON 数组，每项包含相似因子的公式、失败原因摘要。
    用途：避免重蹈覆辙，让 Researcher 知道哪些方向已被验证无效。
    """
    top_k = min(max(top_k, 1), 5)
    try:
        results = _pool.get_similar_failures(formula, top_k)
        slim = [
            {
                "factor_name": r["factor_name"],
                "formula": r["formula"],
                "failure_reason": r["failure_reason"],
                "sharpe": r["sharpe"],
            }
            for r in results
        ]
        return json.dumps(slim, ensure_ascii=False)
    except Exception as e:
        logger.error("get_similar_failures error: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@app.tool()
def get_island_leaderboard() -> str:
    """获取所有 Island 的 Sharpe 排行榜。

    返回：JSON 数组，按 best_sharpe 降序，每项包含 Island 名称、因子数量、
    最高/平均 Sharpe、最优因子名称。
    用途：让 Researcher 了解哪个研究方向目前最有潜力。
    """
    try:
        results = _pool.get_island_leaderboard()
        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        logger.error("get_island_leaderboard error: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@app.tool()
def get_pool_stats() -> str:
    """获取 FactorPool 全局统计（总因子数、超越基线数、全局最优 Sharpe）。

    用途：让 Researcher 了解当前实验进度的全貌。
    """
    try:
        stats = _pool.get_stats()
        return json.dumps(stats, ensure_ascii=False)
    except Exception as e:
        logger.error("get_pool_stats error: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


if __name__ == "__main__":
    logger.info("ChromaDB MCP Server starting...")
    app.run(transport="stdio")
