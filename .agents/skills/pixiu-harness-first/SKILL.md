---
name: pixiu-harness-first
description: Use when changing Pixiu mainline runtime behavior, stage contracts, experiment flow, or bug fixes that require proof through profiles, harness commands, and artifacts rather than code inspection alone
---

# Pixiu Harness First

## Overview

Pixiu 主链改动默认先绑定验证入口，再写实现。

不是“写完再想怎么测”，而是“先说清楚用什么证明它变好了”。

## Trigger

出现下面任一情况就用：

- 改 Stage 行为
- 改 experiment harness / preflight / doctor
- 改 schema 或 stage contract
- 改会影响 `single / evolve` 的主链逻辑
- 修一个必须靠 runtime 才能证实的 bug

## Required Decision

开工前先明确三件事：

1. 这是 `fast feedback` 还是 `controlled run`
2. 用哪个命令验证；如果已存在稳定 profile，再写 profile
3. 哪个 artifact / 输出证明成功

## Validation Modes

### Fast Feedback

只回答局部工程问题：

- Stage 2/3 废料是否下降
- 某个子空间是否更干净
- 某个 contract failure 是否不再出现

它不用于证明正式研究效果。

### Controlled Run

用于验证主链没有被破坏：

- `doctor`
- `preflight`
- `single`
- `evolve 2 rounds`

## Pixiu Anchors

优先绑定这些入口：

- `scripts/experiment_preflight.py`
- `scripts/run_experiment_harness.py`
- `data/experiment_runs/{run_id}/round_*.json`

## Do Not Do This

- 不要一上来就跑长轮次
- 不要只看日志就宣称修好
- 不要把 `fast feedback` 结果说成正式基线
- 不要在没有 resolved profile 的情况下跑实验

## Output Requirement

实现前先写出：

- `Validation mode: ...`
- `Command: ...`
- `Profile: ...`（如适用）
- `Proof artifact: ...`

缺任何一项，都不算准备完成。
