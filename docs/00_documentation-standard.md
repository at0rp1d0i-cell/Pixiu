# Documentation Standard

Purpose: Define the Pixiu docs system, document levels, naming rules, metadata headers, and archive lifecycle.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-23

## 1. Design Goal

Pixiu 的文档系统采用双层结构：

- 上层服务人类快速理解项目
- 下层服务实现、审计和长期维护

默认目标不是“把所有信息都放到入口”，而是“让读者知道先看什么、什么时候该停、什么时候该继续下钻”。

## 2. Directory Roles

### `docs/`

仓库级文档入口。负责定义文档系统，而不是承载具体模块设计。

### `docs/overview/`

`L1` 项目级真相与阅读入口。

只回答：

- 项目是什么
- 现在做到哪了
- 代码入口在哪
- 下一篇该读什么

### `docs/design/`

`L2` 当前有效设计。

只放当前主干仍然成立、可直接指导实现的设计文档。每篇文档只讲一个主题。

### `docs/plans/`

`L3` 会变化的执行文档。

包括：

- 当前执行计划
- 仍在推进的专题计划
- 当前工程债

### `docs/futures/`

`L4` 前瞻设计。

放未来方向、尚未进入当前运行时的系统设计。可以被阅读，但不能被误当作当前实现真相。

### `docs/reference/`

`L4` 外部参考资料与长期可复用背景材料。

### `docs/research/`

`L4` 历史讨论、推理过程和研究背景。

### `docs/archive/`

`L5` 历史归档。

包括：

- 已完成或失效的计划
- 被替代的旧设计
- 兼容层说明
- 阶段报告

## 3. Document Levels

| Level | 目录 | 含义 | 默认受众 |
|---|---|---|---|
| `L1` | `overview/` | 项目级真相、导航、当前状态 | human |
| `L2` | `design/` | 当前有效设计 | both |
| `L3` | `plans/` | 当前执行计划与工程债 | implementer |
| `L4` | `futures/`, `reference/`, `research/` | 前瞻、参考、背景 | implementer |
| `L5` | `archive/` | 历史归档 | implementer |

## 4. Naming Rules

### Root

- `docs/README.md` 保持不变，作为统一入口
- `docs/00_documentation-standard.md` 作为文档系统总规范

### `overview/`

- 必须编号
- 使用 `01_`, `02_`, `03_` 这种两位数顺序
- 文件名反映阅读顺序，不反映实现时间

### `design/`

- 建议编号
- 使用宽间距段号，方便后续插入
- 推荐：
  - `10_` 基础系统
  - `20_` Stage 设计
  - `30_` 团队与产品

### `plans/`

- 使用日期前缀
- 不编号
- 时间语义比阅读顺序更重要

### `futures/`

- 可编号，但只在需要建立阅读顺序时使用

### Numbering Scope Rule

- 编号语义只在**同一目录内**有效。
- 不允许把不同目录下的编号拼成一条全局阅读链。
- 跨目录阅读路径必须由目录入口文档（如 `docs/README.md`、各子目录 `README.md`）显式声明。

## 5. Canonical Metadata Header

所有 canonical 文档都应在开头带一个短元信息块：

- `Purpose`
- `Status`
- `Audience`
- `Canonical`
- `Owner`
- `Last Reviewed`

推荐模板：

```md
Purpose: ...
Status: active
Audience: both
Canonical: yes
Owner: ...
Last Reviewed: YYYY-MM-DD
```

约束：

- `overview/` 中的文档必须带该头部
- `design/` 中的 active 文档必须带该头部
- `plans/` 可简化，但建议至少标明 `Status`、`Owner`

## 6. Content Boundary Rules

### `overview`

- 只写项目边界、当前状态、导航、代码地图
- 不堆实现细节
- 不混入实验计划和迁移日志

### `design`

- 只写当前有效设计
- 不承载大段历史过程
- 设计与实现的偏差统一记录到 `docs/overview/05_spec-execution-audit.md`

### `plans`

- 只保留仍在执行或即将执行的计划
- 完成或失效后移动到 `docs/archive/plans/`

### `futures`

- 只放未来方向
- 必须明确不是当前运行时真相

### `research`

- 解释历史判断与推理过程
- 不作为当前实现依据

## 7. Lifecycle Rules

### Update

以下情况必须更新文档：

- 主模块入口变更
- canonical schema 或 Stage 边界变更
- 设计与实现关系发生前移、后移或漂移
- 当前默认命令发生变化

### Archive

以下情况应归档，而不是继续留在主路径：

- 计划已完成
- 设计已被新设计替代
- 文档只剩追溯价值
- 文档主要描述已删除的 compat 层

### Split

文档达到以下任一条件，应考虑拆分：

- 超过约 `250-300` 行且承担多个角色
- 同时混有当前真相、迁移说明、未来方案
- 新读者无法快速判断“哪些段落对当前版本有效”

## 8. Link and Reference Rules

- 引用代码路径时，使用仓库内真实路径
- 引用命令时，优先写当前实际可用命令
- 如果某路径尚未存在，必须明确标为 `planned` 或 `future`
- 兼容说明可以保留旧路径，但不能把旧路径包装成当前入口

## 9. Trust Order

当多个文档口径冲突时，默认信任顺序为：

1. 当前代码
2. `docs/overview/05_spec-execution-audit.md`
3. `docs/overview/*.md`
4. `docs/design/*.md`
5. `docs/plans/*.md`
6. `docs/futures/`, `docs/research/`, `docs/reference/`
7. `docs/archive/`

## 10. Human-first Rule

任何新文档都不应破坏这条默认阅读路径：

1. `docs/README.md`
2. `docs/overview/01_project-snapshot.md`
3. `docs/overview/02_codebase-map.md`
4. `docs/overview/03_architecture-overview.md`
5. `docs/overview/04_current-state.md`
6. `docs/overview/05_spec-execution-audit.md`

如果一篇新文档会让读者更难判断“先看哪篇”，它就需要改名、改位置或改级别。
