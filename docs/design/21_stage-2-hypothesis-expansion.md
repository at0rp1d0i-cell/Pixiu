# Pixiu v2 Stage 2: Hypothesis Expansion Engine
Purpose: Define how Stage 2 expands the hypothesis space and compresses exploration into structured research objects.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-18

> 版本：2.2 | 更新：2026-03-16（补充 §9-11 实现规格）
> 角色：扩大 hypothesis space，并将探索结果压缩成可进入 Stage 3/4 的结构化研究对象
> 前置依赖：`10_authority-model.md`、`11_interface-contracts.md`、`20_stage-1-market-context.md`

---

## 1. 角色定义

Stage 2 不再只是“并行生成几个候选因子公式”。

它的真正职责是：

> 在不扩大 execution power 的前提下，系统性扩大 hypothesis space，并把探索结果压缩成可审计、可过滤、可执行的研究对象。

这一步是 Pixiu 当前 authority model 收权后的主要补偿层。原本散落在执行层和 agent theatre 里的“聪明感”，应该回收到这里。

## 2. 设计目标

- 保留 LLM 的创造力
- 不把创造力下放到执行真值层
- 让假设扩展变成有子空间、有算子、有边界的系统过程
- 为 Stage 3 / Stage 4 提供强类型输入，而不是自然语言请求

## 3. 输入

Stage 2 读取的输入不应只是一段 prompt 背景，而应是受约束的研究上下文：

- `MarketContextMemo`
- `HistoricalInsight`
- `FailureConstraint` 摘要
- 当前 Island 的研究方向与优先级
- 当前启用的数据原语集合

当前运行时里，这些输入主要通过：

- `MarketContextMemo`
- `FactorPool` 摘要
- `last_verdict`

间接传入 `AlphaResearcher`。

## 4. 四个探索子空间 + Regime 基础设施层

### 4.1 Factor Algebra Search

不是随意拼公式，而是围绕受约束的原语空间做搜索。

第一版原语可分成：

- price-volume primitives
- fundamental primitives
- event-derived primitives
- temporal transforms
- cross-sectional operators
- regime switches

目标是让“发现公式”逐步从自由文本联想，过渡为可解释的算子组合搜索。

### 4.2 Symbolic Factor Mutation

把“改进旧想法”显式化，而不是完全依赖 prompt 即兴发挥。

典型 mutation operator：

- add / remove operator
- swap horizon
- change normalization
- alter interaction term
- impose monotonicity or stability prior

这一步的意义是让“迭代”可以被记录、比较和复用。

### 4.3 Cross-Market Pattern Mining

迁移的不是现成公式，而是市场机制骨架。

目标对象包括：

- market mechanism analogy
- transmission path
- cross-market regime similarity

这使 Stage 2 不只是从 A 股自身历史里兜圈子，而是能吸收跨市场启发，再压缩回 A 股可执行假设。

### 4.4 Economic Narrative Mining

从政策、产业链、公告、预期偏差等叙事材料中抽取结构化机制。

典型输出应是：

- candidate mechanism
- latent driver hypothesis
- event-to-factor mapping

这里的 LLM 价值很高，但输出仍必须落在研究对象上，而不是直接形成交易建议。

### 4.5 Regime 基础设施层（不再作为独立子空间）

很多因子不是“始终有效”，而是只在某些 regime 下有效。

因此 Stage 2 应开始表达：

- factor + applicable regime
- factor + invalid regime
- factor + switching-rule hypothesis

这会直接影响 Stage 3 的 gate 设计，以及 Stage 4/5 对失效模式的判断。

当前运行时口径是：

- 活跃探索子空间只有 4 个：`FACTOR_ALGEBRA / SYMBOLIC_MUTATION / CROSS_MARKET / NARRATIVE_MINING`
- regime 通过 `RegimeDetector / RegimeFilter / applicable_regimes / invalid_regimes` 进入基础设施层
- 后续扩展的是 regime 特征量和消费路径，而不是恢复一个独立的 `REGIME_CONDITIONAL` 子空间

