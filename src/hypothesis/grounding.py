from __future__ import annotations

import re
from typing import Iterable

from src.schemas import PixiuBase
from src.schemas.exploration import SubspaceRegistry
from src.schemas.hypothesis import ExplorationSubspace


class MechanismProxyClaim(PixiuBase):
    mechanism_source: str
    proxy_fields: list[str]
    proxy_rationale: str
    formula_claim: str


def allowed_mechanism_sources(
    subspace: ExplorationSubspace,
    registry: SubspaceRegistry,
) -> set[str]:
    if subspace == ExplorationSubspace.CROSS_MARKET:
        return {template.name for template in registry.mechanism_templates}
    if subspace == ExplorationSubspace.NARRATIVE_MINING:
        return {category.category for category in registry.narrative_categories}
    return set()


def extract_formula_fields(formula: str) -> set[str]:
    return {f"${field}" for field in re.findall(r"\$(\w+)", formula or "")}


def validate_grounding_claim(
    claim: MechanismProxyClaim,
    *,
    subspace: ExplorationSubspace,
    registry: SubspaceRegistry,
    available_fields: Iterable[str],
    formula: str,
) -> str | None:
    allowed_sources = allowed_mechanism_sources(subspace, registry)
    if claim.mechanism_source not in allowed_sources:
        return f"unsupported mechanism_source: {claim.mechanism_source}"

    if not claim.proxy_fields:
        return "missing proxy_fields"

    allowed_fields = set(available_fields)
    invalid_fields = [field for field in claim.proxy_fields if field not in allowed_fields]
    if invalid_fields:
        return f"unsupported proxy_fields: {', '.join(invalid_fields)}"

    formula_fields = extract_formula_fields(formula)
    if not formula_fields:
        return "formula does not reference any runtime fields"

    if not formula_fields.intersection(claim.proxy_fields):
        return (
            "formula does not use declared proxy_fields: "
            + ", ".join(claim.proxy_fields)
        )

    if not claim.proxy_rationale.strip():
        return "missing proxy_rationale"
    if not claim.formula_claim.strip():
        return "missing formula_claim"

    return None
