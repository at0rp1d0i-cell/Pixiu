# Qlib 因子表达式语法规范

> **Type A — 强制规则。所有 Qlib 表达式必须符合以下语法，否则 Validator 会拦截。**

---

<available-fields>
## 合法字段（数据源）

当前可用字段**以运行时注入的可用字段列表为准**，不要假设某个字段一定存在。

常见稳定基础字段：

```text
$open    $high    $low    $close    $volume    $vwap    $amount    $factor
```

基本面扩展字段（运行时可能可用）：

```text
# 盈利能力
$roe  $roe_waa  $roe_dt  $roa  $eps  $dt_eps  $netprofit_margin  $gross_margin
# 偿债与效率
$current_ratio  $quick_ratio  $debt_to_assets  $assets_turn
# 估值与市场
$pe_ttm  $pb  $turnover_rate  $float_mv
```

- 前缀 `$` 是必须的
- 字段名区分大小写，全部小写
- 如果当前运行时没有显式列出某个可选字段，就不要在公式里使用它
- 基本面字段为日频（每日更新），可以直接和行情字段组合使用
</available-fields>

---

<approved-operators>
## 合法算子（运行时真相优先）

算子以运行时 allowlist 为准。不要因为某个 skill 或历史文档提到了某个算子，就默认它当前可用。

以下是当前常见稳定算子类别与示例，而不是永远不变的硬编码总表。

### 时序算子（需要 lookback 参数 N）
| 算子 | 含义 | 示例 |
|---|---|---|
| `Ref(expr, N)` | N 日前的值 | `Ref($close, 5)` |
| `Mean(expr, N)` | N 日均值 | `Mean($volume, 20)` |
| `Std(expr, N)` | N 日标准差 | `Std($close/Ref($close,1)-1, 20)` |
| `Sum(expr, N)` | N 日求和 | `Sum($volume, 5)` |
| `Max(expr, N)` | N 日最大值 | `Max($high, 20)` |
| `Min(expr, N)` | N 日最小值 | `Min($low, 20)` |
| `Slope(expr, N)` | N 日线性回归斜率 | `Slope($close, 20)` |
| `Rsquare(expr, N)` | N 日线性回归 R² | `Rsquare($close, 20)` |
| `Resi(expr, N)` | N 日线性回归残差 | `Resi($close, 20)` |
| `WMA(expr, N)` | N 日加权移动均值 | `WMA($close, 10)` |
| `EMA(expr, N)` | N 日指数移动均值 | `EMA($close, 12)` |
| `Corr(expr1, expr2, N)` | N 日相关系数 | `Corr($close/Ref($close,1), $volume/Ref($volume,1), 20)` |
| `Cov(expr1, expr2, N)` | N 日协方差 | `Cov($close, $volume, 10)` |
| `Rank(expr, N)` | N 日时序排名（归一化到 [0,1]） | `Rank($close/Ref($close,1)-1, 20)` |
| `Kurt(expr, N)` | N 日峰度（尾部风险） | `Kurt($close/Ref($close,1)-1, 20)` |
| `Skew(expr, N)` | N 日偏度（收益分布不对称性） | `Skew($close/Ref($close,1)-1, 20)` |
| `Med(expr, N)` | N 日中位数（比 Mean 更鲁棒） | `Med($volume, 20)` |
| `Quantile(expr, N, q)` | N 日分位数（q 为 0~1） | `Quantile($close/Ref($close,1)-1, 20, 0.9)` |

### 截面算子
**当前没有可用的截面算子**。`Rank` 是时序算子，不是截面算子。不要使用 `CSRank`、`CSMean`、`CSZScore` 等截面算子。

### 数学算子
| 算子 | 含义 |
|---|---|
| `Abs(expr)` | 绝对值 |
| `Sign(expr)` | 符号（-1/0/1） |
| `Log(expr)` | 自然对数（expr 必须 > 0；要求公式本身可证明正值域，不是固定写法） |
| `Power(expr, n)` | 幂次 |
| `Div(expr1, expr2)` | 除法（分母必须可证明非零，存在零风险会被拒绝） |
| `If(cond, t, f)` | 条件表达式 |
</approved-operators>

---

<forbidden-patterns>
## 常见语法错误（Validator 会拦截）

