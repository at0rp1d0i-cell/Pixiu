# Docs Reorganization Design

## Context

Pixiu 的文档已经形成了几个明显问题：

- 文档数量多，但默认阅读路径不够明确
- `overview / design / plans / research / mirofish` 的角色边界对人类读者不够直观
- Phase 3 的重构已经改变了模块边界与代码入口，部分长文档仍残留旧路径、旧命令、旧兼容层叙事
- 当前文档更适合熟悉项目的人查资料，不够适合作为新读者的理解入口

用户已确认本次整编的目标是采用“双层结构”：

- 上层极简，服务人类快速理解项目
- 下层详细，服务实现、审计和 AI agent

同时，用户要求由主代理作为唯一接口与其对接，细项可派子代理并行完成。

## Goals

1. 为人类建立稳定、低认知负担的默认阅读路径
2. 保留足够细的设计与计划文档，支持实现和审计
3. 建立长期有效的文档规范，避免后续再次无序增长
4. 将“当前真相 / 当前设计 / 执行计划 / 前瞻路线 / 历史归档”彻底分层

## Non-Goals

- 本次不重写整个项目的技术设计
- 本次不为了追求目录完美而重命名所有文件
- 本次不把所有历史文档都清空；有价值但非当前主路径的内容应迁移，不应粗暴删除

## Target Information Architecture

### Layer A: Human-first Reading Path

这一层只解决五个问题：

1. Pixiu 是什么
2. Pixiu 不是什么
3. 现在做到哪了
4. 代码入口在哪
5. 接下来应该读哪篇

建议默认阅读路径：

1. `docs/README.md`
2. `docs/overview/01_project-snapshot.md`
3. `docs/overview/02_codebase-map.md`
4. `docs/overview/03_architecture-overview.md`
5. `docs/overview/04_current-state.md`
6. `docs/overview/05_spec-execution-audit.md`
7. 某篇 `docs/design/xx_*.md`

### Layer B: Implementation and Maintenance Layer

- `docs/design/`
  - 仅保留“当前有效设计”
  - 每篇文档只讲一个主题
  - 不再混入长篇迁移说明和历史争论
- `docs/plans/`
  - 仅保留仍在指导当前工作的计划
  - 完成或失效后立即归档
- `docs/futures/`
  - 放前瞻但非当前运行时的设计
  - 例如 Dashboard、Reflection、Bootstrap、Generalization、Commercialization 等
- `docs/research/`
  - 历史背景与讨论
- `docs/reference/`
  - 外部参考和长期复用资料
- `docs/archive/`
  - 完成/失效计划、旧规范、兼容层说明、历史报告

## Numbering Strategy

### Why Numbering

用户希望人类可以按顺序阅读。编号是有效手段，但必须节制使用，否则会制造额外维护成本。

### Where to Number

- `docs/README.md`
  - 不编号，保持稳定入口
- `docs/overview/`
  - 编号，按默认阅读顺序排列
- `docs/design/`
  - 编号，按“基础设计 -> Stage 设计 -> 其他扩展”的阅读顺序排列
- `docs/plans/`
  - 保持日期前缀，不改编号化
- `docs/futures/`
  - 可使用宽间距编号，例如 `10_`, `20_`, `30_`

### Numbering Style

- 使用 `01_`, `02_`, `03_` 这类两位数编号
- 设计层建议使用分段留白，例如：
  - `10_` 基础系统
  - `20_` Stage 设计
  - `30_` 产品与组织
  - `40_` 扩展主题

示例：

- `docs/overview/01_project-snapshot.md`
- `docs/overview/02_codebase-map.md`
- `docs/overview/03_architecture-overview.md`
- `docs/overview/04_current-state.md`
- `docs/overview/05_spec-execution-audit.md`

- `docs/design/10_authority-model.md`
- `docs/design/11_interface-contracts.md`
- `docs/design/12_orchestrator.md`
- `docs/design/13_control-plane.md`
- `docs/design/14_factor-pool.md`
- `docs/design/15_data-sources.md`
- `docs/design/16_test-pipeline.md`
- `docs/design/20_stage-1-market-context.md`
- `docs/design/21_stage-2-hypothesis-expansion.md`
- `docs/design/22_stage-3-prefilter.md`
- `docs/design/23_stage-4-execution.md`
- `docs/design/24_stage-5-judgment.md`
- `docs/design/25_stage-45-golden-path.md`