## 5. 输出对象

### 当前运行时输出

当前代码主干仍以 `FactorResearchNote` 作为 Stage 2 的主要输出对象。

它承担的作用是：

- 记录 hypothesis 与 economic intuition
- 承载 `proposed_formula` / `final_formula`
- 承载 `exploration_questions`
- 作为 Stage 3 / Stage 4 的临时桥接对象

### 目标对象模型

从设计上，Stage 2 应逐步靠拢两层对象：

- `Hypothesis`
  - 负责表达市场机制、适用 regime、失效前提和启发来源
- `StrategySpec`
  - 负责表达可执行因子语义、可用字段、参数化配置和执行约束

也就是说：

- `Hypothesis` 回答 “为什么这件事值得测”
- `StrategySpec` 回答 “到底测什么”

### Runtime bridge

在当前运行时里，`FactorResearchNote` 仍是进入 Stage 3 / Stage 4 的桥接对象。

但设计约束已经固定：

- Stage 2 的收敛方向是 `Hypothesis -> StrategySpec`
- 不允许继续输出自由文本执行请求
- 新增能力应优先落到子空间、算子和对象上，而不是继续堆 prompt 描述

## 6. 与 Stage 4a / Stage 4b 的关系

Stage 2 只负责提出：

- 值得进一步探索的问题
- 值得正式执行的候选对象

不负责：

- 决定如何重试执行
- 在执行时修脚本
- 在回测后临场改语义

### `exploration_questions`

当前 `exploration_questions` 是 Stage 2 与 Stage 4a 的桥。

它们的职责应该进一步收敛为：

- 明确问题
- 明确需要的字段
- 明确建议的分析类型

而不是把 Stage 4a 变成通用“让 AI 去随便看看”的口子。

### `final_formula`

进入 Stage 4b 的唯一公式字段必须是：

- `final_formula`

这条规则保持不变。Stage 2 可以探索，但进入确定性执行时只能交付最终表达式。

## 7. 当前运行时组件

### `AlphaResearcher`

当前 MVP 运行时仍由 `AlphaResearcher` 负责单个 Island 的批量生成。

它目前已做到：

- Island 级并行
- 批量生成 `FactorResearchNote`
- 支持 `exploration_questions`
- 接收历史反馈做局部改进

它现在已经显式体现 4 个活跃子空间，并通过 `RegimeDetector / RegimeFilter` 将 regime 收敛为基础设施层。

当前主要缺口不是“子空间不存在”，而是 `AlphaResearcher` 仍缺少工具调用能力，对新增 RSS / MCP 数据源只能被动消费。

### `SynthesisAgent`

`SynthesisAgent` 当前仍停留在弱关联检查层。

它未来更有价值的职责应是：

- 去重
- 识别潜在 family
- 提出 hypothesis merge / split
- 输出更结构化的组合启发

## 8. 设计缺口（早期 Phase 2 目标，当前状态以 audit 为准）

三个缺口在 Phase 2 中按序填补：

| 缺口 | Phase 2 子任务 | 状态 |
|------|--------------|------|
| Exploration subspace registry | 2.3 Factor Algebra 原语注册表 | 部分实现（已存在 `SubspaceRegistry` / `build_subspace_context`，独立 `PrimitiveRegistry` 仍未收口） |
| Mutation operator vocabulary | 2.4 Symbolic Mutation 运行时 | 已实现（`SymbolicMutator` + 5 种算子） |
| `Hypothesis / StrategySpec` 正式 schema | **已完成**（Phase 1） | ✅ |
| FailureConstraint 结构化沉淀 | 2.1（参见 `17_failure-constraint.md`） | 已实现（`ConstraintExtractor` / `ConstraintChecker`） |
| SynthesisAgent 功能实现 | 2.2（参见 `18_synthesis-agent.md`） | 已实现（仍可继续增强） |
| Regime Detection 标准化 | 2.5（参见 §11） | 已实现（`RegimeDetector` + `RegimeFilter`） |

