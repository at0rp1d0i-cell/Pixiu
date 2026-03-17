# Phase 2: Hypothesis Expansion Engine 实施计划

> ✅ **Phase 2 已完成** — 2026-03-17 | 327 smoke/unit tests 通过
> 本文档作为历史执行计划保留，不再作为开发入口。

---

> 版本：1.1 | 更新：2026-03-17（同步队友 af35d1e 实现进度）
> 前置：Phase 0+1 已完成（177 tests passed），主链端到端可运行
> 目标：将 Stage 2 从 note generation 升级为结构化的 Hypothesis Expansion Engine

---

## 1. 背景

Phase 0+1 完成后，Pixiu 主链可跑通，但 Stage 2 仍有以下缺口待填补：

- ~~子空间只是 prompt hint 文本差异，无结构化搜索空间~~ **→ 已由 af35d1e 解决**
- 失败经验通过 `last_verdict.failure_explanation` 文本传递，无法积累和检索
- `synthesis_node` 是空壳 pass-through
- ~~`MutationOperator` enum 已定义但无运行时消费者~~ **→ af35d1e 完成上下文注入，AST 运行时待做**
- Regime 字段由 LLM 自由填写，无标准化检测

设计文档 `docs/design/stage-2-hypothesis-expansion.md` Section 8 指出三个缺口：

1. ~~Exploration subspace registry（子空间从 prompt → 结构化约束）~~ **→ 已完成（`SubspaceRegistry` + `build_subspace_context()`）**
2. Mutation operator vocabulary（AST 级别的符号变异运行时，LLM 引导已完成，纯符号路径待做）
3. ~~Hypothesis / StrategySpec 正式 schema~~ **→ 已完成（Phase 1）**

### 队友 af35d1e 已实现内容（2026-03-17）

| 模块 | 实现内容 |
|------|---------|
| `src/schemas/exploration.py` | `FactorPrimitive`、`MarketMechanismTemplate`、`NarrativeCategory`、`MutationRecord`、`SubspaceConfig`、`SubspaceRegistry`（含 20 条原语、6 个机制模板、4 个叙事类别） |
| `src/scheduling/subspace_context.py` | 4 个子空间的 context builder + dispatcher `build_subspace_context()` |
| `src/agents/researcher.py` | 集成 `build_subspace_context()`，LLM 接收结构化上下文而非 hint 字符串 |
| `src/schemas/hypothesis.py` / `research_note.py` | 增加 `exploration_subspace`、`mutation_record` 追踪字段 |
| `src/schemas/state.py` | 增加 `hypotheses`、`strategy_specs` 字段 |
| tests | 39 个新测试覆盖 registry、context builder、追踪字段 |

## 2. 子任务分解

### 2.1 FailureConstraint Schema + 查询接口

| 字段 | 值 |
|------|------|
| 优先级 | P0 — 所有子空间依赖 |
| 设计文档 | `docs/design/failure-constraint.md` |
| 写集 | `src/schemas/failure_constraint.py`, `src/factor_pool/pool.py` |
| 依赖 | 无 |
| 验收标准 | 1) Schema 定义完整 2) FactorPool 支持 failure_constraints collection 的 CRUD 3) judgment 节点写入约束 4) researcher 节点查询约束 5) 单元测试覆盖 |

**交付物**：
- `src/schemas/failure_constraint.py` — FailureConstraint schema
- `src/factor_pool/pool.py` — 新增 `register_constraint()` / `query_constraints()` 方法
- `src/agents/judgment.py` — verdict 生成后自动提取 FailureConstraint
- `src/agents/researcher.py` — 替换 `failed_formulas` 列表为结构化约束查询
- `tests/test_failure_constraint.py` — 单元测试

### 2.2 SynthesisAgent 实现

| 字段 | 值 |
|------|------|
| 优先级 | P0 — 填充空壳节点 |
| 设计文档 | `docs/design/synthesis-agent.md` |
| 写集 | `src/agents/synthesis.py`, `src/core/orchestrator.py` |
| 依赖 | 无（可与 2.1 并行） |
| 验收标准 | 1) 向量去重（cosine > 0.85 → 合并）2) factor family 聚类 3) 跨 island merge 建议 4) synthesis_node 不再是 pass-through 5) 单元测试 + e2e mock 覆盖 |

**交付物**：
- `src/agents/synthesis.py` — SynthesisAgent 类
- `src/core/orchestrator.py` — synthesis_node 调用 SynthesisAgent
- `tests/test_synthesis.py` — 单元测试

### 2.3 Factor Algebra 原语注册表 ✅ 已基本完成

**队友 af35d1e 已实现**：`SubspaceRegistry`（含 20 条原语词汇表）+ `build_factor_algebra_context()` + researcher 集成。

**剩余范围（已缩减）**：

| 字段 | 值 |
|------|------|
| 优先级 | P2（降级，核心已完成） |
| 设计文档 | `docs/design/stage-2-hypothesis-expansion.md` §9 |
| 写集 | `src/schemas/exploration.py`（扩展），`src/agents/prefilter.py` |
| 依赖 | 2.1（FailureConstraint 的 forbidden_patterns 集成到 SubspaceRegistry） |
| 验收标准 | 1) `SubspaceRegistry` 增加 `CompositionConstraints`（嵌套深度、forbidden patterns 规则）2) forbidden_patterns 由 FailureConstraint 动态填充 |

