---
name: pixiu-worker-brief
description: Use before delegating any worker task in Pixiu so the brief has bounded ownership, truth anchors, verification expectations, and clear done criteria instead of inviting the agent to invent scope
---

# Pixiu Worker Brief

## Overview

worker 不是来替主线程补需求的。

brief 必须把任务边界、真相锚点、写集和验证方式一次讲清。

## Trigger

任何 worker 派单前都用：

- 单模块实现
- 文档收口
- bugfix
- 测试补强
- 审计扫描

## Required Template

每个 brief 都必须包含：

- `Task`
- `Context`
- `Constraints`
- `Output`
- `Done When`

## Pixiu Guardrails

brief 里还必须明确：

- 允许写哪些文件
- 哪些 truth docs 相关
- 需要跑什么验证命令
- 是否允许更新 docs
- 是否允许提交

## Good vs Bad

### Bad

`去把 Stage 2 弄好，顺便看看文档。`

问题：

- 没有写集
- 没有 truth anchor
- 没有验证入口
- 范围无限

### Good

`Task: 只修 factor_algebra 的 prompt contract。`

`Context: 依据 docs/plans/... 和最新 round artifact，当前 validator waste 主要来自 factor_algebra。`

`Constraints: 只改 researcher.py 和对应 tests；不要碰 Stage 3。`

`Output: 说明改了什么、为什么、跑了哪些测试。`

`Done When: targeted tests 通过，真实 single 产出 artifact，且 rejection mix 有变化。`

## Output Requirement

worker 返回必须包含：

1. `What changed`
2. `Why`
3. `Verification`
4. `Open items`

没有 verification，不算完成。
