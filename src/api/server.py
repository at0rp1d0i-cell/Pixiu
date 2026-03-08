"""
Pixiu v2 FastAPI 后端 API Server

端点：
  GET /api/status   ← 当前运行状态
  GET /api/factors  ← 因子排行榜
  GET /api/islands  ← Island 状态
  GET /api/reports  ← CIO 报告列表
  POST /api/approve ← 注入 human_decision

启动方式：
  uvicorn src.api.server:api --host 0.0.0.0 --port 8080 --reload
"""
import os
import sys
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

api = FastAPI(
    title="Pixiu v2 API",
    version="2.0.0",
    description="Pixiu 自主量化研究平台 - 管理接口",
)

# 允许前端 Vite dev server 跨域访问
api.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# /api/status
# ─────────────────────────────────────────────
@api.get("/api/status")
def get_status():
    """获取系统运行状态和全局统计。"""
    try:
        from src.factor_pool.pool import get_factor_pool
        pool = get_factor_pool()
        stats = pool.get_stats()
        return {
            "status": "running",
            "total_factors": stats.get("total_factors", 0),
            "beats_baseline_count": stats.get("beats_baseline_count", 0),
            "global_best_sharpe": stats.get("global_best_sharpe", 0.0),
            "global_avg_sharpe": stats.get("global_avg_sharpe", 0.0),
        }
    except Exception as e:
        return {"status": "idle", "error": str(e)}


# ─────────────────────────────────────────────
# /api/factors
# ─────────────────────────────────────────────
@api.get("/api/factors")
def get_factors(island: Optional[str] = None, limit: int = 20):
    """获取因子排行榜（按 Sharpe 降序）。"""
    from src.factor_pool.pool import get_factor_pool
    pool = get_factor_pool()
    results = pool.get_top_factors(limit=limit * 2)
    if island:
        results = [r for r in results if r.get("island") == island]
    return results[:limit]


# ─────────────────────────────────────────────
# /api/islands
# ─────────────────────────────────────────────
@api.get("/api/islands")
def get_islands():
    """获取各 Island 的统计数据和排名。"""
    from src.factor_pool.pool import get_factor_pool
    from src.factor_pool.islands import ISLANDS
    pool = get_factor_pool()
    leaderboard = pool.get_island_leaderboard()

    # 补充 FactorPool 中没有数据的 Island
    existing_islands = {item["island"] for item in leaderboard}
    for island_id, info in ISLANDS.items():
        if island_id not in existing_islands:
            leaderboard.append({
                "island": island_id,
                "island_display_name": info.get("name", island_id),
                "factor_count": 0,
                "best_sharpe": 0.0,
                "avg_sharpe": 0.0,
                "best_factor_name": "—",
            })

    return leaderboard


# ─────────────────────────────────────────────
# /api/reports
# ─────────────────────────────────────────────
@api.get("/api/reports")
def get_reports():
    """获取 CIO 报告列表（暂时从 FactorPool 摘要生成）。"""
    from src.factor_pool.pool import get_factor_pool
    pool = get_factor_pool()
    stats = pool.get_stats()
    leaderboard = pool.get_island_leaderboard()

    return [{
        "id": "latest",
        "title": "Pixiu v2 因子库摘要报告",
        "total_factors": stats.get("total_factors", 0),
        "beats_baseline": stats.get("beats_baseline_count", 0),
        "best_sharpe": stats.get("global_best_sharpe", 0.0),
        "island_summary": [
            {
                "island": item["island"],
                "best_sharpe": item["best_sharpe"],
                "factor_count": item["factor_count"],
            }
            for item in leaderboard
        ],
    }]


# ─────────────────────────────────────────────
# POST /api/approve
# ─────────────────────────────────────────────
class ApproveRequest(BaseModel):
    action: str  # "approve" | "redirect:xxx" | "stop"


@api.post("/api/approve")
def post_approve(body: ApproveRequest):
    """向 LangGraph 注入 human_decision（审批/重定向/停止）。"""
    valid_actions = {"approve", "stop"}
    action = body.action
    is_valid = action in valid_actions or action.startswith("redirect:")
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"无效的 action: {action}")

    try:
        from src.core.orchestrator import get_graph, get_latest_config
        graph = get_graph()
        config = get_latest_config()
        if not config:
            raise HTTPException(status_code=404, detail="找不到正在运行的实验（LangGraph config 未初始化）")
        graph.update_state(
            config,
            {"human_decision": action, "awaiting_human_approval": False},
            as_node="human_gate",
        )
        return {"ok": True, "action": action}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# 健康检查
# ─────────────────────────────────────────────
@api.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}
