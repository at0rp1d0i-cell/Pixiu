"""Pixiu SkillLoader: 统一管理多 Agent 的 Skill 文档加载与条件注入。"""
import logging
import os
from collections.abc import Mapping
from typing import Any, Optional

logger = logging.getLogger(__name__)

_SKILLS_BASE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "knowledge", "skills")
)

_DEFAULT_CONSTRAINTS = [
    "constraints/a_share_constraints.md",
    "constraints/qlib_formula_syntax.md",
]

_SUBSPACE_FILE_MAP = {
    "FACTOR_ALGEBRA": "researcher/subspaces/factor_algebra.md",
    "SYMBOLIC_MUTATION": "researcher/subspaces/symbolic_mutation.md",
    "CROSS_MARKET": "researcher/subspaces/cross_market.md",
    "NARRATIVE_MINING": "researcher/subspaces/narrative_mining.md",
    # Also support lowercase enum .value (e.g. "cross_market")
    "factor_algebra": "researcher/subspaces/factor_algebra.md",
    "symbolic_mutation": "researcher/subspaces/symbolic_mutation.md",
    "cross_market": "researcher/subspaces/cross_market.md",
    "narrative_mining": "researcher/subspaces/narrative_mining.md",
}

ISLAND_FILE_MAP = {
    "momentum": "researcher/islands/momentum.md",
    "valuation": "researcher/islands/valuation.md",
    "volatility": "researcher/islands/volatility.md",
    "northbound": "researcher/islands/northbound.md",
    "volume": "researcher/islands/volume.md",
    "sentiment": "researcher/islands/sentiment.md",
}

_ROLE_CONSTRAINTS = {
    "researcher": _DEFAULT_CONSTRAINTS,
    "market_analyst": _DEFAULT_CONSTRAINTS,
    "prefilter": _DEFAULT_CONSTRAINTS,
    "exploration": _DEFAULT_CONSTRAINTS,
    "coder": ["constraints/qlib_formula_syntax.md"],
    "critic": ["constraints/a_share_constraints.md"],
}

_ROLE_SKILLS = {
    "researcher": ["researcher/alpha_generation.md"],
    "market_analyst": ["market_analyst/context_framing.md"],
    "prefilter": ["prefilter/filter_guidance.md"],
    "exploration": ["exploration/a_share_coding_constraints.md"],
    "coder": ["coder/qlib_debugging.md"],
    "critic": [],
}


def _state_value(state: Any, key: str, default: Any = None) -> Any:
    if state is None:
        return default
    if isinstance(state, Mapping):
        return state.get(key, default)
    return getattr(state, key, default)


def _normalize_enum_like(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


class SkillLoader:
    """按 Agent 角色和状态动态加载 Skill 文档。"""

    def load_for_agent(
        self,
        role: str,
        state: Any = None,
        **kwargs,
    ) -> str:
        parts: list[str] = []

        for path in _ROLE_CONSTRAINTS.get(role, _DEFAULT_CONSTRAINTS):
            content = self._load(path, required=True)
            if content:
                parts.append(content)

        for path in _ROLE_SKILLS.get(role, []):
            content = self._load(path, required=True)
            if content:
                parts.append(content)

        parts.extend(self._apply_conditional_rules(role, state, **kwargs))

        valid_parts = [part for part in parts if part]
        logger.debug(
            "[SkillLoader] role=%s loaded %d skill docs",
            role,
            len(valid_parts),
        )
        return "\n\n---\n\n".join(valid_parts)

    def load_for_researcher(
        self,
        state: Any,
        subspace: Any = None,
        island: Optional[str] = None,
    ) -> str:
        """兼容旧接口。"""
        return self.load_for_agent(
            "researcher",
            state,
            subspace=subspace,
            island=island,
        )

    def load_for_coder(self) -> str:
        return self.load_for_agent("coder")

    def load_for_critic(self) -> str:
        return self.load_for_agent("critic")

    def _apply_conditional_rules(
        self,
        role: str,
        state: Any,
        **kwargs,
    ) -> list[str]:
        if role != "researcher":
            return []

        parts: list[str] = []

        if _state_value(state, "current_iteration", 0) > 0:
            content = self._load("researcher/island_evolution.md")
            if content:
                parts.append(content)

        if _state_value(state, "error_message"):
            content = self._load("researcher/feedback_interpretation.md")
            if content:
                parts.append(content)

        if _state_value(state, "market_regime") or _state_value(state, "market_context"):
            content = self._load("researcher/market_regime_detection.md")
            if content:
                parts.append(content)

        subspace = kwargs.get("subspace")
        if subspace is not None:
            skill_path = _SUBSPACE_FILE_MAP.get(_normalize_enum_like(subspace))
            if skill_path:
                content = self._load(skill_path)
                if content:
                    parts.append(content)

        island = kwargs.get("island")
        if island is not None:
            skill_path = ISLAND_FILE_MAP.get(str(island))
            if skill_path:
                content = self._load(skill_path)
                if content:
                    parts.append(content)

        return parts

    def _load(self, relative_path: str, required: bool = False) -> Optional[str]:
        """加载单个 Skill 文档。"""
        full_path = os.path.join(_SKILLS_BASE, relative_path)
        try:
            with open(full_path, "r", encoding="utf-8") as handle:
                return handle.read()
        except FileNotFoundError:
            if required:
                logger.warning("[SkillLoader] 必要的 Skill 文档缺失：%s", full_path)
            return None
        except Exception as exc:
            logger.error("[SkillLoader] 加载 Skill 文档失败 %s: %s", full_path, exc)
            return None
