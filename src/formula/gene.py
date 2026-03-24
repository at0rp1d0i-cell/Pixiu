from __future__ import annotations

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
    if is_family:
        return _validate_gene_mapping(recipe_or_gene, required_fields=_FAMILY_GENE_FIELDS, gene_type="family_gene")
    return _validate_gene_mapping(recipe_or_gene, required_fields=_VARIANT_GENE_FIELDS, gene_type="variant_gene")


def _canonical_gene_key(gene: Mapping[str, Any], *, field_order: tuple[str, ...]) -> str:
    return "|".join(_to_key_component(gene[field]) for field in field_order)


def _validate_gene_mapping(
    gene: Mapping[str, Any], *, required_fields: tuple[str, ...], gene_type: str
) -> dict[str, Any]:
    keys = set(gene.keys())
    required = set(required_fields)
    if keys != required:
        missing = sorted(required - keys)
        unexpected = sorted(keys - required)
        raise ValueError(
            f"Invalid {gene_type} mapping shape: missing={missing}, unexpected={unexpected}; "
            f"expected keys={list(required_fields)}"
        )
    return {field: gene[field] for field in required_fields}


def _to_key_component(value: Any) -> str:
    if value is None:
        return "null"
    return str(value)
