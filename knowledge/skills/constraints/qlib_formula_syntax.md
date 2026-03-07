# Qlib 因子表达式语法规范

> **Type A — 强制规则。所有 Qlib 表达式必须符合以下语法，否则 Validator 会拦截。**

---

## 合法字段（数据源）

```
$open    $high    $low    $close    $volume    $vwap    $factor
```

- 前缀 `$` 是必须的
- 字段名区分大小写，全部小写
- 不存在 `$price`、`$turnover_rate` 等字段（换手率需用 $volume/$float_shares 计算）

---

## 合法算子（完整列表）

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
| `Corr(e1, e2, N)` | N 日相关系数 | `Corr($close/Ref($close,1), $volume/Ref($volume,1), 20)` |
| `Cov(e1, e2, N)` | N 日协方差 | `Cov($close, $volume, 10)` |

### 截面算子（在同一天所有股票间计算）
| 算子 | 含义 |
|---|---|
| `CSRank(expr)` | 截面排名（0~1） |
| `CSZScore(expr)` | 截面 Z-score 标准化 |
| `CSMax(expr)` | 截面最大值 |
| `CSMin(expr)` | 截面最小值 |

### 数学算子
| 算子 | 含义 |
|---|---|
| `Abs(expr)` | 绝对值 |
| `Sign(expr)` | 符号（-1/0/1） |
| `Log(expr)` | 自然对数（expr 必须 > 0） |
| `Power(expr, n)` | 幂次 |
| `If(cond, t, f)` | 条件表达式 |

---

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

# ❌ 对数的参数可能为负
Log($close - Ref($close, 1))   # 日收益率可能为负
# 应改为：Log($close / Ref($close, 1))
```

---

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

# 截面动量排名
CSRank($close / Ref($close, 20) - 1)

# 波动率
Std($close / Ref($close, 1) - 1, 20)
```

---

## ⚠️ Ref 符号规则（极高频错误，LLM 必看）

```
Ref($close, 1)   = 昨天的收盘价  ✅ 正确
Ref($close, 5)   = 5日前的收盘价 ✅ 正确
Ref($close, -1)  = 明天的收盘价  ❌ 未来数据！Validator 必拦截
Ref($close, 0)   = 今天的收盘价  ⚠️ 等同于 $close，无意义
```

**记忆口诀**：正数 = 过去，负数 = 未来。只用正数。

---

## 经过 A 股回测验证的有效因子模板

以下公式已在 CSI300 数据集验证，IC 统计显著，可直接用于 proposed_formula 或作为变体出发点：

```python
# 1. Amihud 非流动性因子（市场冲击代理）
# IC ≈ 0.03~0.05，适合价值+低流动性方向
Mean(Abs($close/Ref($close,1)-1) / ($volume * $close), 20)

# 2. 量价背离因子（资金撤退信号）
# 负相关 = 放量下跌 or 缩量上涨，均为弱势
Corr(Rank($volume, 10), Rank($close, 10), 20)

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
- 除法分母加 `1e-8` 防止零除（Validator 不检查，但 Qlib 执行时可能产生 NaN）
- 以上模板为出发点，结合当前 Island 上下文和市场状态做变体，不要直接照搬

---

*最后更新：2026-03-07*
