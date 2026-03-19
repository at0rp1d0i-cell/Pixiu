Status: historical
Owner: research infra
Last Reviewed: 2026-03-19

> Archived on 2026-03-19. The actionable guidance here has been absorbed by
> `docs/reference/data-download-guide.md`. Keep this note only for historical context.

# 深度检索与架构重构：A股日线数据至 Microsoft Qlib 底层.bin 格式的完美转换实践

（本篇内容由多轮对话的历史研报提炼，包含必须遵循的极端数据清洗与序列化规范）

## 核心坑点与解决方案的底层逻辑

1. **复权机制的数学推演**：
   - 必须使用**后复权（hfq）**数据，保证长周期深度学习模型中的价格序列绝对大于零，避免 NaN 爆炸。
   - 必须根据 $Factor = Adjusted\_Price / Original\_Price$ 逆向推算独立的 `factor` 列。
   - 必须反向缩小交易量：$Volume\_adj = Volume\_unadj / Factor$，以保持真实成交额 `amount` 恒定。这是触发 Qlib 实盘交易单位（最小1手）校验的关键。

2. **停牌股与 NaN 遮罩机制**：
   - 如果股票停牌（成交量为 0），其当天的 OHLCV 及 factor 必须被显式强制设置为 `np.nan`。
   - Qlib 内置的 `DropnaProcessor` 组件依赖这些 `NaN` 来执行遮罩，以阻断神经网络在静态无效价格上的错误梯度更新。

3. **Apache Parquet 与 dump_bin 编译**：
   - 弃用易引发类型推测异常的 CSV 格式，转而使用 Parquet 作为暂存层。
   - `dump_bin.py` 本质上是一个“静态类型编译器”，它将所有 `include_fields` 强转为 `<f` (32位浮点数)。如果未在此前通过 `--exclude_fields symbol,date` 剔除字符串，系统将直接崩溃。

4. **股票代码正规化映射**：
   - 上交所：`SH600000`/`SH688001`
   - 深交所：`SZ000001`/`SZ300001`
   - 北交所：`BJ835185`

---
*注：项目早期曾因环境限制采用 BaoStock 和自写字节流转换脚本，但这里记录的仍是更稳的长期数据管线标准。*
