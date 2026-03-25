from __future__ import annotations

from dataclasses import dataclass

from src.formula.family_semantics import get_factor_algebra_family_semantics

_VOLUME_PROXY_FIELDS = {"$volume", "$amount"}
_RETURN_TOKENS = ("收益率", "回报率", "return", "ret", "涨跌幅", "相对收益")
_ACCELERATION_TOKENS = ("加速度", "acceleration")
_NORMALIZATION_TOKENS = ("标准化", "归一化", "normalize", "normalized")
_VOLUME_TOKENS = ("成交量", "量能", "放量", "缩量", "volume", "amount", "金额")
_RELATIVE_VOLUME_TOKENS = ("相对变化", "相对成交量", "量能比", "volume ratio", "relative volume")
_MEAN_SPREAD_TOKENS = ("均线差", "均值差", "价差", "均价差", "差值", "spread")
_MOMENTUM_TOKENS = ("动量", "momentum", "趋势", "trend")
_RATIO_COMPARATIVE_TOKENS = ("相对强弱", "比值", "relative strength", "短强长弱", "long-short", "短期强于长期")
_PRICE_PROXY_FIELDS = {"$close", "$open", "$high", "$low", "$vwap"}

ALLOWED_BASE_FIELDS = (
    "$close",
    "$open",
    "$high",
    "$low",
    "$vwap",
    "$volume",
    "$amount",
)
ALLOWED_WINDOW_BUCKETS = (5, 10, 20, 30, 60)
ALLOWED_TRANSFORM_FAMILIES = (
    "mean_spread",
    "ratio_momentum",
    "volatility_state",
    "volume_confirmation",
)
ALLOWED_INTERACTION_MODES = ("none", "mul", "sub")
ALLOWED_NORMALIZATIONS = ("none", "rank", "quantile")
ALLOWED_QUANTILE_QSCORES = (0.2, 0.5, 0.8)


@dataclass(frozen=True)
class FormulaRecipe:
    base_field: str
    lookback_short: int
    lookback_long: int
    transform_family: str
    interaction_mode: str = "none"
    normalization: str = "none"
    normalization_window: int | None = None
    quantile_qscore: float | None = None
    secondary_field: str | None = None

    def __post_init__(self) -> None:
        if self.base_field not in ALLOWED_BASE_FIELDS:
            raise ValueError(f"Unsupported base_field: {self.base_field}")
        if self.secondary_field is not None and self.secondary_field not in ALLOWED_BASE_FIELDS:
            raise ValueError(f"Unsupported secondary_field: {self.secondary_field}")
        if self.transform_family not in ALLOWED_TRANSFORM_FAMILIES:
            raise ValueError(f"Unsupported transform_family: {self.transform_family}")
        if self.interaction_mode == "div":
            raise ValueError("Free-form Div is not allowed in FormulaSketch Lite v1")
        if self.interaction_mode not in ALLOWED_INTERACTION_MODES:
            raise ValueError(f"Unsupported interaction_mode: {self.interaction_mode}")
        if self.normalization not in ALLOWED_NORMALIZATIONS:
            raise ValueError(f"Unsupported normalization: {self.normalization}")
        if self.lookback_short not in ALLOWED_WINDOW_BUCKETS:
            raise ValueError(f"Unsupported lookback_short: {self.lookback_short}")
        if self.lookback_long not in ALLOWED_WINDOW_BUCKETS:
            raise ValueError(f"Unsupported lookback_long: {self.lookback_long}")
        if self.lookback_short >= self.lookback_long:
            raise ValueError("lookback_short must be smaller than lookback_long")
        if self.transform_family == "volume_confirmation" and self.secondary_field is None:
            raise ValueError("volume_confirmation requires secondary_field")
        if self.transform_family == "volume_confirmation" and self.interaction_mode != "mul":
            raise ValueError("volume_confirmation requires interaction_mode='mul'")
        if self.transform_family != "volume_confirmation" and self.secondary_field is not None:
            raise ValueError("secondary_field is only supported for volume_confirmation")
        if self.normalization == "none":
            if self.normalization_window is not None or self.quantile_qscore is not None:
                raise ValueError("normalization_window/quantile_qscore are not allowed when normalization='none'")
            return
        if self.normalization_window is None:
            raise ValueError("normalization_window is required for normalized formulas")
        if self.normalization_window not in ALLOWED_WINDOW_BUCKETS:
            raise ValueError(f"Unsupported normalization_window: {self.normalization_window}")
        if self.normalization == "rank":
            if self.quantile_qscore is not None:
                raise ValueError("quantile_qscore is only supported for normalization='quantile'")
            return
        if self.quantile_qscore is None:
            raise ValueError("quantile_qscore is required for normalization='quantile'")
        if self.quantile_qscore not in ALLOWED_QUANTILE_QSCORES:
            raise ValueError(f"Unsupported quantile_qscore: {self.quantile_qscore}")


