# Pixiu Self-Evolution Loop Design

**Date:** 2026-03-24  
**Status:** Drafted and approved for future implementation

## Goal

定义 Pixiu 的最小自进化回路，回答三件事：

- 系统到底学习什么
- 系统绝不自动改什么
- 一轮实验结束后，哪些经验应该写回并改变下一轮搜索分布

这份设计不要求当前立刻实现完整自进化系统。它的作用是给主线一个稳定方向，避免后续把“多记一些失败”误当成真正进化。

## Why Now

截至 2026-03-24，Pixiu 已经从“完全跑不起来”推进到“可以完成短实验”。当前主瓶颈不再只是低级 contract failure，而是：

- `factor_algebra` 仍然有明显 collapse
- `cross_market / narrative_mining` 仍有 alignment grounding 问题
- failure 仍然更多表现为日志和约束，而不是可控的学习回路

这说明 Pixiu 需要的不只是更多过滤器，而是一条明确的：

`Read -> Execute -> Reflect -> Write`

回路。

## Core Principle

Pixiu 的自进化对象不应该是“通用技能库”或“运行时代码本身”，而应该是：

> 外部研究记忆、生成策略和搜索分布。

也就是说，Pixiu 的第一阶段自进化属于 `deployment-time learning`：

- 不更新模型参数
- 不自动改主代码
- 不自动改 Stage 3 硬门
- 通过外部记忆和策略写回改变下一轮行为

## Mapping the Loop to Pixiu

### Read

读取当前可用的研究资产：

- `factor_pool`
- `failure observations / constraints`
- `factor_gene / family memory`
- `market regime`
- `subspace priors`
- `scheduler utility`

### Execute

当前主链执行：

- `Stage 1` 市场上下文
- `Stage 2` 假设生成
- `Stage 3` 过滤
- `Stage 4` 回测
- `Stage 5` judgment

### Reflect

不是只看一轮通过了多少，而是看：

- rejection mix
- 哪个 family 在 collapse
- 哪个 subspace 的 alignment 最差
- 哪类 hypothesis 的通过率更高
- token/cost 花在哪

### Write

只把可行动的经验写回：

- `factor_pool`
- `failure observation`
- `anti-collapse memory`
- `mechanism -> proxy` 经验
- `subspace utility / diversity weight`

## Learnable Objects

Pixiu 当前最适合演化的对象分 5 类。

### 1. Failure Memory

记录可复现、可归因、会重复出现的失败模式。

作用：

- 阻止重复犯低级错误
- 提供 warning priors
- 为后续 promotion policy 提供输入

### 2. Gene / Family Memory

记录 factor family、variant、饱和 family、collapse family。

作用：

- family-level novelty
- anti-collapse steering
- 因子库的 family retrieval

### 3. Subspace Policy

记录每个子空间当前的生成偏好、禁区和有效策略。

作用：

- 让 `factor_algebra / cross_market / narrative_mining / symbolic_mutation` 不再完全依赖静态 prompt
- 允许不同子空间逐步形成各自的搜索纪律

### 4. Mechanism-Proxy Library

记录哪些机制假设能够被哪些可用代理变量稳定表达。

作用：

- 解决 `cross_market / narrative_mining` 的 alignment grounding
- 把“故事”逐步压成可执行研究对象

### 5. Scheduler Utility / Diversity Weights

记录哪个子空间、哪个 family、哪个 regime 下的探索更值得继续。

作用：

- 从简单 quota 演化到 diversity-aware scheduling
- 避免系统长期围绕少数高熟悉度模板绕圈

## Non-Learnable Boundaries

以下对象不应由 Pixiu 运行时自动改写。

### 1. Stage 3 Hard Gate

包括：

- canonical validator path
- 数学安全
- 基本 novelty hard gate

原因：

- 这是主链可信度边界
- 不能被运行时反思直接污染

### 2. Schema Truth

包括：

- `src/schemas/`
- stage I/O contract
- control-plane snapshot contract

原因：

- schema 是人类主导的系统边界
- 不能由实验回路自动漂移

### 3. Execution Layer Behavior

包括：

- deterministic execution
- backtest 执行规则
- allocation 基础规则

原因：

- Pixiu 当前架构原则仍然是“扩大 hypothesis space，不扩大 execution power”

### 4. Runtime Code / Skills

运行时不应直接自动改：

- 主代码
- Stage 间接口
- Stage 3 逻辑
- repo-local Codex workflow skills

原因：

- 这是工程控制面，不是研究记忆

## Minimal Self-Evolution Loop v1

这轮不做“大而全的自进化框架”。先做最小闭环：

1. 一轮实验结束
2. 生成 `failure observations`
3. 生成/更新 `factor_gene family memory`
4. 生成/更新 `subspace utility summary`
5. 下一轮 `Stage 2` 读取这些对象
6. 改变生成分布，而不是只重复生成再被拦截

当前最小落地点是：

- `factor_gene -> anti-collapse memory -> Stage 2 steering`

这是 Pixiu 版最小自进化，不需要先上模型训练。

## Quality Rule

Pixiu 的经验不是“越多越好”，而是“越能改变下一轮行为越好”。

所以可写回经验至少应满足：

- `reproducible`
- `attributable`
- `actionable`
- `net-useful`

否则只留在日志或 observation 层，不进入长期记忆。

## Relationship to Model Training

模型训练不是这条线的第一优先级。

更合理的顺序是：

1. 外部记忆和反馈回路提质
2. 高质量偏好样本和反例样本沉淀
3. 小规模 SFT / DPO
4. 最后才考虑 RL

原因：

- 当前 reward 仍然太噪
- 当前失败经验仍需要 promotion policy
- 现在直接上 RL，容易把噪声内化进模型

## Success Criteria

如果这条自进化回路开始生效，应该能看到下面这些变化：

- 同一 family 的重复 rejection 下降
- 某些 subspace 的 through-rate 上升
- alignment rejection 更集中、更可解释
- token 浪费减少
- experiment artifact 中的 rejection mix 出现结构性变化，而不是随机波动

## Near-Term Priorities

这份设计写完后，不直接开启“大自进化项目”。当前主线仍然是：

1. `factor_gene / anti-collapse`
2. `cross_market / narrative_mining` grounding
3. `experiment reliability platform`

这三条跑稳后，再逐步把：

- failure promotion policy
- subspace policy write-back
- scheduler diversity weights

接进运行时。
