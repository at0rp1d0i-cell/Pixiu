from __future__ import annotations

import pytest

from src.formula.gene import (
    build_family_gene,
    build_family_gene_key,
    build_variant_gene,
    build_variant_gene_key,
)
from src.formula.sketch import FormulaRecipe

pytestmark = pytest.mark.unit


def test_build_family_gene_extracts_expected_fields() -> None:
    recipe = FormulaRecipe(
        base_field="$close",
        secondary_field="$volume",
        lookback_short=5,
        lookback_long=20,
        transform_family="volume_confirmation",
        interaction_mode="mul",
        normalization="quantile",
        normalization_window=20,
        quantile_qscore=0.8,
    )

    assert build_family_gene(recipe) == {
        "subspace": "factor_algebra",
        "transform_family": "volume_confirmation",
        "base_field": "$close",
        "secondary_field": "$volume",
        "interaction_mode": "mul",
        "normalization_kind": "quantile",
    }


def test_build_variant_gene_extracts_expected_fields() -> None:
    recipe = FormulaRecipe(
        base_field="$vwap",
        lookback_short=10,
        lookback_long=30,
        transform_family="volatility_state",
        normalization="rank",
        normalization_window=20,
    )

    assert build_variant_gene(recipe) == {
        "lookback_short": 10,
        "lookback_long": 30,
        "normalization_window": 20,
        "quantile_qscore": None,
    }


def test_gene_keys_are_stable_across_recipe_and_mapping_input() -> None:
    recipe = FormulaRecipe(
        base_field="$close",
        secondary_field="$volume",
        lookback_short=5,
        lookback_long=20,
        transform_family="volume_confirmation",
        interaction_mode="mul",
        normalization="quantile",
        normalization_window=20,
        quantile_qscore=0.8,
    )
    family_gene = {
        "normalization_kind": "quantile",
        "interaction_mode": "mul",
        "secondary_field": "$volume",
        "transform_family": "volume_confirmation",
        "base_field": "$close",
        "subspace": "factor_algebra",
    }
    variant_gene = {
        "quantile_qscore": 0.8,
        "normalization_window": 20,
        "lookback_long": 20,
        "lookback_short": 5,
    }

    assert build_family_gene_key(recipe) == build_family_gene_key(family_gene)
    assert build_variant_gene_key(recipe) == build_variant_gene_key(variant_gene)


def test_family_gene_unchanged_when_only_windows_or_qscore_change() -> None:
    base_recipe = FormulaRecipe(
        base_field="$close",
        lookback_short=5,
        lookback_long=20,
        transform_family="mean_spread",
        normalization="quantile",
        normalization_window=20,
        quantile_qscore=0.2,
    )
    changed_variant_recipe = FormulaRecipe(
        base_field="$close",
        lookback_short=10,
        lookback_long=30,
        transform_family="mean_spread",
        normalization="quantile",
        normalization_window=30,
        quantile_qscore=0.8,
    )

    assert build_family_gene(base_recipe) == build_family_gene(changed_variant_recipe)
    assert build_family_gene_key(base_recipe) == build_family_gene_key(changed_variant_recipe)
    assert build_variant_gene(base_recipe) != build_variant_gene(changed_variant_recipe)
    assert build_variant_gene_key(base_recipe) != build_variant_gene_key(changed_variant_recipe)


def test_family_gene_changes_when_transform_or_base_field_changes() -> None:
    recipe = FormulaRecipe(
        base_field="$close",
        lookback_short=5,
        lookback_long=20,
        transform_family="mean_spread",
        normalization="none",
    )
    changed_transform = FormulaRecipe(
        base_field="$close",
        lookback_short=5,
        lookback_long=20,
        transform_family="ratio_momentum",
        normalization="none",
    )
    changed_base = FormulaRecipe(
        base_field="$vwap",
        lookback_short=5,
        lookback_long=20,
        transform_family="mean_spread",
        normalization="none",
    )

    assert build_family_gene(recipe) != build_family_gene(changed_transform)
    assert build_family_gene(recipe) != build_family_gene(changed_base)
    assert build_family_gene_key(recipe) != build_family_gene_key(changed_transform)
    assert build_family_gene_key(recipe) != build_family_gene_key(changed_base)
