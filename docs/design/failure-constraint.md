# FailureConstraint: 失败经验结构化沉淀

> 版本：1.0 | 日期：2026-03-16
> 依赖：`interface-contracts.md`, `stage-5-judgment.md`, `factor-pool.md`
> 实施计划：`docs/plans/phase-2-hypothesis-engine.md` §2.1

---

## 1. 问题定义

当前失败经验的传递路径：

```
Stage 5 CriticVerdict
  → verdict.failure_explanation (自然语言字符串)
  → 下一轮 researcher prompt 的 feedback_section
  → LLM 自行理解并"尽量避免"
```

缺陷：
- **无法跨轮次积累**：只传递上一轮的 `last_verdict`，历史失败经验丢失
- **无法结构化检索**：无法按 island / failure_mode / formula pattern 查询
- **无法度量有效性**：不知道某条约束是否真的减少了重复失败
- **无法被 prefilter 消费**：Stage 3 无法用已知失败模式做硬过滤

## 2. 设计目标

1. 将失败经验从自然语言提升为结构化 schema
2. 持久化到 FactorPool，支持按维度检索
3. 被 Stage 2（researcher）和 Stage 3（prefilter）双重消费
4. 自带有效性度量机制，防止过度约束

## 3. Schema 定义

```python
# src/schemas/failure_constraint.py

class FailureMode(str, Enum):
    """标准化失败模式分类"""
    LOW_SHARPE = "low_sharpe"              # Sharpe < 阈值
    HIGH_TURNOVER = "high_turnover"        # 换手率过高
    NO_IC = "no_ic"                        # IC 均值接近 0
    NEGATIVE_IC = "negative_ic"            # IC 均值为负
    HIGH_DRAWDOWN = "high_drawdown"        # 最大回撤过大
    OVERFITTING = "overfitting"            # 过拟合（IS/OOS 差距大）
    LOW_COVERAGE = "low_coverage"          # 覆盖率不足
    EXECUTION_ERROR = "execution_error"    # 公式运行时错误
    DUPLICATE = "duplicate"               # 与已有因子高度相关

class FailureConstraint(PixiuBase):
    """一条结构化的失败经验约束"""

    # 标识
    constraint_id: str                     # UUID
    source_note_id: str                    # 产生此约束的 FactorResearchNote
    source_verdict_id: str                 # 产生此约束的 CriticVerdict

    # 分类
    failure_mode: FailureMode              # 标准化失败模式
    island: str                            # 所属 island
    subspace: Optional[str] = None         # 产生该失败的探索子空间

    # 约束内容
    formula_pattern: str                   # 失败公式的结构化模式
    constraint_rule: str                   # 可执行约束描述
    severity: str = "warning"              # "hard" | "warning"
                                           # hard: prefilter 直接拒绝
                                           # warning: 注入 prompt 提醒

    # 元数据
    created_at: str                        # ISO 8601
    times_violated: int = 0               # 后续违反次数
    times_checked: int = 0                # 被检查次数
    last_violated_at: Optional[str] = None
```

### 3.1 formula_pattern 规范

`formula_pattern` 不是原始公式，而是提取出的结构模式。提取规则：

| 原始公式 | 提取的 pattern |
|----------|----------------|
| `Div($close, Ref($close, 5))` | `Div($close, Ref($close, N_SHORT))` |
| `Rank(Mean($volume, 20))` | `Rank(Mean($volume, N_MID))` |
| `Mean($close, 120)` | `Mean($close, N_LONG)` |
| `Log($close + 1) - Log(Ref($close, 3) + 1)` | `Log($close + N_SHORT) - Log(Ref($close, N_SHORT) + N_SHORT)` |

规则：
- 具体数值参数按三档替换（保留算子结构和字段名）：
  - 1–10 → `N_SHORT`（短窗口）
  - 11–60 → `N_MID`（中窗口）
  - 61+ → `N_LONG`（长窗口）
- 字段名保持原样（不替换为 `$F`）
- 保留算子结构

