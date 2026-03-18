# Pixiu v2 Stage 4: Execution Layer
Purpose: Define the deterministic Stage 4 execution path and the boundary between optional exploration and canonical backtest execution.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-18

> 前置依赖：`11_interface-contracts.md`
> 关联文档：`25_stage-45-golden-path.md`、`16_test-pipeline.md`
> 补充说明：`../futures/stage-4-exploration-branch.md`

---

## 1. 角色边界

Stage 4 的职责不是继续“想办法”，而是把 Stage 2 交付的研究对象推进到可回放、可审计的执行产物。

当前主干里，Stage 4 有两条不同权重的路径：

- canonical path
  - `FactorResearchNote.final_formula -> Coder -> DockerRunner -> BacktestReport`
- optional branch
  - `exploration_questions -> ExplorationAgent -> ExplorationResult`

其中第一条是 Stage 4 到 Stage 5 的当前主闭环。第二条仍然存在，但不是 golden path 的默认入口。

## 2. 当前 canonical path

当前运行时的核心文件是：

- `src/execution/coder.py`
- `src/execution/docker_runner.py`
- `src/execution/templates/qlib_backtest.py.tpl`

这条路径的原则很简单：

- `Coder` 不调用 LLM
- 输入只认 `FactorResearchNote.final_formula`
- 输出必须是 `BacktestReport`
- 回测脚本、stdout、stderr 都应可追溯

### `Coder`

`Coder` 当前负责四件事：

1. 从 `FactorResearchNote` 提取 `final_formula`
2. 用固定模板编译脚本
3. 调用 `DockerRunner` 在隔离环境中执行
4. 解析 `BACKTEST_RESULT_JSON`，并写出 `BacktestReport`

当前实现里，`Coder` 还会顺手持久化本轮 artifacts：

- `script.py`
- `stdout.txt`
- `stderr.txt`

因此 Stage 4 不是一个“黑盒回测器”，而是一个可复盘的 deterministic executor。

### `DockerRunner`

`DockerRunner` 是 Stage 4 的共享执行沙箱。

当前约束包括：

- `docker run --network=none`
- Qlib 数据目录只读挂载
- 临时脚本单次执行
- 超时终止
- stdout / stderr 结构化回传

这条边界非常重要，因为它保证 Stage 4 的智能不会重新渗回执行层。

## 3. Optional Exploration Branch

`ExplorationAgent` 仍存在于代码主干，也仍可消费 `FactorResearchNote.exploration_questions`。

但当前应当把它理解为：

- 一个按需使用的探索分支
- 服务于问题澄清、EDA 和 note refinement
- 不等于 Stage 4 的 canonical closure

也就是说：

- 可以有 `ExplorationResult`
- 但进入 Stage 5 的正式执行凭证仍然必须是 `BacktestReport`

更细的探索分支说明已经移到 `../futures/stage-4-exploration-branch.md`，避免当前主路径和旁支设计混在一篇文档里。

## 4. 与 Stage 5 的接口

Stage 4 向下游交付的对象必须保持收敛：

- 主对象：`BacktestReport`
- 失败也必须产出结构化失败报告
- Stage 5 只消费结构化指标和失败原因，不接收执行层自由文本

当前 richer report contract 仍在继续收口，最新偏差以 `../overview/05_spec-execution-audit.md` 为准。

## 5. 验证边界

Stage 4 的默认验证不再写在本页长段落里，而是由两份文档承接：

- `16_test-pipeline.md`
  - 说明 smoke/unit/integration 的默认入口
- `25_stage-45-golden-path.md`
  - 说明当前 Stage 4 -> 5 的最小闭环验收标准

对于当前实现，最重要的验证点是：

- 合法公式能产出结构化 `BacktestReport`
- 非法公式能返回结构化失败
- `BACKTEST_RESULT_JSON` 解析稳定
- Docker 沙箱保持无网络、可超时终止、可追踪 artifacts

## 6. 设计约束

- 不要把脚本修复、执行重试、策略推理塞回 Stage 4
- 不要让 `Coder` 退化成通用代码助手
- `ExplorationAgent` 可以帮助理解问题，但不能替代 deterministic backtest
- 任何新增能力都应优先体现为更好的 typed contract，而不是更多执行层智能
