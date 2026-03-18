# Stage 5 Judgment Expansion Notes

Purpose: Preserve richer Stage 5 expansion ideas that are worth keeping, but should not be confused with the current deterministic MVP.
Status: planned
Audience: both
Canonical: no
Owner: core docs
Last Reviewed: 2026-03-18

这篇文档收纳的是 Stage 5 的增强方向，不是当前运行时真相。

## 1. 为什么移到这里

当前 Stage 5 已经有一个清晰主线：

- `Critic`
- `RiskAuditor`
- `PortfolioManager`
- `ReportWriter`

但后三者目前都是 deterministic MVP。把 richer 审计、组合优化和报告生成草案继续塞在 active design 正文里，会让读者误以为这些能力已经进入主干。

## 2. 风险审计增强方向

未来版本值得继续做的方向包括：

- IS / OOS 分段指标与过拟合比率
- 因子相关性矩阵，而不只是公式完全相同检测
- 边际组合贡献分析
- 更细的 regime-aware 风险标注

这些方向都应建立在当前 `RiskAuditReport` contract 已经稳定的前提上。

## 3. 组合层增强方向

未来如果要扩展 `PortfolioManager`，更合理的顺序是：

1. 保持 deterministic baseline 可用
2. 先扩展约束和优化目标
3. 最后才考虑引入更复杂的 LLM 辅助解释或策略建议

也就是说，组合层升级的重点应是 contract 和 objective，而不是先换成“更聪明的 agent”。

## 4. 报告层增强方向

未来 `ReportWriter` 可以做得更丰富，但当前不应把这些设想当作已实现能力：

- 更细的 high-level narrative synthesis
- round-over-round portfolio change explanation
- 人类审批建议的更强可比性
- 更适合控制平面持久化和审计的报告分层

## 5. 当前主文档

当前有效设计仍以：

- `../design/24_stage-5-judgment.md`
- `../design/25_stage-45-golden-path.md`

为准。
