# Interface Readiness Audit

> 日期：2026-03-09
> 目的：在正式启动 Pixiu MVP 管线前，建立一份真实的外部接口审计基线。

---

## 结论

Pixiu 现在已经不是“没有主链”，但也还不是“所有接口都已接好即可开跑”。

当前真实情况是：

- Stage 4→5 最小闭环已可运行
- 最小 control-plane `state_store` 已落地
- 但外部接口面仍需要逐项核验

特别要澄清的一点：

- 当前 LLM 不是统一通过 skills / MCP 驱动
- 当前主 LLM 运行方式是直接走 OpenAI-compatible API
- MCP 目前是局部工具层，不是统一运行时能力层
- skills 目前主要是本地约束文档，不是所有 agent 的现役注入层

---

## 1. LLM Interface Audit

### 当前真实接入

主要代码入口：

- `src/agents/researcher.py`
- `src/agents/market_analyst.py`
- `src/agents/prefilter.py`
- `src/execution/exploration_agent.py`

当前主要读取：

- `RESEARCHER_MODEL`
- `RESEARCHER_BASE_URL`
- `RESEARCHER_API_KEY`

部分代码路径额外回退到：

- `OPENAI_MODEL`
- `OPENAI_API_BASE`
- `OPENAI_API_KEY`

### 结论

- 当前主 LLM 接口是 OpenAI-compatible provider 模式
- 不是统一走 MCP
- 也不是统一通过 SkillLoader 完成 runtime prompt 注入

### 启动前检查项

- `RESEARCHER_BASE_URL` 是否可连通
- `RESEARCHER_API_KEY` 是否有效
- `RESEARCHER_MODEL` 是否与 provider 匹配
- 失败时是否会中断关键路径，还是可降级

---

## 2. MCP Interface Audit

### 当前真实接入

主要入口：

- `src/agents/market_analyst.py`

当前通过 `langchain_mcp_adapters` 启动：

- `mcp_servers/akshare_server.py`

### 结论

- MCP 目前主要服务 Stage 1 市场上下文
- 不是整个 Pixiu 的统一工具总线
- MCP 失败时当前有降级到空 `MarketContextMemo` 的策略

### 启动前检查项

- `akshare_server.py` 是否能本地启动
- Stage 1 工具调用是否能返回非空数据
- MCP 失败时 orchestrator 是否能继续降级运行

---

## 3. Skills Audit

### 当前真实接入

主要文件：

- `src/skills/loader.py`
- `src/agents/researcher.py`

### 结论

- skills 目前主要是本地文档约束层
- `SkillLoader` 已存在
- 但当前 runtime 并未证明所有关键 agent 都把 skill context 注入到实际 prompt 中

### 启动前检查项

- `knowledge/skills/` 中必要文档是否齐全
- `Researcher / Coder / Critic` 的 skill context 是否真的进入 prompt
- 如果没有，则在 MVP 启动时不应高估 skills 的实际赋能程度

---

## 4. Data Interface Audit

### Layer 1: Qlib 回测层

来源：

- 本地 `data/qlib_bin/`
- `src/data_pipeline/data_downloader.py`
- `src/data_pipeline/format_to_qlib.py`

### Layer 2: 实时市场上下文

来源：

- AKShare MCP

### Layer 3: 基本面扩展

状态：

- 规格已写
- 当前仍属于 planned / optional
- 依赖 `TUSHARE_TOKEN`

### Layer 4: 新闻 / 情绪

状态：

- 规格已写
- 当前仍属于 planned / optional
- 依赖 `TAVILY_API_KEY`

### 启动前检查项

- `data/qlib_bin/` 是否完整
- Docker 容器里是否能挂载并读取该目录
- AKShare MCP 当前工具是否真可返回数据
- Tushare / Tavily 在 MVP 首跑时是否必须；如果不是，文档要明确是 optional

---

## 5. Execution Interface Audit

主要入口：

- `src/execution/coder.py`
- `src/execution/docker_runner.py`
- `src/execution/templates/qlib_backtest.py.tpl`

依赖：

- Docker
- `Pixiu-coder:latest`
- repo-local `data/qlib_bin`

### 启动前检查项

- Docker 是否可调用
- `Pixiu-coder:latest` 镜像是否存在
- 容器内 `/data/qlib_bin` 是否有数据
- 是否能稳定输出 `BACKTEST_RESULT_JSON`

---

## 6. Control Plane Audit

主要入口：

- `src/control_plane/state_store.py`
- `src/core/orchestrator.py`
- `src/api/server.py`
- `src/cli/main.py`

### 当前已具备

- `RunRecord`
- `RunSnapshot`
- `ArtifactRecord`
- `HumanDecisionRecord`

### 启动前检查项

- `PIXIU_STATE_STORE_PATH` 是否可写
- 报告落盘目录是否可写
- CLI/API 是否优先读 control-plane，而不是伪造状态

---

## 7. Human Gate Audit

当前入口：

- `pixiu approve`
- `pixiu redirect`
- `pixiu stop`
- `/api/approve`

### 启动前检查项

- decision 是否进入 LangGraph checkpoint
- decision 是否写入 `state_store`
- 审批失败时是否能明确报错

---

## 8. 当前环境变量真相

当前代码真实需要优先维护的是：

- `RESEARCHER_MODEL`
- `RESEARCHER_BASE_URL`
- `RESEARCHER_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_API_BASE`
- `OPENAI_API_KEY`
- `MAX_ROUNDS`
- `ACTIVE_ISLANDS`
- `REPORT_EVERY_N_ROUNDS`
- `MAX_CONCURRENT_BACKTESTS`
- `PIXIU_STATE_STORE_PATH`
- `FUNDAMENTAL_FIELDS_ENABLED`

当前属于 planned / optional：

- `TUSHARE_TOKEN`
- `TAVILY_API_KEY`
- `ANTHROPIC_BASE_URL`
- `ANTHROPIC_API_KEY`

---

## 9. 正式开跑前的最小检查清单

1. LLM provider 连通
2. AKShare MCP 可启动且能返回数据
3. Docker 与 `Pixiu-coder:latest` 可用
4. `data/qlib_bin/` 可挂载且可回测
5. `state_store` 可写
6. `pixiu status` 和 `pixiu report` 能读到 control-plane 数据
7. 跑通一次真实 single-mode MVP 管线

---

## 10. 当前判断

Pixiu 已经接近“可启动内部 MVP 管线”，但在正式开跑前，必须先把 env 文档、接口清单和真实环境核验统一起来。

这一步的重点不是继续写 agent，而是确保：

- 文档描述的接口就是代码真实依赖的接口
- 启动命令不会再把人带到过时配置上
- 可选接口和必需接口被严格区分
