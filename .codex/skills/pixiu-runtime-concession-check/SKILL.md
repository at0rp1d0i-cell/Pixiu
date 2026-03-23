---
name: pixiu-runtime-concession-check
description: Use when introducing a fallback, degraded mode, experiment-only shortcut, compatibility bridge, or deferred runtime behavior that might need to be recorded in the runtime concessions ledger
---

# Pixiu Runtime Concession Check

## Overview

Pixiu 不再允许临时让步只存在于聊天里。

如果这次改动引入了运行时让步，就要判断它是不是应该进入 runtime concessions ledger。

## Trigger

出现下面任一情况就用：

- 新 fallback
- 自动审批或 special-case gate
- degraded mode
- 实验专用 shortcut
- compat bridge
- 明确延期实现的运行时能力

## Required Check

先判断这件事属于哪类：

- `experiment_concession`
- `mvp_simplification`
- `compat_bridge`
- `deferred`

然后再判断：

- 这是正常设计选择，还是需要记账的运行时让步
- 是否必须更新 [06_runtime-concessions.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/06_runtime-concessions.md)

## Concession vs Drift

- `concession`
  - 我们知道这不是最终形态，但当前阶段故意接受
- `drift`
  - 设计和实现偏了，但没有明确接受它

`drift` 不是这份账本的对象。发现 drift 时，应先回报给 coordinator，由 coordinator 决定是否更新 [05_spec-execution-audit.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/05_spec-execution-audit.md)。

## Not Everything Goes Into The Ledger

以下内容通常不进 `06`：

- 一般性工程债
- 已归档的旧兼容层
- 纯前瞻设想
- 只影响实现细节、不改变运行时行为的内部重构

## Pixiu Examples

- `human_gate_auto_action`
  - 是 `experiment_concession`
- Stage 5 deterministic/template flow
  - 是 `mvp_simplification`
- FactorPool persistent -> in-memory
  - 是 `compat_bridge`
- failure curator 暂不实现
  - 是 `deferred`

## Output Requirement

引入让步时，说明里必须出现一句：

`Concession check: ...`

如果结论是“不入账”，也要给理由。
