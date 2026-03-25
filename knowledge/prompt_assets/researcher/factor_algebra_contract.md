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

## value-density steering（当前最小约束）
- 在 `momentum` island 下，如果 `transform_family=ratio_momentum` 且只使用单一价格代理（如 `$close/$vwap`），不要写成泛化动量、趋势延续或“价格继续上涨/下跌”。
- 这类 recipe 必须明确说明相对强弱、短强长弱、长短窗口比值比较，或其他可检验的 comparative mechanism。
- `transform_family=volume_confirmation` 时，不要只写“量价确认”或“趋势延续得到量能确认”。
- 这类 recipe 必须明确写成：`价格均值差/价差` 由 `成交量/金额/流动性差值` 确认。
- `volume_confirmation` 的 `base_field` 必须是价格代理（`$close/$open/$high/$low/$vwap`），`secondary_field` 必须是量能代理（`$volume/$amount`）。
- 可直接使用接近如下的 hypothesis/economic_intuition：`短期价格均值差在成交量差值配合下更可靠`、`价格价差由流动性差值确认后更容易兑现`。