```python
# ❌ 负数时间偏移（未来数据）
Ref($close, -1)

# ❌ 字段名无 $ 前缀
Mean(close, 5)

# ❌ 括号不匹配
Corr($close, $volume, 20

# ❌ 不存在的算子
MovingAverage($close, 5)   # 应该用 Mean
Ts_Corr($close, $volume, 20)   # Ts_* 系列算子在当前 qlib 版本未注册，全部禁止
Ts_Mean($close, 20)            # 同上，用 Mean 代替

# ❌ Rank 缺少窗口参数
Rank($close)   # 错误！Rank 是时序算子，需要 N：Rank($close, 20)

# ❌ 裸数学常数 e（Validator 拦截：未知标识符）
e * $close     # 错误！e 不是合法标识符
Exp($close)    # 错误！Exp 算子未注册
# 正确：直接用数字 2.71828，或用 Log/Power 等已有算子组合

# ❌ 对数的参数可能为负
Log($close - Ref($close, 1))   # 日收益率可能为负
# 应改为：Log($close / Ref($close, 1)) 或 Log(Abs(expr) + 1e-8)
```

### 除法/对数定义域风险（fail-closed）

Validator 会通过 AST 静态分析拒绝“可能除零”或“Log 参数可能非正”的表达式。
重点是“可证明安全”，而不是某个固定包装模板。

```python
# ❌ 分母可能为零（会被拒绝）
Div($close - Ref($close, 5), Std($close, 5))

# ✅ 通过下界平移确保分母非零（可接受）
Div($close - Ref($close, 5), Std($close, 5) + 1e-8)

# ✅ 分母来自可证明正值域（可接受）
Div($close, Ref($close, 5))

# ❌ Log 参数可能为零或负（会被拒绝）
Log($volume / Mean($volume, 20))

# ✅ 让 Log 参数具备正值域证明（可接受）
Log($close / Ref($close, 1))

# ✅ Max 保护也是可接受方案之一（不是唯一方案）
Log(Max($volume / Mean($volume, 20), 1e-8))
```
</forbidden-patterns>

---

<ref-sign-rule>
## ⚠️ Ref 符号规则（极高频错误，LLM 必看）

```
Ref($close, 1)   = 昨天的收盘价  ✅ 正确
Ref($close, 5)   = 5日前的收盘价 ✅ 正确
Ref($close, -1)  = 明天的收盘价  ❌ 未来数据！Validator 必拦截
Ref($close, 0)   = 今天的收盘价  ⚠️ 等同于 $close，无意义
```

**记忆口诀**：正数 = 过去，负数 = 未来。只用正数。
</ref-sign-rule>

---

<formula-templates>
## 推荐的常用模板

```python
# 日收益率（最基础的动量信号）
$close / Ref($close, 1) - 1

# N 日收益率
$close / Ref($close, N) - 1

# 量价相关性（捕捉放量上涨 vs 缩量上涨）
Corr($close / Ref($close, 1), $volume / Ref($volume, 1), 20)

# 相对成交量（当日成交量 vs 近期均量）
$volume / Mean($volume, 20)

# 波动率
Std($close / Ref($close, 1) - 1, 20)
```
</formula-templates>

---

<verified-factors>
## 经过 A 股回测验证的有效因子模板

以下公式已在 CSI300 数据集验证，IC 统计显著，可直接用于 proposed_formula 或作为变体出发点：

```python
# 1. Amihud 非流动性因子（市场冲击代理）
# IC ≈ 0.03~0.05，适合价值+低流动性方向
Mean(Abs($close/Ref($close,1)-1) / ($volume * $close), 20)

# 2. 量价背离因子（资金撤退信号）
# 负相关 = 放量下跌 or 缩量上涨，均为弱势
Corr(Rank($volume, 20), Rank($close, 20), 20)

# 3. 波动率期限结构斜率（短期 vs 长期波动）
# 短波 > 长波 = 近期异动，反转或趋势加速
Std($close/Ref($close,1)-1, 5) / (Std($close/Ref($close,1)-1, 20) + 1e-8)

# 4. 换手调整动量（高换手削弱动量）
# 过度交易稀释了真实趋势信号
($close/Ref($close,20)-1) / (Mean($volume/Mean($volume,60),20) + 1e-8)

# 5. RSI 近似（无未来数据版本）
# 上涨幅度均值 / 总波动均值，值域 [0,1]
Mean(If(Gt($close,Ref($close,1)),$close/Ref($close,1)-1,0),14) / (Mean(Abs($close/Ref($close,1)-1),14) + 1e-8)
```

**使用注意**：
- Div/Mod/Log/Sqrt 采用 fail-closed：表达式必须在公式层面可证明安全；不可证明时会被 Stage 3 拒绝，不会自动改写。
- 以上模板为出发点，结合当前 Island 上下文和市场状态做变体，不要直接照搬
</verified-factors>

---

*最后更新：2026-03-22*
