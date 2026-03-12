# Current Implementation Plan

> 更新时间：2026-03-09
> 来源：`docs/overview/spec-execution-audit.md`、`docs/design/stage-45-golden-path.md`

---

## 目标

把 Pixiu 从“规格领先、运行时分叉”的状态，推进到“Stage 4/5 闭环可收敛、测试入口稳定”的状态。
并逐步完成 authority model 收口：LLM 负责认知，deterministic 系统负责执行真值。

---

## 当前阶段

### Phase A: 文档与入口收敛

- [x] 建立 `docs/README.md`
- [x] 建立 `docs/overview/README.md` 与 `docs/design/README.md`
- [x] 建立规格执行审计
- [x] 建立测试管线设计
- [x] 拆分旧总览文档中过重主题
- [x] 建立 Stage 4→5 golden path 收口规格

### Phase B: Stage 4 收口

- [x] 明确 `src/execution/` 为唯一执行路径
- [x] 清理 orchestrator 中旧 coder 接口
- [x] 明确 `BacktestReport` 的唯一生成方式（最小版）
- [x] 对应补 execution integration tests

### Phase C: Stage 5 MVP

- [x] 实现 deterministic `Critic`
- [x] 打通 `FactorPool.register_factor` 的最小写回路径
- [x] 生成最小 `CIOReport`
- [x] 明确 `src/agents/judgment.py` 为唯一 Stage 5 主路径，旧 Stage 5 文件降级为兼容层

注：当前已经落下 deterministic `Critic / RiskAuditor / PortfolioManager / ReportWriter` 的最小运行时，但 richer contract 和控制平面还未完成。

### Phase D: 测试基础设施

- [x] 配置 pytest 入口，无需手工 `PYTHONPATH`
- [x] 注册 marker：`smoke/unit/integration/live/e2e`
- [x] 将实验脚本隔离出默认 pytest 收集路径
- [ ] 收敛 async 测试的长期策略：继续同步包装或正式引入 `pytest-asyncio`

### Phase E: 控制平面与产品层

- [x] 设计并落最小 `state_store`
- [x] 收敛 CLI/API 到稳定数据面的最小读路径
- [ ] 再考虑 Dashboard 落地

---

## 当前验收结论

当前已经不是“Stage 4/5 没落地”，而是：

- 方向明确
- schema 基本成型
- Stage 4/5 最小闭环已经可运行、可回归
- 默认测试入口已经稳定
- 最小 control-plane state_store 已经落地
- richer contract 已开始进入主干，但仍处在新旧字段双轨期
- 当前主任务转为 richer contract 收口、控制平面扩展和产品层收口
