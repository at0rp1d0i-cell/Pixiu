"""
Pixiu v2: Coder Agent (Deterministic Mode)
Role: Wrapper for the Execution Layer (no internal LLMs).
"""
import logging
from src.schemas.state import AgentState
from src.execution.coder import Coder

async def coder_node(state: AgentState) -> dict:
    """
    对每个 approved_note（status="ready_for_backtest"），
    调用 Coder 执行 Qlib 回测。
    目前简化处理：对全部 ready 的 note 进行并行/串行执行。
    """
    logging.info("[Coder Node] 唤醒确定性隔离 Docker 沙箱进行回测...")
    
    coder_executor = Coder()
    new_reports = []
    
    for note in state.approved_notes:
        if note.status == "ready_for_backtest":
            logging.info(f"正在回测因子: {note.note_id} | 公式: {note.final_formula or note.proposed_formula}")
            report = await coder_executor.run_backtest(note)
            new_reports.append(report)
            note.status = "completed"
            
            if report.passed:
                logging.info(f"✅ 回测通过: Sharpe={report.metrics.sharpe}, IC={report.metrics.ic_mean}")
            else:
                logging.error(f"❌ 回测失败: {report.error_message or '未能达到基线要求'}")
                
    # 集合之前的所有回测报告并返回全新的状态片段
    return {
        "backtest_reports": list(state.backtest_reports) + new_reports,
        "approved_notes": state.approved_notes  # 状态已经被更新为空已完成
    }
