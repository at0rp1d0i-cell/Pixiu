Purpose: Record deliberate runtime concessions, experiment-specific degradations, and deferred implementations that are still accepted in the current Pixiu mainline.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-23

# Runtime Concessions

这份文档记录当前主线里**被明确接受**的运行时让步。

它只回答三件事：

- 现在有哪些能力是故意降级、缩小或延期实现的
- 为什么当前阶段接受这些让步
- 什么条件下必须拆掉它们

它**不**负责：

- 记录所有设计与实现漂移
- 记录所有工程债
- 记录具体实现过程

设计与实现是否一致，请看 [05_spec-execution-audit.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/05_spec-execution-audit.md)。

## 1. 使用规则

### 1.1 和 `05_spec-execution-audit.md` 的区别

- `05_spec-execution-audit.md`
  - 关注设计文档与代码主干是否对齐
  - 结论口径是 `active / implemented/partial / planned / exploratory / archive`
- `06_runtime-concessions.md`
  - 关注当前运行时为了推进实验或控制复杂度，**故意接受**了哪些让步
  - 结论口径是 `active / agreed / resolved`

两者可以互相引用，但不应互相替代。

### 1.2 什么应记在这里

以下内容应该进入本账本：

- 为了让实验先跑起来而接受的降级
- 为了控制复杂度而保留的 MVP 简化
- 仍在主路径里的 compat bridge
- 已经达成设计共识、但明确延期实现的运行时能力

以下内容不应该进入本账本：

- 一般性工程债
- 已完全退出主路径的历史兼容层
- 只存在于 futures/research 的前瞻设想

### 1.3 字段约定

每条记录固定包含：

- `ID`
- `Type`
- `Status`
- `Scope`
- `Current Behavior`
- `Why It Exists`
- `Risk If Kept`
- `Removal Trigger`
- `Related Settings`
- `Evidence`

其中：

- `Type`
  - `experiment_concession`
  - `mvp_simplification`
  - `compat_bridge`
  - `deferred`
- `Status`
  - `active`
  - `agreed`
  - `resolved`

## 2. 当前仍生效的让步

### EXP-001

- `Type`: `experiment_concession`
- `Status`: `active`
- `Scope`: `Stage 1 market context`
- `Current Behavior`:
  - Stage 1 按 `blocking core + async enrichment` 运行
  - `async enrichment` 不做同轮 late merge，只影响下一轮
  - 同日、非 degraded 的 `market_context` 会在 round 0 之后被复用，避免重复慢 MCP
- `Why It Exists`:
  - 当前 Stage 1 数据面和工具面还不够稳定
  - 先保证实验入口可跑、blocking red light 语义清楚
- `Risk If Kept`:
  - 上下文密度受限
  - 同日缓存会削弱“每轮都拿到全新上下文”的真实性
- `Removal Trigger`:
  - blocking core 足够稳定
  - enrichment 的角色与注入方式进一步收口
  - fast feedback / controlled run 的 context policy 正式进入设置层
- `Related Settings`:
  - `config/experiments/default.json`
- `Evidence`:
  - [20_stage-1-market-context.md](/home/torpedo/Workspace/ML/Pixiu/docs/design/20_stage-1-market-context.md)
  - [stage1.py](/home/torpedo/Workspace/ML/Pixiu/src/core/orchestrator/nodes/stage1.py)

### EXP-002

- `Type`: `experiment_concession`
- `Status`: `active`
- `Scope`: `Human Gate / harness`
- `Current Behavior`:
  - harness 可通过 `PIXIU_HUMAN_GATE_AUTO_ACTION` 自动 `approve / stop / redirect:*`
  - 默认实验 profile 当前使用自动审批，避免 Gate 1 卡在人工门
- `Why It Exists`:
  - 当前目标先是恢复实验有效性，而不是模拟完整人工审批流
- `Risk If Kept`:
  - 容易把实验特判误当成正式产品行为
- `Removal Trigger`:
  - 控制平面和正式审批路径稳定
  - 实验 profile 与正式 profile 明确分层
- `Related Settings`:
  - `config/experiments/default.json`
  - `PIXIU_HUMAN_GATE_AUTO_ACTION`
- `Evidence`:
  - [default.json](/home/torpedo/Workspace/ML/Pixiu/config/experiments/default.json)
  - [control.py](/home/torpedo/Workspace/ML/Pixiu/src/core/orchestrator/nodes/control.py)

### EXP-003

- `Type`: `experiment_concession`
- `Status`: `active`
- `Scope`: `Stage 2 generation`
- `Current Behavior`:
  - Stage 2 在本地复用 Stage 3 canonical validator/novelty 规则做 pre-screen
  - 整批全灭时最多只做一次 bounded retry
