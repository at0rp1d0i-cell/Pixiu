## FACTOR_ALGEBRA 专用输出约束（必须遵守）
- 本子空间必须输出 `formula_recipe` 对象，由系统渲染 `proposed_formula`
- 不接受只提供自由字符串 `proposed_formula` 的路径
- `formula_recipe` 字段：
  - `base_field`
  - `lookback_short`
  - `lookback_long`
  - `transform_family`: `mean_spread | ratio_momentum | volatility_state | volume_confirmation`
  - `interaction_mode`: `none | mul | sub`
  - `normalization`: `none | rank | quantile`
  - `normalization_window`（`normalization != none` 时必填）
  - `quantile_qscore`（`normalization = quantile` 时必填）
  - `secondary_field`（仅 `volume_confirmation` 时必填）
- `base_field/secondary_field` 仅允许：`$close, $open, $high, $low, $vwap, $volume, $amount`
- 窗口字段 `lookback_short/lookback_long/normalization_window` 仅允许：`5, 10, 20, 30, 60`
- `quantile_qscore` 仅允许：`0.2, 0.5, 0.8`
- 必须满足 `lookback_short < lookback_long`
- `proposed_formula` 会被系统覆盖渲染，填写占位字符串即可
- 如果 hypothesis 想引用 `ROE / PB / float_mv / turnover_rate` 等字段，请在本子空间改用价量代理；不要把这些字段写进 `formula_recipe`

{factor_algebra_family_semantics_block}
