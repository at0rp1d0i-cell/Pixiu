from __future__ import annotations

import pytest

from src.formula.sketch import (
    FormulaRecipe,
    render_formula_recipe,
    validate_formula_recipe_alignment,
)

pytestmark = pytest.mark.unit


def test_render_mean_spread_with_rank_normalization() -> None:
    recipe = FormulaRecipe(
        base_field="$close",
        lookback_short=10,
        lookback_long=20,
        transform_family="mean_spread",
        normalization="rank",
        normalization_window=20,
    )

    assert render_formula_recipe(recipe) == "Rank(Mean($close, 10) - Mean($close, 20), 20)"


def test_render_volatility_state_without_normalization() -> None:
    recipe = FormulaRecipe(
        base_field="$vwap",
        lookback_short=5,
        lookback_long=20,
        transform_family="volatility_state",
        normalization="none",
    )

    assert render_formula_recipe(recipe) == "Std($vwap, 5) - Std($vwap, 20)"


def test_render_volume_confirmation_with_quantile_normalization() -> None:
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

    assert render_formula_recipe(recipe) == (
        "Quantile(Mul(Mean($close, 5) - Mean($close, 20), Mean($volume, 5) - Mean($volume, 20)), 20, 0.8)"
    )


def test_reject_unsupported_transform_family() -> None:
    with pytest.raises(ValueError, match="Unsupported transform_family"):
        FormulaRecipe(
            base_field="$close",
            lookback_short=5,
            lookback_long=20,
            transform_family="cross_sectional_magic",
        )


def test_reject_unsupported_normalization() -> None:
    with pytest.raises(ValueError, match="Unsupported normalization"):
        FormulaRecipe(
            base_field="$close",
            lookback_short=5,
            lookback_long=20,
            transform_family="mean_spread",
            normalization="zscore",
        )


def test_reject_invalid_window_ordering() -> None:
    with pytest.raises(ValueError, match="lookback_short must be smaller than lookback_long"):
        FormulaRecipe(
            base_field="$close",
            lookback_short=20,
            lookback_long=20,
            transform_family="mean_spread",
        )


def test_reject_free_form_div_interaction_mode() -> None:
    with pytest.raises(ValueError, match="Free-form Div"):
        FormulaRecipe(
            base_field="$close",
            lookback_short=5,
            lookback_long=20,
            transform_family="mean_spread",
            interaction_mode="div",
        )


def test_validate_formula_recipe_alignment_rejects_return_delta_for_mean_spread() -> None:
    recipe = FormulaRecipe(
        base_field="$close",
        lookback_short=5,
        lookback_long=20,
        transform_family="mean_spread",
    )

    reason = validate_formula_recipe_alignment(
        recipe,
        hypothesis="捕捉短期与长期收益率的差值，刻画价格动量加速度",
        economic_intuition="收益率差值越大越强",
    )

    assert reason == "mean_spread cannot claim return delta or acceleration"


def test_validate_formula_recipe_alignment_rejects_missing_volume_mechanism_for_volume_confirmation() -> None:
    recipe = FormulaRecipe(
        base_field="$close",
        secondary_field="$volume",
        lookback_short=5,
        lookback_long=20,
        transform_family="volume_confirmation",
        interaction_mode="mul",
    )

    reason = validate_formula_recipe_alignment(
        recipe,
        hypothesis="捕捉价格趋势延续",
        economic_intuition="趋势越强后续越容易延续",
    )

    assert reason == "volume_confirmation must explicitly mention a volume/liquidity confirmation mechanism"


def test_validate_formula_recipe_alignment_rejects_momentum_wording_for_volume_confirmation() -> None:
    recipe = FormulaRecipe(
        base_field="$close",
        secondary_field="$volume",
        lookback_short=5,
        lookback_long=20,
        transform_family="volume_confirmation",
        interaction_mode="mul",
    )

    reason = validate_formula_recipe_alignment(
        recipe,
        hypothesis="捕捉量价动量确认和趋势延续",
        economic_intuition="成交量放大时价格趋势更容易延续",
    )

    assert reason == "volume_confirmation cannot claim momentum, trend continuation, or return-delta effects"
