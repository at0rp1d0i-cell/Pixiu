# Pixiu v2 测试管线规格
Purpose: Define the default test entrypoints, test layers, and merge-gate expectations.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-19

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
- `tests/test_formula_capabilities.py`
- `tests/test_cli_smoke.py`

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
- `StateStore` / CLI 的最小联通 smoke

### Tier C: Local Integration

目标：验证本地集成链路，但外部依赖必须被隔离或 mock。

要求：
- 可依赖本地 filesystem
- 可依赖临时 ChromaDB / SQLite / Docker mock
- 不依赖互联网和真实交易数据源

典型覆盖：
- `tests/test_factor_pool.py`
- `tests/test_state_store.py`
- `tests/test_orchestrator.py`
- `tests/test_script_entrypoints.py`
- CLI / API 的最小接口联通

### Tier D: Live Integration

目标：验证外部数据源、MCP Server、真实 API 或实时数据联通。

要求：
- 显式标记为 `live`
- 不纳入默认 merge gate
- 失败优先视为环境或上游依赖问题，不直接阻塞普通开发

典型覆盖：
- `tests/test_mcp_servers.py` 中的 AKShare / cross-market 段落
- `tests/integration/test_stage1_live.py`
- `tests/integration/test_stage2_live.py`
- `tests/integration/test_e2e_live.py`

### Tier E: End-to-End

目标：验证 orchestrator 主流程、Qlib 数据、Docker 执行和 FactorPool 写入的完整闭环。

要求：
- 显式标记为 `e2e`
- 需要真实环境（Qlib 数据、Docker 镜像、必要 env）
- 只在专门时段或手动触发执行

典型覆盖：
- `tests/integration/test_e2e_pipeline.py`
- `tests/integration/test_e2e_live.py`

---

## 3. 目录和命名规则

- 正式测试统一放在 `tests/`。
- 实验脚本统一放在 `experiments/`、`sandbox_workspace/` 或 `scripts/`，不得放在仓库根目录下以 `test_*.py` 命名。
- 任何会在 import 阶段执行 `sys.exit()`、真实网络请求或长时间任务的文件，不得进入默认 pytest 收集路径。

当前已知违规项：
- 旧实验脚本已经迁出默认测试入口；`tests/` 下的测试文件都应保持可被默认 `pytest` 发现。

---

## 4. 测试基础设施要求

### Python Path

项目必须保证测试入口无需手动注入路径。目标状态：

- 在 `pyproject.toml` 或 `pytest.ini` 中配置项目根路径
- 运行 `pytest tests` 时可直接导入 `src.*`

当前状态：

```bash
uv run pytest -q tests -m "smoke or unit"
```

### Async 测试

长期目标仍然是统一 async 测试策略，但当前仓库已经把关键路径测试收敛成“同步包装 async 逻辑”的方式，并且少量边界测试仍保留原生 async。

当前状态：
- pytest 配置中已注册 `asyncio` marker
- `pytest-asyncio` 已安装
- 默认绿色入口继续以同步包装为主，不要求所有新测试改成 async

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
- 当前 CLI/API 最小实现（`src/cli/main.py`, `src/api/server.py`）应至少有 import 和接口 smoke 测试；当前对应覆盖已落在 `tests/test_cli_smoke.py`、`tests/test_state_store.py` 与 `tests/test_script_entrypoints.py`。

---

## 8. 当前缺口

截至 2026-03-19，仓库仍存在以下问题：

- `live / e2e` 仍缺少稳定环境说明和自动化触发策略，默认 merge gate 继续排除这两层
- async 测试的长期方案尚未定稿，当前是同步包装与少量原生 async 并存
- 默认 `smoke or unit` 基线当前为 `511 passed, 26 deselected`
- CLI / API 的最小联通 smoke 已补齐；后续重点是保持 approval / report / human-gate 路径与真实 graph 路由一致

本规格的目标，就是把这些问题从“口头约定”提升为明确的工程约束。
