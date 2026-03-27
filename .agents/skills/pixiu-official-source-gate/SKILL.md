---
name: pixiu-official-source-gate
description: Use when changing behavior that depends on external system semantics such as Qlib, Tushare, OpenAI, Chroma, or MCP, especially when a worker might otherwise implement from memory or guesswork
---

# Pixiu Official Source Gate

## Overview

Pixiu 不允许“没查官方资料就直接写外部语义”。

只要这次改动依赖外部系统语义，先找证据，再动实现。

## Trigger

出现下面任一情况就用这个 skill：

- 要改 `Qlib` 算子、字段、表达式语义
- 要改 `Tushare` 数据字段、接口或数据契约
- 要改 `OpenAI` 模型、Responses API、token/cost 口径
- 要改 `Chroma` 持久化、collection、embedding 行为
- 要改 `MCP` server/client、tool 契约、stdio 行为

## Required Workflow

1. 先写明本次依赖的外部真相对象是什么。
2. 先查以下任一证据源：
   - 官方文档
   - 本地已安装 runtime 的真实行为
   - 已存在且可核对的 canonical 项目文档
3. 在开工前明确记录：
   - 用了哪个来源
   - 哪条语义是硬事实
   - 哪条仍是推断
4. 若证据不足：
   - 不直接改实现
   - 先把缺口标明，再去补证据

## What Counts As Evidence

- `Qlib`
  - 官方文档 + 本地安装版本行为
- `Tushare`
  - 官方接口文档 + 当前账号可用性
- `OpenAI`
  - 官方 OpenAI 文档
- `Chroma`
  - 官方文档或本地库行为
- `MCP`
  - 官方协议/工具文档 + 当前 server 行为

## Pixiu Examples

- 改 `Rank` / `Quantile` 语义前，先核 `Qlib` 官方 operator 签名和本地 runtime 行为。
- 改 Stage 1 `moneyflow_hsgt` / `margin` 接口前，先核 `Tushare` 官方字段和当前账号可用性。
- 改 token ledger 前，先核 OpenAI 官方 Responses/usage 文档，而不是从旧聊天里猜。

## Stop Condition

以下情况不允许直接改代码：

- 没有找到任何可信来源
- 只有二手博客或记忆，没有官方或 runtime 证据
- 当前项目文档本身就在漂移，且没有回到更高真相层核对

## Output Requirement

任务说明或实现说明里必须包含一句：

`Source checked: ...`

没有这句，默认视为证据链不完整。
