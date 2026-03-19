# Tushare Dataset Matrix

Purpose: Summarize which official Tushare datasets matter for Pixiu, what they are good for, and how they should enter the stack.
Status: active
Audience: both
Canonical: no
Owner: research infra
Last Reviewed: 2026-03-19

## 1. Why This Exists

Tushare 的问题不是“有没有数据”，而是“太多接口都能下，但并不是每一条都值得接进 Pixiu 主路径”。

这份矩阵只回答三件事：

- 官方有哪些和 Pixiu 真正相关的数据面
- 它们更适合进入哪一层
- 当前本地状态和接入优先级是什么

如果你只想知道本地怎么跑下载脚本，看：

- `docs/reference/data-download-guide.md`

## 2. Adopt / Stage / Watch

| 数据集 | 官方 API | 更适合进入哪层 | Pixiu 价值 | 当前建议 |
|---|---|---|---|---|
| 价量基础行情 | `daily` / `pro_bar` / `adj_factor` | 回测直接读取层 | 回测底座 | 已采用，继续用 Qlib 主链 |
| 每日指标 | `daily_basic` | 扩展结构化字段层 | 估值、换手率、市值 | P0，已在下载与转换 |
| 财务指标 | `fina_indicator` | 扩展结构化字段层 | `roe` 等财务质量信号 | P0，已转换 |
| 个股资金流 | `moneyflow` | 扩展结构化字段层 / Agent 上下文层 | 量价/资金流 alpha | P1，建议尽快接 |
| 沪深港通日资金流 | `moneyflow_hsgt` | Agent 上下文层 | 北向/南向宏观风险偏好 | P1，已开始接入 |
| 沪深港通持股明细 | `hk_hold` | Agent 上下文层 | 北向历史持仓结构 | 历史价值高，但注意官方断档 |
| 融资融券汇总/明细 | `margin` / `margin_detail` | 扩展结构化字段层 / Agent 上下文层 | 杠杆风险偏好 | P1，汇总已接，明细待补 |
| 每日涨跌停价格 | `stk_limit` | 扩展结构化字段层 | A 股特有约束与时滞 | P1，建议尽快接 |
| 指数成分和权重 | `index_weight` | Agent 上下文层 / 数据治理层 | 基准、成分调整、风格暴露 | P2，值得接 |
| 指数成分全集 | `index_member_all` | 数据治理层 | 行业/指数 membership | P2，值得接 |
| 三大财务报表 | `income` / `balancesheet` / `cashflow` | 扩展结构化字段层 | 更丰富的会计特征 | P2，慎重接入 |

## 3. Recommended Order

### P0: Already justified

- `fina_indicator`
- `daily_basic`

理由：

- 直接补强 `valuation` / `fundamental` 型研究
- 与当前 Stage 2/3 的字段白名单最直接相关
- 已经有本地脚本链和 capability scan

### P1: Most worth adding next

- `moneyflow`
- `moneyflow_hsgt`
- `stk_limit`
- `margin_detail`

理由：

- 都是 A 股特有、研究价值高、比“再加更多财报列”更快产生 alpha 研究收益
- 对 `volume / northbound / volatility / narrative` 几个方向都直接有帮助
- 其中 `moneyflow_hsgt` 与 `stk_limit` 对 Stage 1 市场上下文尤其实用

### P2: Add after P1 stabilizes

- `index_weight`
- `index_member_all`
- `income`
- `balancesheet`
- `cashflow`
- `forecast`
- `express`

理由：

- 价值高，但更依赖完整 PIT 处理、字段治理和更细的 schema
- 更适合在 Stage 2/3/4 已经稳定消费 `daily_basic + moneyflow` 后再扩

## 4. Current Local Status

截至 2026-03-19，本地数据面状态是：

- Qlib 价量主宇宙已完整
- `fina_indicator` staging 已完整，`roe` 已进入 runtime capability
- `daily_basic` 正在全量下载中，`pb / pe_ttm / turnover_rate / float_mv` 还未达到 capability 覆盖阈值
- `margin` 汇总历史已具备单表下载脚本
- `moneyflow_hsgt` 已有历史下载脚本，适合 Stage 1 北向上下文

## 5. Key Constraints

### 不要把 Tushare “下载了” 等同于 “运行时可用”

Pixiu 当前真正的可用标准不是 staging 目录里有没有 parquet，而是：

1. 数据是否 point-in-time 对齐或日度对齐
2. 是否已写入 `data/qlib_bin/features/**`
3. 本地 capability scan 是否把字段识别为可用

### 不要让 skills 写死字段与算子

Tushare 数据面的扩展速度一定会快于 prompt 文档更新速度。

所以正确约束链应该是：

- 本地 feature store / staging 真相
- runtime capability scan
- validator / researcher prompt / subspace context
- skills 只写方法，不写死“当前一定可用什么”

### 注意 `hk_hold` 的官方断档

官方文档对 `hk_hold` 明确写了：交易所从 `2024-08-20` 开始停止发布北向资金数据，因此它更适合做历史研究，不应再作为未来稳定增量主源。

## 6. Official References

- Tushare 股票/指数/财务总目录：<https://www.tushare.pro/document/2?doc_id=108>
- `moneyflow_hsgt`：<https://www.tushare.pro/document/2?doc_id=47>
- `hk_hold`：<https://www.tushare.pro/document/41?doc_id=188>
- `moneyflow`：<https://www.tushare.pro/document/2?doc_id=170>
- `cashflow` 示例页（财务报表类入口之一）：<https://www.tushare.pro/document/2?doc_id=44>

## 7. Practical Decision

如果目标是让 Pixiu 在下一阶段更像一个 A 股研究系统，而不是只会价量组合：

- 先把 `daily_basic` 跑满并转完
- 然后优先接 `moneyflow` 与 `stk_limit`
- 北向层优先用 `moneyflow_hsgt` 作为连续日级宏观流量
- `hk_hold` 保留为历史补充，不再当未来稳定主源