def render_formula_recipe(recipe: FormulaRecipe) -> str:
    expr = _render_core(recipe)
    return _apply_normalization(expr, recipe)


def _render_core(recipe: FormulaRecipe) -> str:
    short = recipe.lookback_short
    long = recipe.lookback_long
    base = recipe.base_field
    if recipe.transform_family == "mean_spread":
        return f"Mean({base}, {short}) - Mean({base}, {long})"
    if recipe.transform_family == "ratio_momentum":
        return f"Mean({base}, {short}) / Mean({base}, {long}) - 1"
    if recipe.transform_family == "volatility_state":
        return f"Std({base}, {short}) - Std({base}, {long})"
    volume = recipe.secondary_field
    return (
        f"Mul(Mean({base}, {short}) - Mean({base}, {long}), "
        f"Mean({volume}, {short}) - Mean({volume}, {long}))"
    )


def _apply_normalization(expr: str, recipe: FormulaRecipe) -> str:
    if recipe.normalization == "none":
        return expr
    if recipe.normalization == "rank":
        return f"Rank({expr}, {recipe.normalization_window})"
    return f"Quantile({expr}, {recipe.normalization_window}, {recipe.quantile_qscore})"


def validate_formula_recipe_alignment(
    recipe: FormulaRecipe,
    *,
    hypothesis: str,
    economic_intuition: str,
    island: str | None = None,
) -> str | None:
    text = f"{hypothesis} {economic_intuition}".strip().lower()
    if not text:
        return None

    uses_volume_proxy = recipe.base_field in _VOLUME_PROXY_FIELDS or recipe.secondary_field in _VOLUME_PROXY_FIELDS

    if any(token in text for token in _NORMALIZATION_TOKENS) and recipe.normalization == "none":
        return "hypothesis mentions normalization but recipe.normalization='none'"

    if any(token in text for token in _VOLUME_TOKENS) and not uses_volume_proxy:
        return "hypothesis mentions volume/liquidity but recipe has no volume proxy"

    if recipe.transform_family == "mean_spread":
        if any(token in text for token in _RETURN_TOKENS + _ACCELERATION_TOKENS):
            return "mean_spread cannot claim return delta or acceleration"
    elif recipe.transform_family == "ratio_momentum":
        if any(token in text for token in _MEAN_SPREAD_TOKENS):
            return "ratio_momentum should not be described as a mean spread"
        if (
            island == "momentum"
            and recipe.base_field in _PRICE_PROXY_FIELDS
            and any(token in text for token in _MOMENTUM_TOKENS)
            and not any(token in text for token in _RATIO_COMPARATIVE_TOKENS)
        ):
            return (
                "ratio_momentum on momentum island must describe a comparative relative-strength mechanism, "
                "not generic momentum/trend continuation"
            )
    elif recipe.transform_family == "volatility_state":
        if any(token in text for token in _RETURN_TOKENS + _ACCELERATION_TOKENS + _MOMENTUM_TOKENS):
            return "volatility_state cannot claim momentum or return-delta effects"
    elif recipe.transform_family == "volume_confirmation":
        if not any(token in text for token in _VOLUME_TOKENS):
            return "volume_confirmation must explicitly mention a volume/liquidity confirmation mechanism"
        if any(token in text for token in _RELATIVE_VOLUME_TOKENS):
            return "volume_confirmation cannot claim relative volume change"
        if any(token in text for token in _MOMENTUM_TOKENS + _RETURN_TOKENS + _ACCELERATION_TOKENS):
            return "volume_confirmation cannot claim momentum, trend continuation, or return-delta effects"

    return None


def describe_factor_algebra_family_semantics(transform_family: str) -> str:
    semantics = get_factor_algebra_family_semantics(transform_family)
    if semantics is None:
        return ""
    return f"{semantics['allowed']} {semantics['forbidden']}"
