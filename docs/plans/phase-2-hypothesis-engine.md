# Phase 2: Hypothesis Expansion Engine 实施计划

> 版本：1.0 | 日期：2026-03-16
> 前置：Phase 0+1 已完成（153 tests passed），主链端到端可运行
> 目标：将 Stage 2 从 note generation 升级为结构化的 Hypothesis Expansion Engine

---

## 1. 背景

Phase 0+1 完成后，Pixiu 主链可跑通，但 Stage 2 仍停留在"让 prompt 更聪明"的阶段：

- 子空间只是 prompt hint 文本差异，无结构化搜索空间
- 失败经验通过 `last_verdict.failure_explanation` 文本传递，无法积累和检索
- `synthesis_node` 是空壳 pass-through
- `MutationOperator` enum 已定义但无运行时消费者
- Regime 字段由 LLM 自由填写，无标准化检测

设计文档 `docs/design/stage-2-hypothesis-expansion.md` Section 8 指出三个缺口：

1. Exploration subspace registry（子空间从 prompt → 结构化约束）
2. Mutation operator vocabulary（变异算子运行时）
3. Hypothesis / StrategySpec 正式 schema（**已完成**）

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

### 2.3 Factor Algebra 原语注册表

| 字段 | 值 |
|------|------|
| 优先级 | P1 |
| 设计文档 | `docs/design/stage-2-hypothesis-expansion.md` §9 |
| 写集 | `src/hypothesis/primitives.py`, `src/agents/researcher.py` |
| 依赖 | 2.1（读取 FailureConstraint 的 forbidden patterns） |
| 验收标准 | 1) 原语分类注册（price-volume / temporal / cross-section / interaction）2) 组合约束规则（嵌套深度、禁止模式）3) researcher prompt 注入结构化原语清单 4) 单元测试 |

**交付物**：
- `src/hypothesis/primitives.py` — PrimitiveRegistry
- `src/agents/researcher.py` — 生成 prompt 时注入原语约束
- `tests/test_primitives.py` — 单元测试

### 2.4 Symbolic Mutation 运行时

| 字段 | 值 |
|------|------|
| 优先级 | P1 |
| 设计文档 | `docs/design/stage-2-hypothesis-expansion.md` §10 |
| 写集 | `src/hypothesis/mutation.py`, `src/agents/researcher.py` |
| 依赖 | 2.3（共享原语定义和 AST 解析） |
| 验收标准 | 1) 5 种 MutationOperator 运行时实现 2) AST 解析 Qlib 公式 3) mutation trace 可追踪 4) SYMBOLIC_MUTATION 子空间可纯符号生成（不调 LLM）5) 单元测试 |

**交付物**：
- `src/hypothesis/mutation.py` — SymbolicMutator + QlibFormulaAST
- `src/agents/researcher.py` — SYMBOLIC_MUTATION 路径集成
- `tests/test_mutation.py` — 单元测试

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

## 3. 依赖图

```
2.1 FailureConstraint ─────────────┐
                                    ├──→ 2.3 Factor Algebra ──→ 2.4 Symbolic Mutation
2.2 SynthesisAgent (并行)           │
                                    │
2.5 Regime Detection (独立) ────────┘
```

**并行窗口**：
- Wave 1: 2.1 + 2.2 并行（写集不重叠）
- Wave 2: 2.3 + 2.5 并行（2.3 依赖 2.1，2.5 独立）
- Wave 3: 2.4（依赖 2.3）

## 4. 任务路由

| 子任务 | 路由 | 理由 |
|--------|------|------|
| 2.1 FailureConstraint | codex | Schema + CRUD，边界明确 |
| 2.2 SynthesisAgent | codex | 独立模块实现 |
| 2.3 Factor Algebra | coordinator + codex | 原语设计需 coordinator 审阅 |
| 2.4 Symbolic Mutation | codex | AST 解析 + 算子实现，边界明确 |
| 2.5 Regime Detection | codex | 独立模块，规则明确 |

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