**剩余交付物**：
- `src/schemas/exploration.py` — `SubspaceRegistry` 增加 `CompositionConstraints` 字段
- 注：`PrimitiveRegistry` 类不再单独实现，`SubspaceRegistry` 已承担其职责

### 2.4 Symbolic Mutation 运行时（LLM 引导已完成，AST 层待做）

**队友 af35d1e 已实现**：`MutationRecord` schema + `build_symbolic_mutation_context()`（LLM 被引导选择 seed + operator 进行变异，mutation_record 追踪）。

**剩余范围（AST 级纯符号路径）**：

| 字段 | 值 |
|------|------|
| 优先级 | P1（仍需做，纯符号路径价值高） |
| 设计文档 | `docs/design/stage-2-hypothesis-expansion.md` §10 |
| 写集 | `src/hypothesis/mutation.py`（新建） |
| 依赖 | 无（独立模块） |
| 验收标准 | 1) `QlibFormulaParser` 可解析常用算子为 AST 2) `SymbolicMutator` 对 5 种算子有确定性实现 3) SYMBOLIC_MUTATION 路径可绕过 LLM 纯符号生成 4) 单元测试 |

**剩余交付物**：
- `src/hypothesis/mutation.py` — `QlibFormulaParser` + `FormulaNode` + `SymbolicMutator`
- `src/agents/researcher.py` — SYMBOLIC_MUTATION 子空间优先走纯符号路径，失败时 fallback 到 LLM
- `tests/test_mutation.py` — 单元测试
- 注：`MutationTrace` 命名统一到队友的 `MutationRecord`（已有 schema）

### 2.5 Regime Detection 独立模块

| 字段 | 值 |
|------|------|
| 优先级 | P1 |
| 设计文档 | `docs/design/stage-2-hypothesis-expansion.md` §11 |
| 写集 | `src/market/regime_detector.py`, `src/agents/market_analyst.py` |
| 依赖 | 无（可与 2.3/2.4 并行） |
| 验收标准 | 1) 标准化 regime 枚举 2) 基于规则的检测逻辑（波动率、趋势、成交量）3) Stage 1 集成（MarketContextMemo.market_regime 由检测器产出）4) Stage 3 集成（prefilter 用当前 regime 过滤 invalid_regimes）5) 单元测试 |

**交付物**：
- `src/market/regime_detector.py` — RegimeDetector
- `src/schemas/market_context.py` — regime 枚举标准化
- `src/agents/market_analyst.py` — 集成 RegimeDetector
- `src/agents/prefilter.py` — 新增 regime 过滤逻辑
- `tests/test_regime_detector.py` — 单元测试

## 3. 依赖图（更新后）

```
2.1 FailureConstraint ─────────────────→ 2.3 Factor Algebra 剩余范围（forbidden_patterns）
                                                          ↑
2.2 SynthesisAgent (并行)              已完成 ✅（SubspaceRegistry + context builders）

2.4 Symbolic Mutation AST (独立)
2.5 Regime Detection (独立)
```

**当前并行窗口（Wave 1）**：
- 2.1 + 2.2 + 2.4 + 2.5 可全部并行（写集不重叠）
- 2.3 剩余范围依赖 2.1，在 Wave 2 完成

## 4. 任务路由（更新后）

| 子任务 | 状态 | 路由 | 备注 |
|--------|------|------|------|
| 2.1 FailureConstraint | **待做** | codex | Schema + CRUD，边界明确 |
| 2.2 SynthesisAgent | **待做** | codex | 独立模块实现 |
| 2.3 Factor Algebra | **✅ 核心完成**，剩余 P2 | codex | forbidden_patterns 集成，依赖 2.1 |
| 2.4 Symbolic Mutation AST | **待做（P1）** | codex | AST 解析 + 算子，边界明确 |
| 2.5 Regime Detection | **待做** | codex | 独立模块，规则明确 |

所有子任务的 **schema 设计** 由 coordinator 在设计文档中固定，codex 负责实现。

## 5. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| Qlib 公式 AST 解析复杂度 | 2.4 延期 | 先支持常用算子子集，渐进扩展 |
| SynthesisAgent embedding 质量 | 去重精度不足 | 先用简单的 TF-IDF，后续可换 sentence-transformers |
| Regime 检测规则过于简单 | 误分类 | 先出 MVP 5 种 regime，accumulate 真实数据后校准 |
| FailureConstraint 过度约束 | 限制探索空间 | 加 `times_violated` 计数，低违反率的约束自动降级 |

## 6. 测试策略

- 每个子任务必须附带 smoke/unit 测试
- Phase 2 完成后，现有 e2e 测试（`test_e2e_pipeline.py`）必须继续通过
- 新增 e2e 场景：synthesis 去重 + failure constraint 反馈循环
- 最终验收：`uv run pytest -q tests -m "smoke or unit"` 全绿

## 7. 完成标志

Phase 2 完成的定义：

1. `synthesis_node` 不再是 pass-through，执行去重 + family 检测
2. 失败因子自动生成 FailureConstraint，下一轮 researcher 可查询
3. Factor Algebra subspace 注入结构化原语约束
4. Symbolic Mutation subspace 可纯符号生成候选（不调 LLM）
5. Regime Detection 产出标准化 regime 标签，prefilter 据此过滤
6. 所有现有测试继续通过，新增测试覆盖新模块
7. 设计文档与实现一致