- `Why It Exists`:
  - 在 FormulaSketch 和 anti-collapse 还没进入主线前，先减少明显废料送入 Stage 3
- `Risk If Kept`:
  - 这只是止血层，不是最终生成架构
  - 容易继续掩盖上游 contract 问题
- `Removal Trigger`:
  - FormulaSketch Lite 进入主线
  - anti-collapse memory 与更强结构化生成生效
- `Related Settings`:
  - `src/agents/researcher.py` 内部诊断与 retry 逻辑
- `Evidence`:
  - [researcher.py](/home/torpedo/Workspace/ML/Pixiu/src/agents/researcher.py)
  - [2026-03-23-stage2-generation-compliance.md](/home/torpedo/Workspace/ML/Pixiu/docs/plans/2026-03-23-stage2-generation-compliance.md)

### EXP-004

- `Type`: `experiment_concession`
- `Status`: `active`
- `Scope`: `Stage 2b synthesis`
- `Current Behavior`:
  - Synthesis 失败时降级为 pass-through
  - 不阻塞主链
- `Why It Exists`:
  - 当前主线优先保证 Stage 2→5 闭环可运行
  - 去重与 family 聚合失败不应直接打断实验
- `Risk If Kept`:
  - collapse 问题会更晚暴露
  - family 级信号不能稳定回流到 Stage 2
- `Removal Trigger`:
  - anti-collapse memory 正式进入主线
  - synthesis 失败语义与 fallback 策略进一步收口
- `Related Settings`:
  - 无独立设置，当前属于运行时降级
- `Evidence`:
  - [18_synthesis-agent.md](/home/torpedo/Workspace/ML/Pixiu/docs/design/18_synthesis-agent.md)
  - [stage2.py](/home/torpedo/Workspace/ML/Pixiu/src/core/orchestrator/nodes/stage2.py)
  - [synthesis.py](/home/torpedo/Workspace/ML/Pixiu/src/agents/synthesis.py)

### MVP-001

- `Type`: `mvp_simplification`
- `Status`: `active`
- `Scope`: `Stage 5 judgment`
- `Current Behavior`:
  - Stage 5 仍是 deterministic/template MVP
  - `Critic -> RiskAuditor -> PortfolioManager -> ReportWriter`
  - allocation 仍是 equal-weight，报告仍是模板化输出
- `Why It Exists`:
  - 先建立可运行、可测试、可审计的 Stage 4→5 golden path
- `Risk If Kept`:
  - 容量和表达力有限
  - 易被误读成“Stage 5 已经成熟”
- `Removal Trigger`:
  - richer judgment / optimization / report contract 收口
  - 控制平面读模型更稳定
- `Related Settings`:
  - 无独立设置
- `Evidence`:
  - [24_stage-5-judgment.md](/home/torpedo/Workspace/ML/Pixiu/docs/design/24_stage-5-judgment.md)
  - [25_stage-45-golden-path.md](/home/torpedo/Workspace/ML/Pixiu/docs/design/25_stage-45-golden-path.md)

### MVP-002

- `Type`: `mvp_simplification`
- `Status`: `active`
- `Scope`: `Control plane`
- `Current Behavior`:
  - 当前 control plane 仍是最小 `state_store`
  - 还不是稳定读模型，也不是完整审计面
- `Why It Exists`:
  - 先支持实验状态、审批注入和最小进度可观测性
- `Risk If Kept`:
  - 产品层与实验层边界仍会继续共用最小读模型
- `Removal Trigger`:
  - 稳定读模型收口
  - API / CLI / 后续 Dashboard 的读取面分层
- `Related Settings`:
  - 无独立设置
- `Evidence`:
  - [13_control-plane.md](/home/torpedo/Workspace/ML/Pixiu/docs/design/13_control-plane.md)
  - [04_current-state.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/04_current-state.md)

### BRIDGE-001

- `Type`: `compat_bridge`
- `Status`: `active`
- `Scope`: `FactorPool persistence`
- `Current Behavior`:
  - Chroma persistent client 初始化失败时，FactorPool 会退到 in-memory client
  - 只 warning，不让主链直接崩
- `Why It Exists`:
  - 持久化面仍在硬化期
  - 当前更重要的是保住实验主线写路径
- `Risk If Kept`:
  - 容易让持久化问题被掩盖
  - 运行结果的长期资产化会失真
- `Removal Trigger`:
  - 持久化层在主支持环境上稳定
  - 对失败场景有更强测试和更清楚的运行告警
- `Related Settings`:
  - `src/factor_pool/storage.py`
- `Evidence`:
  - [storage.py](/home/torpedo/Workspace/ML/Pixiu/src/factor_pool/storage.py)
  - [14_factor-pool.md](/home/torpedo/Workspace/ML/Pixiu/docs/design/14_factor-pool.md)

### BRIDGE-002

