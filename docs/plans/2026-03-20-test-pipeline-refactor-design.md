# Test Pipeline Refactor Design

Status: active
Owner: coordinator
Last Reviewed: 2026-03-20

Purpose: Define the scope, ordering, and guardrails for the Test Pipeline Refactor that must precede the next large runtime refactors.

---

## Why Now

Pixiu 的默认测试入口已经能稳定跑绿，但“测试体系可被信任”还没有完全成立。

当前最主要的问题不是测试数量不够，而是：

- 测试分层文档与真实 marker/入口不一致
- orchestrator / capability / env 仍存在顺序敏感风险
- 若干关键 contract 只被局部 smoke 覆盖，没有端到端 contract test
- 部分 integration test 实际已变成 contract-isolated pipeline test，但命名和分层还没跟上

如果不先收口测试体系，就会出现两个后果：

1. `FactorPool Boundary Refactor` 和 `Orchestrator Boundary Refactor` 没有可靠护栏
2. 开发者会继续把“组合跑失败”当成 runtime 红灯，浪费调试时间

因此 `Test Pipeline Refactor` 必须先于 `Epic B / Epic C`。

---

## Goals

这轮重构的目标不是追求覆盖率最大化，而是把测试系统变成后续重构可依赖的工程基础设施。

必须达成的结果：

1. 测试层级有唯一真相
2. `smoke / unit / integration / live / e2e` 的边界可执行，而不是停留在文档描述
3. 关键 contract 有真正的行为测试
4. 顺序敏感和环境污染风险明显下降
5. 文档、计划、代码中的测试口径保持一致

---

## Non-Goals

这轮不做：

- 不追求全仓库 test style 统一
- 不为每个模块补满覆盖率
- 不引入复杂 CI 编排
- 不把 `live/e2e` 变成默认 merge gate
- 不顺手重构业务 runtime，只修为测试可靠性服务的最小边界

---

## Refactor Waves

### Wave 1: Truth Alignment

先把“应该信什么”收口。

范围：

- `docs/design/12_orchestrator.md`
- `docs/design/16_test-pipeline.md`
- `docs/design/22_stage-3-prefilter.md`
- `docs/design/24_stage-5-judgment.md`
- `docs/overview/05_spec-execution-audit.md`
- `docs/plans/current_implementation_plan.md`
- `docs/plans/2026-03-19-refactor-roadmap.md`
- `docs/plans/README.md`

要回答清楚的关键问题：

1. `test_e2e_pipeline.py` 是 `integration` 还是 `e2e`
2. `live/e2e` 是否必须显式 marker
3. `conftest.py` 的自动补标是长期机制还是过渡兼容
4. 哪些 test file 其实是 contract-isolated，不该再叫 “real integration”

### Wave 2: Harness Stabilization

再把最容易制造假红灯的基础设施风险压掉。

范围：

- `tests/conftest.py`
- `tests/integration/test_e2e_pipeline.py`
- `tests/integration/test_stage1_live.py`
- `tests/integration/test_stage2_live.py`
- `tests/integration/test_e2e_live.py`
- `tests/integration/test_stage1_market_context.py`
- 如需要，可新增共享 test helper / fixture 文件

目标：

- 增加统一 orchestrator reset fixture
- 降低模块全局状态污染
- 去掉测试文件里的 `sys.path.insert(...)`
- 把 import-time `.env` / skip 决策移到更稳定的位置
- 禁止 unit test 裸读真实 runtime capability

### Wave 3: High-Value Contract Tests

最后补最值钱的测试，而不是机械加覆盖率。

优先级最高的新增/重构测试：

1. orchestrator entrypoint suite
2. approval full-path suite
3. FactorPool write-path parity suite
4. Stage 5 execution-error regression
5. readiness / downloader branch suite

---

## Test Taxonomy Decision

这轮先定一个明确口径：

- `contract-isolated pipeline test`
  - 允许用显式 stub / fake capability / fake pool
  - 目标是验证 stage contract 组合，而不是验证真实 local backend
- `local integration test`
  - 允许临时 SQLite / Chroma / filesystem
  - 但应尽量使用真实本地 runtime path，而不是 shadow contract

据此：

- `tests/integration/test_stage3_to_stage5.py`
  更接近 contract-isolated pipeline test
- `tests/integration/test_e2e_pipeline.py`
  应明确是否保留在 integration，还是拆分成更轻 smoke + 更重 local integration

---

## Acceptance Criteria

本 epic 完成的判据：

1. `16_test-pipeline.md` 与真实 marker/入口一致
2. `tests/conftest.py` 不再掩盖 tier 漏标
3. orchestrator reset 和 env isolation 有统一 fixture
4. approval full-path 测试存在且稳定
5. entrypoint / FactorPool write-path / readiness branches 至少各有一组新增 contract test
6. `smoke/unit` 与目标 integration 组合不再出现已知顺序敏感失败

---

## Dependency Impact

完成这轮后，后续优先级应调整为：

1. `Test Pipeline Refactor`
2. `FactorPool Boundary Refactor`
3. `Orchestrator Boundary Refactor`
4. `Data Capability Platform` 剩余平台化工作

也就是说，`Test Pipeline Refactor` 是 B/C 的前置 gate，而不是附属清理项。
