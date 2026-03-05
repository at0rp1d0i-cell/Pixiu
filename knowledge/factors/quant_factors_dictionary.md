# 📚 Qlib Quantitative Factors Dictionary (Layer 1 Prompt Inject)

## 1. 原理与定位
这是你的核心量价因子教典。在生成交易策略和特征工程代码时，**不要**使用外行的“均线金叉”语言。你必须使用 Qlib 内置的操作符（`Mean`, `Std`, `Delay`, `Delta`, `Rank`, `Count`, `Corr`）来构建有深刻数学统计意义的因子公式。

## 2. Qlib 数据集的基础算子 (Operators)
Qlib 的 `ExpressionOps` 支持极其强大的时序和截面计算。例如：
- `Ref($close, 1)`: 昨日收盘价 (也是 `Delay` 的同义词)。
- `Mean($close, 5)`: 过去 5 天收盘价的移动平均。
- `Std($close, 20)`: 过去 20 天收盘价的标准差（衡量波动率）。
- `Roc($close, 10)`: 10 天的变化率 (Rate of Change) = `($close - Ref($close, 10)) / Ref($close, 10)`。
- `Rank($close)`: 截面排名（当天全市场股票的收盘价排名，输出 0~1 的分位数）。
- `Corr($close, $volume, 10)`: 过去 10 天收盘价和成交量的时序相关系数（衡量量价背离）。

## 3. Alpha158 核心逻辑（参考范例）
Alpha158 提供了一组经过验证的因子组合，你在构建挖掘新因子时应模仿这种数学抽象思路：

### A. 趋势与动量因子 (Trend & Momentum)
捕捉股票中长期的惯性效应。
- **KMO1M**: 过去 1 个月（20天）的动量 `Roc($close, 20)`
- **VROC10**: 10天成交量变化率 `Roc($volume, 10)`
- **MA_DIFF**: 均线乖离 `(Mean($close, 5) - Mean($close, 20)) / Mean($close, 20)`

### B. 均值回归与反转因子 (Mean-Reversion)
寻找短期超买或超卖。
- **BIAS10**: 乖离率 `($close - Mean($close, 10)) / Mean($close, 10)`
- **RSI**: 相对强弱指标（通过价格涨跌序列的 `Sum` 和 `Abs` 构建）。

### C. 量价分析因子 (Volume-Price Relationship)
最容易产生 Alpha 的区域。
- **VIMA (Volume-Price Correlation)**: `Corr($close, $volume, 5)`
  - 如果价格上涨且相关性高，说明是**放量上涨**（买入动能强）。
  - 如果价格上涨但相关性为负，说明是**缩量上涨**（可能动能衰竭）。
- **WVAD (Williams's Variable Accumulation/Distribution)**: 衡量资金流入流出的压力。

### D. 波动率与风险因子 (Volatility)
- **HighLow_Ratio**: 振幅 `($high - $low) / Ref($close, 1}')`
- **Return_Std**: 收益率的波动 `Std(Roc($close, 1), 20)`

## 4. 你的任务标准
当你要提出一个新的 Hypothesis（假设）时，你的输出格式必须包含明确的 Qlib 公式。
例如，不要说：“我觉得成交量放大的时候应该买入”。
你应该说：
> **Hypothesis**: 基于资金抢筹逻辑，我们将尝试挖掘一个短期量价共振因子。
> **Formula**: `Rank(Corr($close, $volume, 5)) * Roc($close, 1)` 
> **Logic**: 我们截面选取过去 5 天量价正相关性最强的股票池，并乘以昨日动能，以捕捉流动性溢价。
