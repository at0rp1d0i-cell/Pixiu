# Test Pipeline Refactor Implementation

Status: active
Owner: coordinator
Last Reviewed: 2026-03-20

Purpose: Break the Test Pipeline Refactor into executable slices with disjoint write sets and verification gates.

---

## Slice 0: Planning and Routing

- [x] 完成审计
- [x] 完成设计稿
- [x] 确立优先级：`Test Pipeline Refactor -> Epic B -> Epic C`

---

## Slice 1: Canonical Docs Alignment

Owner: coordinator

Write set:

- `docs/design/12_orchestrator.md`
- `docs/design/16_test-pipeline.md`
- `docs/design/22_stage-3-prefilter.md`
- `docs/design/24_stage-5-judgment.md`
- `docs/overview/05_spec-execution-audit.md`
- `docs/plans/current_implementation_plan.md`
- `docs/plans/2026-03-19-refactor-roadmap.md`
- `docs/plans/README.md`

Tasks:

1. 修正 `report -> human_gate` 的真实 runtime 描述
2. 修正 Stage 3 五段过滤链和 `prefilter_diagnostics`
3. 修正 Stage 5 `execution_succeeded` / warning-only execution error 语义
4. 修正测试层级、marker 规则、默认入口命令
5. 在 active plans 中明确 `Test Pipeline Refactor` 是 B/C 的前置 gate

Done when:

- 文档不再与当前 runtime/test reality 冲突

---

## Slice 2: Test Harness Stabilization

Owner: worker

Write set:

- `tests/conftest.py`
- `tests/integration/test_e2e_pipeline.py`
- `tests/integration/test_stage1_live.py`
- `tests/integration/test_stage2_live.py`
- `tests/integration/test_e2e_live.py`
- `tests/integration/test_stage1_market_context.py`
- 如需要，可新增 `tests/helpers/*.py`

Tasks:

1. 增加统一 orchestrator reset fixture
2. 清理 `sys.path.insert(...)`
3. 收口 import-time `.env` / skip 逻辑
4. 让 live/e2e marker 规则与文档目标一致
5. 重新归类过重 smoke/integration 测试

Done when:

- 测试基础设施不再明显依赖环境/全局状态偶然性

---

## Slice 3: Approval and Entrypoint Contract Tests

Owner: worker

Write set:

- 新增 `tests/test_orchestrator_entrypoints.py`
- `tests/test_orchestrator.py`
- `tests/test_state_store.py`
- `tests/test_cli_smoke.py`
- 如需要，可新增共享 stub 文件，但不得改动 Slice 2/4/5 的文件

Tasks:

1. 覆盖 `run_evolve()` / `run_single()` 的最终状态写回
2. 增加 approval full-path 测试：
   - enqueue
   - consume
   - route
   - snapshot/run status 清理
3. 加 CLI 成功/失败分支行为测试，而不只是 helper 调用

Done when:

- 审批链和 entrypoint contract 有稳定测试护栏

---

## Slice 4: FactorPool and Stage 5 Contract Tests

Owner: worker

Write set:

- 新增 `tests/test_factor_pool_write_paths.py`
- `tests/test_factor_pool.py`
- `tests/test_stage5.py`
- `tests/test_constraints.py`

Tasks:

1. 给 `register_factor()` 和 `register_factor_v2()` 补 parity tests
2. 覆盖 `execution_succeeded` 新语义
3. 覆盖 `EXECUTION_ERROR -> warning constraint`
4. 去掉会制造 false positive 的旧 stub/旧签名

Done when:

- FactorPool / Stage 5 的关键 contract 漂移会被测试直接打红

---

## Slice 5: Readiness and Downloader Branch Tests

Owner: worker

Write set:

- `tests/test_data_readiness.py`
- `tests/test_formula_capabilities.py`
- `tests/test_data_download_scripts.py`
- `tests/test_moneyflow_pipeline.py`
- `tests/test_stk_limit_pipeline.py`

Tasks:

1. 覆盖 `read_min_coverage_ratio()` 分支
2. 覆盖 `canonical_universe_dirs()` fallback
3. 覆盖 staged/materialized/runtime-ready 组合边界
4. 给 `moneyflow` / `stk_limit` 加与 `daily_basic` 对齐的 script-level progress/resume tests

Done when:

- Data capability / downloader 平台的关键分支被直接保护

---

## Verification Gates

每个 slice 至少通过与其写集对应的 targeted tests。

最终总验收：

```bash
uv run pytest -q tests -m "smoke or unit"
uv run pytest -q tests -m "integration and not live and not e2e"
uv run ruff check ...
git diff --check
```

必要时再加：

```bash
uv run pytest tests --collect-only -q -m live
uv run pytest tests --collect-only -q -m e2e
```

---

## Sequencing

推荐顺序：

1. Slice 1
2. Slice 2
3. Slice 3 / Slice 4 / Slice 5 可并行
4. 总体验证
5. 再进入 `FactorPool Boundary Refactor`