向后兼容说明：旧版约束记录中存在使用 `N` 占位符的 pattern，
`ConstraintChecker._matches_pattern` 同时支持新格式（N_SHORT/N_MID/N_LONG）和旧格式（N），
无需迁移历史数据。

### 3.2 constraint_rule 示例

```
"avoid Ref window < 3 for momentum island — signal too noisy"
"avoid nested Rank(Rank(...)) — reduces to monotone transform, no added information"
"avoid Div($volume, Ref($volume, N)) without smoothing — turnover > 50%"
```

## 4. 存储层

### 4.1 FactorPool 扩展

在 FactorPool（ChromaDB）中新增 collection `failure_constraints`：

```python
# src/factor_pool/pool.py — 新增方法

class FactorPool:
    CONSTRAINT_COLLECTION = "failure_constraints"

    def register_constraint(self, constraint: FailureConstraint) -> None:
        """写入一条 FailureConstraint"""
        collection = self._get_or_create_collection(self.CONSTRAINT_COLLECTION)
        collection.upsert(
            ids=[constraint.constraint_id],
            documents=[constraint.constraint_rule],   # 用于向量检索
            metadatas=[{
                "failure_mode": constraint.failure_mode.value,
                "island": constraint.island,
                "subspace": constraint.subspace or "",
                "formula_pattern": constraint.formula_pattern,
                "severity": constraint.severity,
                "times_violated": constraint.times_violated,
                "created_at": constraint.created_at,
            }],
        )

    def query_constraints(
        self,
        island: Optional[str] = None,
        failure_mode: Optional[FailureMode] = None,
        limit: int = 10,
    ) -> List[FailureConstraint]:
        """按 island / failure_mode 查询约束"""
        where_clauses = {}
        if island:
            where_clauses["island"] = island
        if failure_mode:
            where_clauses["failure_mode"] = failure_mode.value

        collection = self._get_or_create_collection(self.CONSTRAINT_COLLECTION)
        results = collection.get(
            where=where_clauses if where_clauses else None,
            limit=limit,
        )
        return self._parse_constraint_results(results)

    def query_constraints_by_formula(
        self,
        formula: str,
        limit: int = 5,
    ) -> List[FailureConstraint]:
        """按公式相似度检索相关约束"""
        collection = self._get_or_create_collection(self.CONSTRAINT_COLLECTION)
        results = collection.query(
            query_texts=[formula],
            n_results=limit,
        )
        return self._parse_constraint_results(results)

    def increment_violation(self, constraint_id: str) -> None:
        """记录一次约束违反"""
        # 读取 → 更新 times_violated → 写回
        ...
```

### 4.2 In-Memory Fallback

与现有 FactorPool 一致，当 ChromaDB 不可用时，使用 `dict` 作为 fallback 存储。`query_constraints_by_formula` 在 fallback 模式下退化为精确匹配。

## 5. 生产者：Stage 5 Judgment

### 5.1 约束提取逻辑

在 `Critic.evaluate()` 之后，对 `overall_passed=False` 的 verdict 自动提取 FailureConstraint：

```python
# src/agents/judgment.py — 新增

class ConstraintExtractor:
    """从 CriticVerdict 提取 FailureConstraint"""

    def extract(
        self,
        verdict: CriticVerdict,
        note: FactorResearchNote,
    ) -> Optional[FailureConstraint]:
        if verdict.overall_passed:
            return None

        failure_mode = self._classify_failure_mode(verdict)
        formula_pattern = self._extract_pattern(note.proposed_formula)

        return FailureConstraint(
            constraint_id=str(uuid.uuid4()),
            source_note_id=note.note_id,
            source_verdict_id=verdict.verdict_id,
            failure_mode=failure_mode,
            island=note.island,
            subspace=None,  # 从 state 获取
            formula_pattern=formula_pattern,
            constraint_rule=self._generate_rule(failure_mode, formula_pattern, verdict),
            severity=self._determine_severity(failure_mode, verdict),
            created_at=datetime.now(UTC).isoformat(),
        )

    def _classify_failure_mode(self, verdict: CriticVerdict) -> FailureMode:
        """根据 failed_checks 映射到标准化 FailureMode"""
        # 优先级：execution_error > overfitting > 指标类
        if verdict.failure_mode == "execution_error":
            return FailureMode.EXECUTION_ERROR
        for check in verdict.checks:
            if not check.passed:
                return self._metric_to_failure_mode(check.metric)
        return FailureMode.LOW_SHARPE  # fallback

    def _extract_pattern(self, formula: str) -> str:
        """将具体公式抽象为结构模式"""
        import re
        # 数值参数 → N
        pattern = re.sub(r'\b\d+\b', 'N', formula)
        return pattern
```