- `Type`: `compat_bridge`
- `Status`: `active`
- `Scope`: `Orchestrator package surface`
- `Current Behavior`:
  - `src/core/orchestrator/__init__.py` 仍保留 package-root compatibility facade
- `Why It Exists`:
  - 当前正在做 orchestrator boundary 收口，仍需保住旧 caller
- `Risk If Kept`:
  - 容易继续模糊真正入口
- `Removal Trigger`:
  - caller/doc seam 收口完成
  - facade 进一步瘦身或退出主路径
- `Related Settings`:
  - 无独立设置
- `Evidence`:
  - [12_orchestrator.md](/home/torpedo/Workspace/ML/Pixiu/docs/design/12_orchestrator.md)
  - [__init__.py](/home/torpedo/Workspace/ML/Pixiu/src/core/orchestrator/__init__.py)

## 3. 今天已确认、但尚未实现的让步

这一节只记录已经达成共识、且会影响后续运行时行为的让步。它们还**不是当前代码真相**，但应该被明确标记，避免继续散落在对话中。

### EXP-005

- `Type`: `experiment_concession`
- `Status`: `agreed`
- `Scope`: `Experiment settings / fast feedback`
- `Current Behavior`:
  - 尚未实现
  - 目标是允许 frozen/cached market context、关闭高耗时 enrichment、限制 islands/subspaces，并且不污染正式 `factor_pool / failure memory / scheduler state`
- `Why It Exists`:
  - 为了快速验证 Stage 2/3 改动，而不是每次都跑完整 live context
- `Risk If Kept`:
  - 若长期不实现，实验迭代速度会继续过慢
  - 若实现后不隔离写路径，会污染正式经验资产
- `Removal Trigger`:
  - experiment settings layer v1 进入主线
  - fast feedback 与 controlled run 有明确 profile 区分
- `Related Settings`:
  - 未来的 experiment settings schema
- `Evidence`:
  - 本次 2026-03-23 架构讨论结论

### EXP-006

- `Type`: `mvp_simplification`
- `Status`: `agreed`
- `Scope`: `Stage 2 factor_algebra`
- `Current Behavior`:
  - 尚未实现
  - `FormulaSketch Lite v1` 将先只覆盖最脏子空间，且临时禁止自由 `Div`，只允许白名单安全模板
- `Why It Exists`:
  - 用更窄的生成空间，换更快的收敛和更少的低级废料
- `Risk If Kept`:
  - 若长期停留在 v1，会把结构化生成长期限制在局部子空间
- `Removal Trigger`:
  - Stage 2 family memory、anti-collapse memory、全子空间 sketch/renderer 进一步成熟
- `Related Settings`:
  - 未来 Stage 2 formula sketch 配置
- `Evidence`:
  - 本次 2026-03-23 架构讨论结论

### DEF-001

- `Type`: `deferred`
- `Status`: `agreed`
- `Scope`: `Failure system`
- `Current Behavior`:
  - 尚未实现 curator
  - 当前只达成规则共识：`Stage 5` 应产出 `FailureObservation`，promotion 由后续 curator 处理
- `Why It Exists`:
  - 当前主线优先是让实验真实跑起来并开始积累经验
  - 不是在实验入口前继续扩系统
- `Risk If Kept`:
  - 低质量 failure memory 仍可能继续进入长期资产链
- `Removal Trigger`:
  - 实验短轮次稳定
  - promotion policy 被收成独立设计并实现
- `Related Settings`:
  - 未来 failure policy / curator settings
- `Evidence`:
  - 本次 2026-03-23 架构讨论结论

### DEF-002

- `Type`: `deferred`
- `Status`: `agreed`
- `Scope`: `Stage 2 anti-collapse`
- `Current Behavior`:
  - 尚未实现
  - 已确认后续要引入 `passed family memory + novelty-collapse memory`
- `Why It Exists`:
  - 当前先通过 telemetry 确定最脏子空间，再做有针对性的收缩
- `Risk If Kept`:
  - 系统会继续围绕训练数据中的常见 family 绕圈
- `Removal Trigger`:
  - factor_algebra 的 FormulaSketch Lite 先进入主线
  - family-level memory 设计完成
- `Related Settings`:
  - 未来 Stage 2 family/novelty memory settings
- `Evidence`:
  - 本次 2026-03-23 架构讨论结论

## 4. 维护规则

- 新增 concession 时，优先先判断它属于 `experiment_concession`、`mvp_simplification`、`compat_bridge` 还是 `deferred`
- 如果某条 concession 已被拆除：
  - 将 `Status` 更新为 `resolved`
  - 在条目里补 removal proof
  - 必要时再移入 `docs/archive/`
- `docs/plans/` 只保留“下一步先拆哪个 concession”，不保留本账本本体