当前实现偏差，请查看 `../overview/05_spec-execution-audit.md`。

---

## 9. Factor Algebra 原语注册表（§2.3 实现规格）

### 9.1 设计目标

将”发现公式”从自由文本联想，过渡为**受约束的原语组合搜索**。

Researcher 不再对着空白 prompt 发挥，而是：
1. 从原语注册表中选取合法原语
2. 按组合规则拼接
3. 对照 FailureConstraint 中的 forbidden patterns 过滤

### 9.2 原语分类

```python
# src/hypothesis/primitives.py

class PrimitiveCategory(str, Enum):
    PRICE_VOLUME = “price_volume”         # $close, $open, $high, $low, $volume, $vwap
    FUNDAMENTAL = “fundamental”           # $pe_ttm, $pb, $roe, $revenue_yoy（需 FUNDAMENTAL_FIELDS_ENABLED）
    TEMPORAL = “temporal”                 # Ref, Mean, Std, Max, Min, Sum
    CROSS_SECTION = “cross_section”       # Rank, Zscore, Demean, Neutralize
    ARITHMETIC = “arithmetic”             # Add, Sub, Mul, Div, Log, Abs, Sign, Power
    INTERACTION = “interaction”           # 两个子空间字段的交叉项
    REGIME_SWITCH = “regime_switch”       # If($regime == X, expr_a, expr_b)


class Primitive(PixiuBase):
    name: str                             # 如 “Ref”, “$close”
    category: PrimitiveCategory
    arity: int                            # 参数个数：0=字段, 1=一元, 2=二元
    param_constraints: Dict[str, Any]     # 如 {“window”: {“min”: 1, “max”: 252}}
    description: str
    example: str


class PrimitiveRegistry:
    “””原语注册表 — 单例，启动时加载”””

    _registry: Dict[str, Primitive] = {}

    @classmethod
    def register(cls, p: Primitive) -> None:
        cls._registry[p.name] = p

    @classmethod
    def get(cls, name: str) -> Optional[Primitive]:
        return cls._registry.get(name)

    @classmethod
    def list_by_category(cls, category: PrimitiveCategory) -> List[Primitive]:
        return [p for p in cls._registry.values() if p.category == category]

    @classmethod
    def to_prompt_section(cls, enabled_categories: Optional[List[PrimitiveCategory]] = None) -> str:
        “””生成注入 researcher prompt 的原语清单文本”””
        ...
```

### 9.3 内置原语定义

启动时注册的标准原语（`primitives.py` 模块级代码）：

**Price-Volume（始终启用）**：
`$close`, `$open`, `$high`, `$low`, `$volume`, `$vwap`, `$amount`, `$factor`

**Temporal transforms**：
`Ref(expr, N)`, `Mean(expr, N)`, `Std(expr, N)`, `Max(expr, N)`, `Min(expr, N)`,
`Sum(expr, N)`, `Delta(expr, N)`, `Slope(expr, N)`, `Resi(expr, expr, N)`

**Cross-sectional operators**：
`Rank(expr)`, `Zscore(expr)`, `Demean(expr)`, `Corr(expr_a, expr_b, N)`

**Arithmetic**：
`Add`, `Sub`, `Mul`, `Div`, `Log`, `Abs`, `Sign`, `Power`, `If`

**Fundamental（`FUNDAMENTAL_FIELDS_ENABLED=true` 时启用）**：
`$pe_ttm`, `$pb`, `$roe`, `$revenue_yoy`, `$profit_yoy`, `$turnover_rate`, `$float_mv`

### 9.4 组合约束规则

