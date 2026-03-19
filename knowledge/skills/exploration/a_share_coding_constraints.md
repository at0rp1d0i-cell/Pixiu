<!-- SKILL:EXPLORATION_CODING -->

# ExplorationAgent A 股编码约束

> Type B — 永久注入。规范 ExplorationAgent 生成的 Python 脚本。

---

## 1. Qlib API 使用规范

### 初始化
```python
import qlib
from qlib.data import D

# 必须在任何数据操作前初始化
qlib.init(provider_uri="/data/qlib_bin/")
```

### 数据加载
```python
# 正确：使用 D.features()
df = D.features(
    instruments="csi300",
    fields=["$close", "$volume", "$open", "$high", "$low"],
    start_time="2021-01-01",
    end_time="2025-03-31",
)

# 正确：使用 D.instruments()
instruments = D.instruments(market="csi300")
```

### 禁止的模式
```python
# ❌ 禁止直接读 CSV / Parquet
pd.read_csv("data/stock_prices.csv")

# ❌ 禁止引用未挂载的数据路径
pd.read_pickle("/external/data/factors.pkl")

# ❌ 禁止使用 tushare / akshare 等在线数据源
import tushare as ts
ts.get_k_data("000001")

# ❌ 禁止直接读 bin 文件
np.fromfile("data/qlib_bin/SH600000/close.day.bin")
```

---

## 2. 可用数据字段

| 字段 | 含义 | 注意事项 |
|------|------|----------|
| `$close` | 收盘价（前复权） | 最常用 |
| `$open` | 开盘价（前复权） | |
| `$high` | 最高价（前复权） | |
| `$low` | 最低价（前复权） | |
| `$volume` | 成交量（股） | 注意单位，非手 |
| `$factor` | 复权因子 | 用于计算真实价格 |
| `$vwap` | 成交均价 | `= amount / volume` |

### 不可用字段
- `$amount`（成交额）— 部分数据集未包含
- `$pe` / `$pb` / `$ps` — 基本面字段需通过额外数据加载
- `$market_cap` — 不在标准 qlib 字段中

---

## 3. 常见陷阱

### NaN 处理
```python
# ✅ 正确：先检查再计算
df = df.dropna(subset=["$close", "$volume"])

# ✅ 正确：使用 fillna 时要有理由
df["$volume"].fillna(0)  # 停牌日成交量为 0

# ❌ 错误：忽略 NaN 直接计算
result = df["$close"] / df["$volume"]  # volume=0 时产生 inf
```

### 日期对齐
```python
# ✅ 正确：Qlib 返回的 DataFrame 索引已对齐（instrument, datetime）
# 不需要手动对齐日期

# ❌ 错误：假设所有股票每天都有数据
# 停牌股票会缺失交易日
```

### Universe 泄漏
```python
# ❌ 错误：用当前成分股回测历史
current_stocks = get_csi300_components("2025-03-19")
historical_data = D.features(instruments=current_stocks, start_time="2021-01-01")

# ✅ 正确：使用 Qlib 的 instruments 参数，自动处理成分股变动
data = D.features(instruments="csi300", ...)
```

### 除零保护
```python
# ✅ 正确：分母加极小值
ratio = numerator / (denominator + 1e-8)

# ✅ 正确：条件过滤
valid = df[df["$volume"] > 0]
ratio = valid["$close"] / valid["$volume"]
```

---

## 4. 输出格式

脚本最后必须打印标准 JSON：

```python
import json
result = {
    "findings": "描述发现",
    "key_statistics": {"ic": 0.03, "sharpe": 1.2},
    "refined_formula_suggestion": "Mean($close, 5) / Mean($close, 20) - 1"  # 或 null
}
print("EXPLORATION_RESULT_JSON:" + json.dumps(result, ensure_ascii=False))
```

---

## 5. 性能要求

- 脚本执行时间 < 60 秒
- 避免对全市场做逐股票循环（使用 pandas 向量化操作）
- 大数据量时使用 `.sample()` 或截取子集

---

*最后更新：2026-03-19*
