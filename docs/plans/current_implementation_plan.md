# Current Implementation Plan

> 更新时间：2026-03-09
> 来源：`docs/specs/v2_spec_execution_audit.md`、`docs/specs/v2_stage45_golden_path.md`

---

## 目标

把 Pixiu 从“规格领先、运行时分叉”的状态，推进到“Stage 4/5 闭环可收敛、测试入口稳定”的状态。

---

## 当前阶段

### Phase A: 文档与入口收敛

- [x] 建立 `docs/README.md`
- [x] 建立 `docs/specs/README.md`
- [x] 建立规格执行审计
- [x] 建立测试管线规格
- [x] 拆分 `v2_architecture_overview.md` 中过重主题
- [x] 建立 Stage 4→5 golden path 收口规格

### Phase B: Stage 4 收口

- [ ] 明确 `src/execution/` 为唯一执行路径
- [ ] 清理 orchestrator 中旧 coder 接口
- [ ] 明确 `BacktestReport` 的唯一生成方式
- [ ] 对应补 execution integration tests

### Phase C: Stage 5 MVP

- [ ] 实现 deterministic `Critic`
- [ ] 打通 `FactorPool.register_factor`
- [ ] 生成最小 `CIOReport`

注：当前计划不先推进完整 `RiskAuditor / PortfolioManager / ReportWriter` 栈，等 deterministic MVP 收口后再评估。

### Phase D: 测试基础设施

- [ ] 配置 pytest 入口，无需手工 `PYTHONPATH`
- [ ] 引入并配置 `pytest-asyncio`
- [ ] 注册 marker：`smoke/unit/integration/live/e2e`
- [ ] 将实验脚本移出默认 pytest 收集路径

### Phase E: 控制平面与产品层

- [ ] 设计 state store
- [ ] 收敛 CLI/API 到稳定的数据面
- [ ] 再考虑 Dashboard 落地

---

## 当前验收结论

不是“项目没做出来”，而是：

- 方向明确
- schema 基本成型
- 部分运行时主干已存在
- 但 Stage 4/5 和测试基础设施还没有完成真正的工程收口