```python
class CompositionConstraints:
    MAX_NESTING_DEPTH = 4              # 最大嵌套深度
    MAX_TOTAL_OPERATORS = 8            # 单公式最多算子数
    FORBIDDEN_PATTERNS = [
        “Rank(Rank(...))”,             # 冗余双重排名
        “Div(X, Ref(X, 0))”,          # 除以当日自身（分母恒为 1）
        “Log(Ref($volume, N))”,        # 未归一化的对数成交量（高换手）
    ]
```

### 9.5 与 Researcher 的集成

在 `AlphaResearcher.generate_batch()` 构建 prompt 时，注入原语清单：

```python
# researcher.py

registry = PrimitiveRegistry()
primitives_section = registry.to_prompt_section(
    enabled_categories=[
        PrimitiveCategory.PRICE_VOLUME,
        PrimitiveCategory.TEMPORAL,
        PrimitiveCategory.CROSS_SECTION,
        PrimitiveCategory.ARITHMETIC,
    ] + ([PrimitiveCategory.FUNDAMENTAL] if FUNDAMENTAL_FIELDS_ENABLED else [])
)
```

---

## 10. Symbolic Mutation 运行时（§2.4 实现规格）

### 10.1 设计目标

把”改进旧因子”从 LLM 即兴发挥，变成**显式、可追踪的算子操作**。

SYMBOLIC_MUTATION 子空间触发时，优先**纯符号生成**（不调 LLM），对已有公式施加 mutation operators。

### 10.2 MutationOperator 枚举（已存在于 schema）

```python
# src/schemas/hypothesis.py（已有）

class MutationOperator(str, Enum):
    ADD_OPERATOR = “add_operator”
    REMOVE_OPERATOR = “remove_operator”
    SWAP_HORIZON = “swap_horizon”
    CHANGE_NORMALIZATION = “change_normalization”
    ALTER_INTERACTION = “alter_interaction”
```

### 10.3 QlibFormulaAST

Qlib 公式是括号嵌套的前缀表达式，解析规则：

```
formula  = field | operator “(“ args “)”
args     = formula (“,” formula)*
field    = “$” identifier
operator = identifier
```

```python
# src/hypothesis/mutation.py

@dataclass
class FormulaNode:
    “””Qlib 公式 AST 节点”””
    op: str                            # 算子名 或 字段名（如 “$close”）
    args: List[“FormulaNode”]          # 子节点
    param: Optional[int] = None        # 窗口参数（如 Ref(..., 5) 中的 5）

    def to_formula(self) -> str:
        “””将 AST 序列化回 Qlib 公式字符串”””
        if not self.args:
            return self.op
        args_str = “, “.join(a.to_formula() for a in self.args)
        if self.param is not None:
            return f”{self.op}({args_str}, {self.param})”
        return f”{self.op}({args_str})”


class QlibFormulaParser:
    “””将 Qlib 公式字符串解析为 FormulaNode AST”””

    def parse(self, formula: str) -> FormulaNode:
        tokens = self._tokenize(formula)
        return self._parse_expr(iter(tokens))
```

### 10.4 SymbolicMutator

