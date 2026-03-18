# Pixiu v2 Stage 5: Judgment and Reporting
Purpose: Define the current Stage 5 runtime from deterministic judgment through portfolio allocation and CIO reporting.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-18

> 前置依赖：`11_interface-contracts.md`、`14_factor-pool.md`
> 关联文档：`25_stage-45-golden-path.md`
> 补充说明：`../futures/stage-5-judgment-expansion.md`

---

## 1. 角色边界

Stage 5 接收 Stage 4 产出的 `BacktestReport`，把它们收敛成可审计、可落库、可提交给人类审批的对象。

当前主干里的顺序是：

1. `judgment_node`
2. `portfolio_node`
3. `report_node`

对应的主要输出是：

- `CriticVerdict`
- `RiskAuditReport`
- `PortfolioAllocation`
- `CIOReport`

Stage 5 的职责不是继续修改公式，也不是重试执行。它只做结构化判断、风险补充、组合更新和审批材料生成。

## 2. 当前 runtime 组件

| 组件 | 当前状态 | 运行时职责 |
|---|---|---|
| `Critic` | active | 对 `BacktestReport` 做 deterministic checks、打分、决策和失败归因 |
| `RiskAuditor` | active MVP | 做最小风险审计：高换手/执行失败的 overfitting penalty，以及与已通过因子的简单相似性检查 |
| `PortfolioManager` | active MVP | 基于本轮通过因子生成 equal-weight allocation |
| `ReportWriter` | active MVP | 生成模板化 `CIOReport`，并显式挂起等待人类审批 |

这四个组件都已经在 `src/agents/judgment/` 包下收口。

## 3. `Critic`

`Critic` 是当前 Stage 5 的核心。

它的工作包括：

- 根据 `THRESHOLDS` 生成 `checks`
- 计算 `overall_passed`
- 诊断 `failure_mode / failure_explanation / suggested_fix`
- 生成 `decision / score / reason_codes`
- 记录 `regime_at_judgment`

当前 `Critic` 的意义不是“让 LLM 评价因子”，而是把 Stage 4 的执行结果压缩成一个足够稳定、足够可下游消费的 judgment object。

## 4. `RiskAuditor`

`RiskAuditor` 当前是一个最小 deterministic MVP，而不是完整的统计审计层。

当前已做的事情：

- 若执行失败，给出 execution-error penalty
- 若换手率超过阈值，给出 overfitting score
- 若和已通过因子公式完全一致，标记 `too_similar`
- 输出 `manual_review` 或 `clear`

更丰富的相关性矩阵、OOS/IS 比值、组合边际贡献分析，已经移到 `../futures/stage-5-judgment-expansion.md`。

## 5. `PortfolioManager`

`PortfolioManager` 当前不是 LLM 组合优化器，而是 deterministic equal-weight allocator。

它只做这几件事：

- 读取本轮 `overall_passed=True` 的 verdicts
- 找到对应的 `BacktestReport`
- 为每个通过因子分配等权
- 输出 `PortfolioAllocation`

这保证了当前 Stage 5 是可运行、可测试、可解释的 MVP。

## 6. `ReportWriter`

`ReportWriter` 当前是模板化 CIO 报告生成器。

它会：

- 汇总本轮测试数量和通过数量
- 找出最佳因子
- 生成简洁 markdown
- 给出 `suggested_actions`
- 将 `requires_human_decision` 设为 `True`

因此当前运行时依然保留明确的 human gate，而不是让 Stage 5 自动落到最终动作。

## 7. 与 FactorPool 和约束沉淀的关系

当前 `judgment_node` 在循环处理 `BacktestReport` 时会：

- 生成 `CriticVerdict`
- 生成 `RiskAuditReport`
- 在 `register_to_pool=True` 时写入 `FactorPool`
- 对失败样本尝试提取 `FailureConstraint`

这里最重要的系统约束是：

- 通过与失败都要被沉淀
- 失败沉淀优先进入结构化约束，而不是只留日志
- 设计与实现的细微偏差统一记录到 `../overview/05_spec-execution-audit.md`

## 8. 当前边界

Stage 5 现在已经有了稳定的最小闭环，但还不是完整的 judgment platform。

仍然刻意保持简化的部分包括：

- 风险审计还是最小 MVP
- 组合层还是 equal-weight，而不是优化求解
- 报告层还是模板生成，而不是 richer narrative synthesis

这不是缺陷隐藏，而是当前 authority model 的选择：先确保对象稳定，再扩展策略层复杂度。
