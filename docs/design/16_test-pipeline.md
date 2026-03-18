# Pixiu v2 测试管线规格
Purpose: Define the default test entrypoints, test layers, and merge-gate expectations.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-18

> 创建：2026-03-09
> 前置依赖：`.../overview/03_architecture-overview.md`、`11_interface-contracts.md`
> 目的：定义统一的测试分层、运行命令、依赖前提和 merge gate，避免“测试文件存在，但没有稳定测试管线”。

---

## 1. 设计原则

1. 测试必须分层，不能把纯单测、外部数据测试和端到端实验混在一个入口下。
2. 默认开发入口必须是稳定、可重复的本地测试命令。
3. 任何依赖网络、真实 LLM、真实 AKShare、真实 Docker/Qlib 的测试，都不得作为默认 merge gate。
4. 实验脚本不是测试，不能让 `pytest` 默认收集到它们。

---

## 2. 测试分层

### Tier A: Smoke

目标：验证基础导入、schema 构造和最小纯逻辑。

要求：
- 不访问网络
- 不启动 Docker
- 不依赖真实 Qlib 数据
- 运行时间 < 30 秒

典型覆盖：
- `tests/test_schemas.py`
- `tests/test_prefilter.py` 中纯逻辑部分
- `tests/test_stage2_batch.py` 中 mock 驱动的生成逻辑

### Tier B: Unit

目标：验证单模块业务逻辑，允许使用 mock 和临时目录。

要求：
- 不访问网络
- 不依赖真实 LLM 返回
- 可以使用临时文件和假数据

典型覆盖：
- `SkillLoader`
- `Critic` 的解析/判定逻辑
- `ExplorationAgent` 的脚本提取逻辑
- `FactorPool` 的格式化和过滤逻辑

### Tier C: Local Integration

目标：验证本地集成链路，但外部依赖必须被隔离或 mock。

要求：
- 可依赖本地 filesystem
- 可依赖临时 ChromaDB / SQLite / Docker mock
- 不依赖互联网和真实交易数据源

典型覆盖：
- `tests/test_execution.py`
- `tests/test_factor_pool.py`
- `tests/test_state_store.py`
- `tests/test_orchestrator_state_store.py`
- `tests/test_api_state_store.py`
- CLI / API 的最小接口联通

### Tier D: Live Integration

目标：验证外部数据源、MCP Server、真实 API 或实时数据联通。

要求：
- 显式标记为 `live`
- 不纳入默认 merge gate
- 失败优先视为环境或上游依赖问题，不直接阻塞普通开发

典型覆盖：
- `tests/test_akshare_mcp.py`

### Tier E: End-to-End

目标：验证 orchestrator 主流程、Qlib 数据、Docker 执行和 FactorPool 写入的完整闭环。

要求：
- 显式标记为 `e2e`
- 需要真实环境（Qlib 数据、Docker 镜像、必要 env）
- 只在专门时段或手动触发执行

---

## 3. 目录和命名规则

- 正式测试统一放在 `tests/`。
- 实验脚本统一放在 `experiments/`、`sandbox_workspace/` 或 `scripts/`，不得放在仓库根目录下以 `test_*.py` 命名。
- 任何会在 import 阶段执行 `sys.exit()`、真实网络请求或长时间任务的文件，不得进入默认 pytest 收集路径。

当前已知违规项：
- 仓库根的 `test_experiment_4.py` 不是测试，而是实验脚本，后续实现应迁出默认测试入口。

---

## 4. 测试基础设施要求

### Python Path

项目必须保证测试入口无需手动注入路径。目标状态：

- 在 `pyproject.toml` 或 `pytest.ini` 中配置项目根路径
- 运行 `pytest tests` 时可直接导入 `src.*`

当前状态：

```bash
pytest ...
```

### Async 测试

长期目标仍然是统一 async 测试策略，但当前仓库已经把关键路径测试收敛成“同步包装 async 逻辑”的方式，因此默认绿色入口暂时不依赖 `pytest-asyncio`。

当前状态：
- pytest 配置中已注册 `asyncio` marker
- `tests/test_execution.py` 已改为同步包装，不再阻塞默认测试入口

后续二选一：
- 正式引入 `pytest-asyncio`，统一回到原生 async 测试
- 继续维持“同步包装 + 少量 async 边界”的策略，并避免扩散 `@pytest.mark.asyncio`

### Marker 体系

必须统一注册以下 markers：

- `smoke`
- `unit`
- `integration`
- `live`
- `e2e`

如果测试没有 marker，不允许进入长期稳定 CI。

---

## 5. 规范化命令

### 默认开发命令

```bash
pytest -q tests -m "smoke or unit"
```

### 本地集成

```bash
pytest -q tests -m "integration and not live and not e2e"
```

### Live 数据联通

```bash
pytest -q tests -m live
```

### 端到端闭环

```bash
pytest -q tests -m e2e
```

当前仓库已经完成 pytest 路径和 marker 基础配置，可以把上述命令视为稳定入口；但 `live / e2e` 仍不属于默认 merge gate。

---

## 6. Merge Gate

合并请求的最低要求：

1. 通过 `smoke + unit`
2. 对被改动模块补上对应层级测试
3. 如果触及 `execution / factor_pool / orchestrator`，至少跑一组 `integration`

不作为默认阻塞项：

- `live`
- `e2e`

这些测试应由专门环境或手动触发承担。

---

## 7. 规格到测试的映射要求

- 每篇 active 规格都必须至少对应一组 `smoke / unit / integration` 中的一个测试入口。
- `11_interface-contracts.md` 必须映射到 schema 测试。
- `22_stage-3-prefilter.md` 必须映射到 prefilter 测试。
- `23_stage-4-execution.md` 必须映射到 execution 测试。
- `24_stage-5-judgment.md` 必须映射到 judgment 测试。
- 当前 CLI/API 最小实现（`src/cli/main.py`, `src/api/server.py`）必须至少有 import 和接口 smoke 测试。

---

## 8. 当前缺口

截至 2026-03-09，仓库仍存在以下问题：

- `live / e2e` 仍缺少稳定环境说明和自动化触发策略
- async 测试的长期方案尚未定稿，当前是同步包装而不是统一插件方案
- `FactorPool` 的 persistent backend 在部分环境下仍不稳定，本地 integration 依赖 in-memory fallback
- 仓库根仍保留实验脚本 `test_experiment_4.py`，虽然已被 `testpaths = ["tests"]` 隔离出默认收集路径，但后续仍应迁入 `experiments/`

本规格的目标，就是把这些问题从“口头约定”提升为明确的工程约束。