```python
class MutationTrace(PixiuBase):
    “””记录一次 mutation 操作”””
    operator: MutationOperator
    original_formula: str
    mutated_formula: str
    description: str                   # 人类可读的描述


class SymbolicMutator:
    “””对公式 AST 施加 MutationOperator”””

    def mutate(
        self,
        formula: str,
        operator: MutationOperator,
        seed_note: Optional[FactorResearchNote] = None,
    ) -> Optional[MutationTrace]:
        “””
        返回 MutationTrace 或 None（mutation 不适用时）
        “””
        ast = QlibFormulaParser().parse(formula)
        mutated_ast = self._apply_operator(ast, operator)
        if mutated_ast is None:
            return None

        mutated_formula = mutated_ast.to_formula()
        return MutationTrace(
            operator=operator,
            original_formula=formula,
            mutated_formula=mutated_formula,
            description=self._describe(operator, formula, mutated_formula),
        )

    def _apply_operator(self, node: FormulaNode, op: MutationOperator) -> Optional[FormulaNode]:
        match op:
            case MutationOperator.SWAP_HORIZON:
                return self._swap_horizon(node)
            case MutationOperator.CHANGE_NORMALIZATION:
                return self._change_normalization(node)
            case MutationOperator.REMOVE_OPERATOR:
                return self._remove_outer_operator(node)
            case MutationOperator.ADD_OPERATOR:
                return self._add_cross_section_wrapper(node)
            case _:
                return None  # 其他 operator 暂返回 None

    def _swap_horizon(self, node: FormulaNode) -> FormulaNode:
        “””将所有窗口参数乘以 / 除以 2（随机选择），保持整数”””
        import copy, random
        result = copy.deepcopy(node)
        self._traverse_swap(result, factor=random.choice([0.5, 2.0]))
        return result

    def _change_normalization(self, node: FormulaNode) -> Optional[FormulaNode]:
        “””将最外层算子在 Rank / Zscore 之间切换”””
        if node.op == “Rank”:
            return FormulaNode(op=”Zscore”, args=node.args)
        if node.op == “Zscore”:
            return FormulaNode(op=”Rank”, args=node.args)
        return None

    def _remove_outer_operator(self, node: FormulaNode) -> Optional[FormulaNode]:
        “””移除最外层一元算子，返回其唯一子节点”””
        if len(node.args) == 1:
            return node.args[0]
        return None

    def _add_cross_section_wrapper(self, node: FormulaNode) -> FormulaNode:
        “””在公式外包一层 Rank”””
        return FormulaNode(op=”Rank”, args=[node])
```

### 10.5 SYMBOLIC_MUTATION 子空间路径

在 `AlphaResearcher` 中，当 assigned subspace 为 `SYMBOLIC_MUTATION` 时：

```python
# researcher.py

if subspace == “SYMBOLIC_MUTATION”:
    # 1. 从 FactorPool 取已有公式作为 seed
    seed_formulas = pool.get_recent_formulas(island=self.island, limit=5)
    if not seed_formulas:
        # 降级：无 seed 时走普通 LLM 路径
        return await self._llm_generate(prompt)

    # 2. 对每个 seed 尝试所有 MutationOperator
    mutator = SymbolicMutator()
    candidates = []
    for formula in seed_formulas:
        for op in MutationOperator:
            trace = mutator.mutate(formula, op)
            if trace:
                candidates.append(trace)

    # 3. 将 trace 转换为 FactorResearchNote
    notes = [self._trace_to_note(t) for t in candidates[:batch_size]]
    return notes
```

---

## 11. Regime Detection 模块（§2.5 实现规格）

### 11.1 设计目标

将 `market_regime` 从 LLM 自由填写，变成**规则引擎的确定性输出**。

Stage 1 负责检测并写入标准化 regime 标签，所有下游模块按此标签路由。

### 11.2 标准化 Regime 枚举

```python
# src/schemas/market_context.py（更新）

class MarketRegime(str, Enum):
    BULL_TREND = “bull_trend”             # 上涨趋势，低波动
    BEAR_TREND = “bear_trend”             # 下跌趋势，低波动
    HIGH_VOLATILITY = “high_volatility”   # 高波动（不区分方向）
    RANGE_BOUND = “range_bound”           # 横盘震荡
    STRUCTURAL_BREAK = “structural_break” # 结构性突破（政策冲击等）
```

`MarketContextMemo.market_regime: MarketRegime` 替换当前的自由字符串。

### 11.3 RegimeDetector

