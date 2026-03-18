"""
Infrastructure helpers: singleton getters, run record management, snapshots.
Also holds node-name constants (imported by both graph.py and node files).

Note: _ensure_run_record, _update_run_record, _write_snapshot, _persist_cio_report
are defined in src.core.orchestrator (__init__.py) so that test monkeypatching
targets the correct namespace. Node files and graph.py import those via
`import src.core.orchestrator as _orch`.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# 节点名称常量
# ─────────────────────────────────────────────────────────
NODE_MARKET_CONTEXT  = "market_context"
NODE_HYPOTHESIS_GEN  = "hypothesis_gen"
NODE_SYNTHESIS       = "synthesis"
NODE_PREFILTER       = "prefilter"
NODE_EXPLORATION     = "exploration"
NODE_NOTE_REFINEMENT = "note_refinement"
NODE_CODER           = "coder"
NODE_JUDGMENT        = "judgment"
NODE_PORTFOLIO       = "portfolio"
NODE_REPORT          = "report"
NODE_HUMAN_GATE      = "human_gate"
NODE_LOOP_CONTROL    = "loop_control"

# ─────────────────────────────────────────────────────────
# 模块级调度器（跨轮次复用）
# ─────────────────────────────────────────────────────────
_scheduler = None
_current_run_id: Optional[str] = None