### 5.2 集成点

在 `judgment_node` 中，verdict 生成后立即调用 `ConstraintExtractor`：

```python
# orchestrator.py judgment_node 内部
extractor = ConstraintExtractor()
for verdict, note in zip(verdicts, approved_notes):
    constraint = extractor.extract(verdict, note)
    if constraint:
        pool.register_constraint(constraint)
```

## 6. 消费者

### 6.1 Stage 2 — AlphaResearcher

替换当前的 `failed_formulas` 列表参数：

```python
# researcher.py generate_batch() 内部

# Before:
failed_section = "\n".join(f"- {f}" for f in failed_formulas[:5])

# After:
pool = FactorPool()
constraints = pool.query_constraints(island=self.island, limit=10)
hard_constraints = [c for c in constraints if c.severity == "hard"]
warnings = [c for c in constraints if c.severity == "warning"]

constraint_section = ""
if hard_constraints:
    constraint_section += "## 硬约束（必须遵守）\n"
    constraint_section += "\n".join(f"- {c.constraint_rule}" for c in hard_constraints)
if warnings:
    constraint_section += "\n## 警告（建议避免）\n"
    constraint_section += "\n".join(f"- {c.constraint_rule}" for c in warnings)
```

### 6.2 Stage 3 — Prefilter

新增 ConstraintChecker 作为第四道过滤器：

```python
# prefilter.py

class ConstraintChecker:
    """检查候选公式是否匹配已知失败模式"""

    def __init__(self, pool: FactorPool):
        self.pool = pool

    def check(self, note: FactorResearchNote) -> tuple[bool, str]:
        hard_constraints = self.pool.query_constraints(
            island=note.island,
            limit=20,
        )
        hard_constraints = [c for c in hard_constraints if c.severity == "hard"]

        for constraint in hard_constraints:
            if self._matches_pattern(note.proposed_formula, constraint.formula_pattern):
                self.pool.increment_violation(constraint.constraint_id)
                return False, f"Matches failure pattern: {constraint.constraint_rule}"

        return True, "No known failure patterns matched"
```

过滤链变为：`Validator → NoveltyFilter → AlignmentChecker → ConstraintChecker`

## 7. 约束生命周期管理

### 7.1 自动降级

约束不应永久存在。引入简单的有效性度量：

```
violation_rate = times_violated / times_checked
```

- `violation_rate < 0.05` 且 `times_checked > 50`：约束已充分吸收，自动降级为 `warning`
- `times_violated == 0` 且 `times_checked > 100`：约束可能过时，标记为 `inactive`

降级逻辑在 `loop_control_node` 中每 N 轮执行一次。

### 7.2 手动管理

通过 CLI 提供约束管理命令：

```bash
pixiu constraints list --island momentum
pixiu constraints deactivate <constraint_id>
pixiu constraints stats
```

## 8. 测试要求

1. **单元测试**：FailureConstraint schema 验证、pattern 提取、failure mode 分类
2. **集成测试**：FactorPool constraint CRUD（ChromaDB + fallback）
3. **E2E mock**：verdict → constraint 提取 → researcher 查询 → prefilter 检查
4. **回归**：现有 153 个测试不受影响