## Documentation Standard as First-class Output

本次整编不只要改结构，还要产出一份长期有效的文档规范：

- 目标路径：`docs/00_documentation-standard.md`
- 作用：为后续所有文档建立统一的目录职责、文档级别、命名、头部元信息、生命周期、拆分规则和引用规范

该规范应至少覆盖：

1. 目录职责
2. 文档级别定义
3. 命名规范
4. 文档头部规范
5. 内容边界
6. 生命周期与归档规则
7. 链接与引用规范
8. 长度与拆分规则

## Canonical Metadata Header

每篇 canonical 文档建议统一加一个简短头部块，帮助读者快速判断是否值得信任与细读：

- `Purpose`
- `Status`
- `Audience`
- `Canonical`
- `Owner`
- `Last Reviewed`

建议约束：

- `overview/` 与 `design/` 中的 canonical 文档必须有该头部
- `plans/` 可选，但建议至少标注 `Status` 和 `Owner`

## Content Boundary Rules

### `overview`

- 只写项目定义、当前状态、阅读顺序、代码导航
- 不承载大段实现细节
- 不承载实验方案和迁移细节

### `design`

- 只写当前有效设计
- 允许解释当前实现边界，但不堆历史过程
- 如果代码与设计不一致，偏差先记入 `05_spec-execution-audit.md`

### `plans`

- 只写仍在执行或即将执行的计划
- 计划完成、前提失效、被重构吸收后，移动到 `docs/archive/plans/`

### `futures`

- 只放未来方向
- 不能再被误当成当前运行时设计

### `research`

- 只保留背景价值和历史判断
- 不是当前真相

## Scope of This Reorganization

### New or Reshaped Artifacts

- 新增 `docs/00_documentation-standard.md`
- 重写 `docs/README.md`
- 新增 `docs/overview/02_codebase-map.md`
- 新增 `docs/overview/04_current-state.md`
- 编号化 `docs/overview/`
- 编号化 `docs/design/`
- 新建 `docs/futures/`

### Main Cleanup Targets

- 修正 `docs/design/` 与 `docs/plans/` 中残留的旧路径、旧命令、旧模块引用
- 清理被 Phase 3 重构淘汰的 compat/shim 叙事
- 把不再适合作为当前设计的前瞻文档移出 `docs/design/`
- 把完成或失效的计划移出 `docs/plans/`

## Migration Principles

1. 先建新骨架，再迁移旧文档
2. 每一步都保持主路径可读，不做长时间失效的大搬家
3. 旧路径引用必须同步修复，避免读者掉入死链
4. 当前真相优先于完美分类；遇到冲突，以 `docs/overview/05_spec-execution-audit.md` 为准

## Collaboration Model

- 用户只与主代理对接
- 子代理用于并行完成细节探索、局部清理和交叉核对
- 架构边界、目录治理、最终验收由主代理负责

## Acceptance Criteria

整编完成后，应满足：

1. 新读者可在 15-30 分钟内理解项目定义、当前状态和代码入口
2. `docs/README.md` 能清晰给出默认阅读路径
3. `docs/design/` 不再混入明显的未来路线或已失效计划
4. `docs/plans/` 中只保留仍在指导当前工作的文档
5. 每篇 canonical 文档开头可快速判断用途、状态、受众和可信度
6. 默认阅读路径中的文档不再残留已删除的主入口路径或显著过期命令

## Recommended Execution Order

1. 写出文档规范 `docs/00_documentation-standard.md`
2. 重建 `docs/README.md` 和 `docs/overview/` 主路径
3. 为 `docs/design/` 重新编号并修正主干漂移
4. 新建 `docs/futures/` 并迁移前瞻文档
5. 精简 `docs/plans/`
6. 全量修复文档间链接与代码路径引用
7. 做一轮机械校验与人工抽读
