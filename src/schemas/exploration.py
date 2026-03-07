from typing import List, Dict, Any, Optional
from src.schemas import EvoQuantBase
from src.schemas.research_note import ExplorationQuestion

class ExplorationRequest(EvoQuantBase):
    request_id: str             # UUID
    note_id: str                # 对应的 FactorResearchNote
    question: ExplorationQuestion
    data_fields: List[str]      # 实际需要从 Qlib 加载的字段

class ExplorationResult(EvoQuantBase):
    request_id: str
    note_id: str
    success: bool
    script_used: str            # ExplorationAgent 生成的 Python 脚本（审计用）
    findings: str               # 自然语言总结（给 Researcher 读）
    key_statistics: Dict[str, Any]  # 关键统计数值（IC、相关性等）
    refined_formula_suggestion: Optional[str] = None # 基于探索结果建议的公式修正
    error_message: Optional[str] = None
