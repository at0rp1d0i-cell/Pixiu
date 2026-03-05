"""
EvoQuant: SkillLoader — 统一管理 Skill 文档的加载与条件注入
"""
import logging
import os
from typing import Optional

from src.agents.state import AgentState

logger = logging.getLogger(__name__)

_SKILLS_BASE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "knowledge", "skills")
)


class SkillLoader:
    """按 Agent 角色和 AgentState 动态加载 Skill 文档。

    三类 Skill：
      Type A (Rules)  — 永久注入，硬约束
      Type B (Process)— 永久注入，流程规范
      Type C (Context)— 按 AgentState 条件注入
    """

    def load_for_researcher(self, state: AgentState) -> str:
        """为 Researcher Agent 加载完整的 Skill 上下文。"""
        parts = []

        # ── Type A: 永久注入（硬约束）─────────────────────────
        parts.append(self._load("constraints/a_share_constraints.md", required=True))
        parts.append(self._load("constraints/qlib_formula_syntax.md", required=True))

        # ── Type B: 永久注入（流程规范）───────────────────────
        parts.append(self._load("researcher/alpha_generation.md", required=True))

        # ── Type C: 条件注入（上下文感知）─────────────────────
        # 非第一轮：注入 Island 进化规范
        if state.get("current_iteration", 0) > 0:
            parts.append(self._load("researcher/island_evolution.md"))

        # 有失败记录：注入失败解读规范
        if state.get("error_message"):
            parts.append(self._load("researcher/feedback_interpretation.md"))

        # 过滤掉加载失败的（None）
        valid_parts = [p for p in parts if p]

        logger.debug("[SkillLoader] Researcher 加载了 %d 个 Skill 文档", len(valid_parts))
        return "\n\n---\n\n".join(valid_parts)

    def load_for_coder(self) -> str:
        """为 Coder Agent 加载 Skill 上下文（无状态依赖）。"""
        parts = [
            self._load("constraints/qlib_formula_syntax.md", required=True),
            self._load("coder/qlib_debugging.md", required=True),
        ]
        return "\n\n---\n\n".join(p for p in parts if p)

    def load_for_critic(self) -> str:
        """为 Critic Agent 加载 Skill 上下文。"""
        parts = [
            self._load("constraints/a_share_constraints.md", required=True),
        ]
        return "\n\n---\n\n".join(p for p in parts if p)

    # ─────────────────────────────────────────────
    def _load(self, relative_path: str, required: bool = False) -> Optional[str]:
        """加载单个 Skill 文档。

        Args:
            relative_path: 相对于 knowledge/skills/ 的路径
            required: True 时加载失败会打印 warning；False 时静默失败

        Returns:
            文件内容字符串，或 None（加载失败时）
        """
        full_path = os.path.join(_SKILLS_BASE, relative_path)
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            if required:
                logger.warning("[SkillLoader] 必要的 Skill 文档缺失：%s", full_path)
            return None
        except Exception as e:
            logger.error("[SkillLoader] 加载 Skill 文档失败 %s: %s", full_path, e)
            return None
