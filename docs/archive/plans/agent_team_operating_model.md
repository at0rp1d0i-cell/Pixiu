# Agent Team Operating Model

Status: historical
Owner: coordinator
Last Reviewed: 2026-03-19

> Archived on 2026-03-19. The durable collaboration rules now live primarily in
> `AGENTS.md`, while current agent role boundaries live in
> `docs/design/30_agent-team.md`. Keep this file only as a historical operating memo.

> 角色：定义当前仓库里 root / worker / reviewer / explorer 的最小协作规则

## 1. 目标

这个文件不是在追求“更多 agent”，而是在控制：

- 谁持有架构真相
- 什么任务适合分发
- 什么时候该收权回 root

## 2. 角色定义

### `root`

负责：

- 持有架构与文档真相
- 切分任务
- 集成多处改动
- 做最终验证

`root` 不应把跨模块判断、规格裁决和最终验收外包。

### `worker`

负责：

- 处理边界清楚、写集明确的实现任务
- 返回具体改动、原因和验证结果

适合：

- 单模块实现
- 单组测试补齐
- 明确的文档迁移

### `reviewer`

负责：

- 在已有 diff 和至少一条验证结果之后做二次审查

不适合：

- 从零理解整个项目
- 代替 root 做集成判断

### `explorer`

负责：

- 做短时、证据型审计
- 给出真实路径、漂移点和最小下一步

不适合：

- 长时间背景研究
- 宽口径开放式调研

## 3. 派单原则

一个 worker 任务必须至少明确：

- 目标
- 写集
- 禁止改动的区域
- 成功标准
- 必跑验证命令

如果这些信息不清楚，就不应该派单。

## 4. 当前推荐拓扑

默认优先：

- `root`
- `root + 1 worker`
- `root + 2 workers`

不要默认扩成大团队常驻协作。

## 5. 时间盒

- `explorer`
  - 5-10 分钟
- `reviewer`
  - 5-10 分钟
- `worker`
  - 20-40 分钟，超过后应拆小

超时没有有效产出时，root 应直接接管或重切任务。

## 6. 输出要求

worker / reviewer 的结果至少包含：

- 改了什么
- 为什么
- 跑了什么验证
- 哪些文件被改动

如果没有验证结果，不应宣称任务完成。