```python
# src/market/regime_detector.py

class RegimeSignals(PixiuBase):
    “””用于 regime 检测的市场信号”””
    index_close: List[float]              # 最近 N 日收盘（沪深 300 或全 A）
    volume: List[float]                   # 最近 N 日成交量
    date_range: int = 60                  # 使用的历史窗口（交易日）


class RegimeDetector:
    “””基于规则的 Regime 检测器”””

    # 阈值常量（可通过环境变量覆盖）
    TREND_MIN_RETURN = 0.08               # 60 日涨跌幅 > 8% → 趋势
    HIGH_VOL_THRESHOLD = 0.025            # 年化波动率 > 25% → 高波动（日波动 ~1.58%）
    RANGE_MAX_RETURN = 0.04               # 涨跌幅 < 4% → 震荡

    def detect(self, signals: RegimeSignals) -> MarketRegime:
        trend_return = self._compute_trend_return(signals.index_close)
        daily_vol = self._compute_daily_vol(signals.index_close)

        # 优先级：structural_break > high_volatility > trend > range
        if self._is_structural_break(signals):
            return MarketRegime.STRUCTURAL_BREAK
        if daily_vol > self.HIGH_VOL_THRESHOLD:
            return MarketRegime.HIGH_VOLATILITY
        if trend_return > self.TREND_MIN_RETURN:
            return MarketRegime.BULL_TREND
        if trend_return < -self.TREND_MIN_RETURN:
            return MarketRegime.BEAR_TREND
        return MarketRegime.RANGE_BOUND

    def _compute_trend_return(self, closes: List[float]) -> float:
        if len(closes) < 2:
            return 0.0
        return (closes[-1] - closes[0]) / closes[0]

    def _compute_daily_vol(self, closes: List[float]) -> float:
        import statistics, math
        if len(closes) < 5:
            return 0.0
        returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
        return statistics.stdev(returns)

    def _is_structural_break(self, signals: RegimeSignals) -> bool:
        “””检测近 5 日波动明显高于前 55 日（结构突破信号）”””
        closes = signals.index_close
        if len(closes) < 10:
            return False
        recent_vol = self._compute_daily_vol(closes[-5:])
        prior_vol = self._compute_daily_vol(closes[-60:-5])
        return prior_vol > 0 and recent_vol / prior_vol > 2.5
```

### 11.4 Stage 1 集成

`MarketAnalyst` 在调用 LLM 生成上下文前，先运行 `RegimeDetector`：

```python
# market_analyst.py

detector = RegimeDetector()
regime = detector.detect(signals)
# 将 regime 写入 MarketContextMemo，LLM 只负责生成 raw_summary 等文本
memo = MarketContextMemo(
    market_regime=regime,
    ...
)
```

`market_regime` 字段不再由 LLM 填写，改为检测器产出。LLM 可在 prompt 中看到检测结果，用于生成叙事部分。

### 11.5 Stage 3 集成

Prefilter 新增 regime 过滤：若 `FactorResearchNote.invalid_regimes` 包含当前 regime，硬拒绝：

```python
# prefilter.py — AlignmentChecker 中增加

current_regime = state.market_context.market_regime
if current_regime and note.invalid_regimes:
    if current_regime.value in note.invalid_regimes:
        return False, f”Factor invalid in current regime: {current_regime.value}”
```

### 11.6 数据依赖

`RegimeDetector` 需要指数收盘价序列。优先顺序：

1. `MarketAnalyst` 调用 akshare 时顺手传入（推荐路径）
2. 无数据时降级：`MarketRegime.RANGE_BOUND`（保守默认）

---

## 12. 文档索引

| 主题 | 文档 |
|------|------|
| Phase 2 整体执行计划 | `docs/archive/plans/phase-2-hypothesis-engine.md` |
| FailureConstraint 设计 | `docs/design/17_failure-constraint.md` |
| SynthesisAgent 设计 | `docs/design/18_synthesis-agent.md` |
| Factor Algebra 原语注册表 | 本文 §9 |
| Symbolic Mutation 运行时 | 本文 §10 |
| Regime Detection 模块 | 本文 §11 |
| 当前实现偏差 | `docs/overview/05_spec-execution-audit.md` |
