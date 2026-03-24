# Experiment Harness Design

Status: active
Owner: coordinator
Last Reviewed: 2026-03-23

Purpose: Define a single, script-based experiment harness that turns Pixiu's preflight discipline into an executable workflow.

---

## Why Now

Pixiu 当前最大的问题不是“不能跑命令”，而是实验入口缺少唯一 discipline。

目前的真实问题是：

- `doctor`、`pytest`、`single`、`evolve` 之间没有一个固定顺序
- 开发者可以直接跳到长轮次实验，绕过最小 preflight
- 环境真相（如 `QLIB_DATA_DIR`、`TUSHARE_TOKEN`）仍然依赖个人记忆
- 实验失败后，往往分不清是环境红灯、运行时红灯，还是实验本体失败

因此这轮不做新的产品入口，而是先建立一个可靠的 experiment harness。

---

## Goals

必须达成的结果：

1. 实验有唯一默认入口
2. preflight discipline 变成可执行脚本，而不是口头约定
3. 实验 profile 进入一个最小设置层
4. 默认流程不允许跳过 `doctor(core) -> single -> evolve 2 rounds`
5. 长轮次实验必须显式开启

---

## Non-Goals

这轮不做：

- 不把 harness 做进 CLI
- 不新增产品层设置系统
- 不引入复杂 dashboard
- 不顺手扩写大量文档
- 不把所有实验参数都抽象成通用配置平台

---

## Chosen Shape

采用 `scripts + JSON profile`：

- `scripts/experiment_preflight.py`
- `scripts/run_experiment_harness.py`
- `config/experiments/default.json`

理由：

- 比 shell/Make 更适合表达结构化结果和失败阶段
- 比 CLI 更稳定，且不依赖当前 CLI 成熟度
- 以后 App 接管时，这层仍可保留为底层 harness

---

## Flow

默认执行顺序固定为：

1. 读取 profile
2. 校验环境真相
3. 运行 `doctor --mode core`
4. 若 blocking fail，直接停止
5. 运行 `single`
6. 运行 `evolve 2 rounds`
7. 只有显式 `--long-run` 才继续长轮次

第一版先不允许自由重排步骤。

---

## Profile Boundary

`config/experiments/default.json` 第一版只承载 experiment discipline 所需设置：

- `doctor_mode`
- `single_island`
- `preflight_evolve_rounds`
- `long_run_rounds`
- `require_reset_clean`
- `qlib_data_dir`
- `report_every_n_rounds`
- `max_rounds_env_override_allowed`

这是一层“实验设置”，不是通用产品设置。

---

## Red-light Rules

以下情况视为红灯，必须停止：

- `doctor(core)` 出现 blocking fail
- `QLIB_DATA_DIR` 缺失或 runtime readiness 不通过
- `single` 运行失败
- `evolve 2 rounds` 任一轮失败
- Stage 1 进入 blocking timeout / degraded 状态

---

## Output Contract

第一版只做最小结构化摘要：

- profile 信息
- preflight 结论
- `single` 结果
- `evolve 2 rounds` 结果
- 是否进入 long run
- 若失败，明确失败阶段与下一步建议

stdout 输出短摘要，详细结果进入现有 experiment artifacts / runs 路径。

---

## Testing Strategy

第一版只补高价值 contract tests：

1. profile 解析
2. preflight 阻断逻辑
3. long-run 需要显式开启
4. 某一步失败后不再继续后续步骤
5. script entrypoint 可导入
6. harness 对 orchestrator entrypoint 的调用顺序正确

---

## Acceptance

完成标准：

1. 开发者不再需要手工拼接实验命令
2. `config/experiments/default.json` 可直接驱动默认 preflight
3. harness 能稳定执行 `doctor(core) -> single -> evolve 2 rounds`
4. 关键阻断逻辑有测试保护
