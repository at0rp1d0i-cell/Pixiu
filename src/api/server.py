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
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


def _get_state_store():
    from src.control_plane.state_store import get_state_store

    return get_state_store()

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
        store = _get_state_store()
        run = store.get_latest_run()
        if run is None:
            return {"status": "idle"}

        snapshot = store.get_snapshot(run.run_id)
        return {
            "status": run.status,
            "run_id": run.run_id,
            "mode": run.mode,
            "current_round": run.current_round,
            "current_stage": run.current_stage,
            "awaiting_human_approval": snapshot.awaiting_human_approval if snapshot else False,
            "approved_notes_count": snapshot.approved_notes_count if snapshot else 0,
            "backtest_reports_count": snapshot.backtest_reports_count if snapshot else 0,
            "verdicts_count": snapshot.verdicts_count if snapshot else 0,
            "llm_calls": snapshot.llm_calls if snapshot else 0,
            "llm_prompt_tokens": snapshot.llm_prompt_tokens if snapshot else 0,
            "llm_completion_tokens": snapshot.llm_completion_tokens if snapshot else 0,
            "llm_total_tokens": snapshot.llm_total_tokens if snapshot else 0,
            "llm_estimated_cost_usd": snapshot.llm_estimated_cost_usd if snapshot else 0.0,
            "last_error": run.last_error,
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
    """获取 CIO 报告列表（从 control-plane state_store 读取）。"""
    try:
        reports = _get_state_store().list_reports(limit=20)
        return [
            {
                "id": report.ref_id,
                "run_id": report.run_id,
                "title": f"CIO Report {report.ref_id}",
                "path": report.path,
                "created_at": report.created_at.isoformat(),
            }
            for report in reports
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# POST /api/approve
# ─────────────────────────────────────────────
class ApproveRequest(BaseModel):
    action: str  # "approve" | "redirect:xxx" | "stop"


@api.post("/api/approve")
def post_approve(body: ApproveRequest):
    """向 control plane 写入 human_decision（审批/重定向/停止）。"""
    valid_actions = {"approve", "stop"}
    action = body.action
    is_valid = action in valid_actions or action.startswith("redirect:")
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"无效的 action: {action}")

    try:
        store = _get_state_store()
        run = store.get_latest_run()
        if run is None:
            raise HTTPException(status_code=404, detail="找不到正在运行的实验")

        snapshot = store.get_snapshot(run.run_id)
        if snapshot is None or not snapshot.awaiting_human_approval:
            raise HTTPException(status_code=409, detail="当前没有等待审批的实验")

        from src.schemas.control_plane import HumanDecisionRecord

        store.append_human_decision(HumanDecisionRecord(run_id=run.run_id, action=action))
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
