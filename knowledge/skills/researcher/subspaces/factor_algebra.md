# 因子代数搜索 — FormulaSketch Lite v1

> **Type C — 子空间注入：当 subspace == FACTOR_ALGEBRA 时注入。**
> 本子空间采用 FormulaSketch Lite v1：先输出 `formula_recipe`，再由系统渲染 `proposed_formula`。

---

## 核心定位

因子代数搜索是**有约束的 recipe 组合搜索**，不是自由公式写作。
每个假设必须锚定可解释机制，`formula_recipe` 是唯一主路径。

---

## 结构化生成步骤（必须按顺序）

**Step 1 — 选择机制与字段**
- 选一个机制（均值差、比值动量、波动状态、量价确认）
- 选择 `base_field`；仅 `volume_confirmation` 需要 `secondary_field`

**Step 2 — 填写 formula_recipe**
- 必填字段：
  - `base_field`
  - `lookback_short`
  - `lookback_long`
  - `transform_family`（`mean_spread | ratio_momentum | volatility_state | volume_confirmation`）
  - `interaction_mode`（`none | mul | sub`）
  - `normalization`（`none | rank | quantile`）
- 条件字段：
  - `normalization_window`（当 normalization != none）
  - `quantile_qscore`（当 normalization = quantile）
  - `secondary_field`（仅 volume_confirmation）
- 字段白名单（必须命中）：
  - `base_field / secondary_field` ∈ `{$close, $open, $high, $low, $vwap, $volume, $amount}`
- 数值白名单（必须命中）：
  - `lookback_short / lookback_long / normalization_window` ∈ `{5, 10, 20, 30, 60}`
  - `quantile_qscore` ∈ `{0.2, 0.5, 0.8}`

**Step 3 — recipe 合规自检**
- [ ] `lookback_short < lookback_long`
- [ ] `volume_confirmation` 时 `interaction_mode='mul'`
- [ ] `base_field / secondary_field` 仅使用 `$close/$open/$high/$low/$vwap/$volume/$amount`
- [ ] 所有窗口值仅使用 `{5, 10, 20, 30, 60}`
- [ ] `quantile_qscore`（若使用）仅为 `{0.2, 0.5, 0.8}`
- [ ] 归一化仅使用 `Rank(expr, N)` 或 `Quantile(expr, N, qscore)` 对应 recipe 字段
- [ ] 不提交自由 `Div`、不手写任意算子树

如果 hypothesis 想表达 ROE / PB / float_mv / turnover_rate / 北向持仓等机制：
- 在本子空间改用价量代理
- 或把这个想法留给 `cross_market / narrative_mining`
- 不要把这些字段直接写进 `formula_recipe`

**Step 4 — 输出 Note**
- `proposed_formula` 填占位文本即可，系统会按 recipe 覆盖渲染
- hypothesis/economic_intuition/risk/regime 仍需完整输出

---

## 禁止项

- **禁止**：把自由 `proposed_formula` 字符串作为主路径（缺失 `formula_recipe` 会被拒绝）
- **禁止**：`lookback_short >= lookback_long`
- **禁止**：窗口值不在 `{5, 10, 20, 30, 60}` 内
- **禁止**：`base_field/secondary_field` 使用白名单以外字段（例如 `$roe`, `$float_mv`, `$turnover_rate`）
- **禁止**：`quantile_qscore` 不在 `{0.2, 0.5, 0.8}` 内（例如 `0.75`）
- **禁止**：`volume_confirmation` 搭配非 `mul` 交互模式
- **禁止**：使用未在运行时可用列表中的字段
