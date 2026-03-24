from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from src.formula.sketch import FormulaRecipe

_SUBSPACE_FACTOR_ALGEBRA = "factor_algebra"

_FAMILY_GENE_FIELDS = (
    "subspace",
    "transform_family",
    "base_field",
    "secondary_field",
    "interaction_mode",
    "normalization_kind",
)

_VARIANT_GENE_FIELDS = (
    "lookback_short",
    "lookback_long",
    "normalization_window",
    "quantile_qscore",
)


def build_family_gene(recipe: FormulaRecipe) -> dict[str, Any]:
    return {
        "subspace": _SUBSPACE_FACTOR_ALGEBRA,
        "transform_family": recipe.transform_family,
        "base_field": recipe.base_field,
        "secondary_field": recipe.secondary_field,
        "interaction_mode": recipe.interaction_mode,
        "normalization_kind": recipe.normalization,
    }


def build_variant_gene(recipe: FormulaRecipe) -> dict[str, Any]:
    return {
        "lookback_short": recipe.lookback_short,
        "lookback_long": recipe.lookback_long,
        "normalization_window": recipe.normalization_window,
        "quantile_qscore": recipe.quantile_qscore,
    }


def build_family_gene_key(recipe_or_gene: FormulaRecipe | Mapping[str, Any]) -> str:
    gene = _coerce_gene(recipe_or_gene, is_family=True)
    return _canonical_gene_key(gene, field_order=_FAMILY_GENE_FIELDS)


def build_variant_gene_key(recipe_or_gene: FormulaRecipe | Mapping[str, Any]) -> str:
    gene = _coerce_gene(recipe_or_gene, is_family=False)
    return _canonical_gene_key(gene, field_order=_VARIANT_GENE_FIELDS)


def _coerce_gene(recipe_or_gene: FormulaRecipe | Mapping[str, Any], *, is_family: bool) -> dict[str, Any]:
    if isinstance(recipe_or_gene, FormulaRecipe):
        return build_family_gene(recipe_or_gene) if is_family else build_variant_gene(recipe_or_gene)
    if not isinstance(recipe_or_gene, Mapping):
        raise TypeError("recipe_or_gene must be FormulaRecipe or mapping")
    return _canonical_gene_object(recipe_or_gene, is_family=is_family)


def _canonical_gene_object(gene: Mapping[str, Any], *, is_family: bool) -> dict[str, Any]:
    if is_family:
        return {
            "subspace": gene.get("subspace", _SUBSPACE_FACTOR_ALGEBRA),
            "transform_family": gene.get("transform_family"),
            "base_field": gene.get("base_field"),
            "secondary_field": gene.get("secondary_field"),
            "interaction_mode": gene.get("interaction_mode"),
            "normalization_kind": gene.get("normalization_kind"),
        }
    return {
        "lookback_short": gene.get("lookback_short"),
        "lookback_long": gene.get("lookback_long"),
        "normalization_window": gene.get("normalization_window"),
        "quantile_qscore": gene.get("quantile_qscore"),
    }


def _canonical_gene_key(gene: Mapping[str, Any], *, field_order: tuple[str, ...]) -> str:
    # Keep explicit nulls for absent/None values by serializing full ordered objects.
    ordered = {field: gene.get(field) for field in field_order}
    return json.dumps(ordered, ensure_ascii=True, separators=(",", ":"), sort_keys=False)
