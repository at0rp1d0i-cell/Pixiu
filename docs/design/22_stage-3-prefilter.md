# Pixiu v2 Stage 3：前置过滤层规格
Purpose: Define the Stage 3 hard-gate chain before expensive execution, with a single canonical truth for formula legality and math safety.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-22

> 版本：2.1
> 创建：2026-03-07
> 前置依赖：`11_interface-contracts.md`
> 文件位置：`src/agents/prefilter.py`、`src/formula/semantic.py`

---

## 1. 职责

Stage 3 的职责是在进入昂贵 Stage 4 之前，对 `FactorResearchNote` 做硬 gate。

目标不是“帮 Stage 2 修公式”，而是：

- 拒绝不合法或不安全的公式
- 拒绝过于重复的候选
- 拒绝与假设不一致或与 regime 明显冲突的候选
- 只放行少量更值得进入确定性执行的对象

Stage 3 是收缩层，不是修补层。

---

## 2. 唯一真相

Stage 3 的 canonical runtime path 是：

- `src/agents/prefilter.py` 中的 `Validator.validate()`
- `src/formula/semantic.py` 中的 `parse_and_check_ast()`

当前口径：

- 字段合法性来自 runtime capability manifest
- 算子合法性来自 runtime capability manifest
- 语法、参数个数和数学安全由 AST 语义检查统一裁决

`src/agents/validator.py` 是历史遗留实现，不是 Stage 3 的 canonical runtime。

如果文档、prompt、测试和 runtime 冲突，先以这条主链为准，再回写文档。

---

## 3. Fail-closed 数学安全

Stage 3 对数学安全采用 `fail-closed`：

- 如果不能证明公式安全，就拒绝
- 不做自动改写
- 不做 silent repair
- 不在 Stage 3 替模型补公式

这意味着：

- `Researcher` 必须直接产出符合当前 canonical 约束的公式
- Stage 3 只判断是否放行，不负责把危险公式“修成安全公式”

当前需要被硬 gate 的典型约束：

- `Ref($close, -N)` 这类未来数据引用必须拒绝
- `Div` / `Mod` 的分母如果可能为零，必须拒绝
- `Log()` 的参数如果不能证明严格大于零，必须拒绝
- `Sqrt()` 的参数如果可能为负，必须拒绝
- 未注册字段、未批准算子、未知裸标识符必须拒绝

文档、提示词和测试不应继续传播：

- “自动加 `+1` 就安全”的旧叙事
- “Stage 3 会替你加 `Max(..., 1e-8)`”的旧叙事

只有 runtime 真正接受的 canonical 写法，才可以出现在 prompt 和测试里。

---

## 4. 过滤链

### Filter A：Validator（active, hard gate）

职责：

- 做公式合法性与数学安全检查
- 依赖 runtime capability manifest
- 依赖 AST 语义检查

返回：

- `(passed: bool, reason: str)`

如果失败，直接拒绝。

### Filter B：NoveltyFilter（active, hard gate）

职责：

- 基于公式 token / AST 近似，拒绝与历史对象过度相似的候选

当前实现：

- 从 `FactorPool` 读取同岛历史对象
- 使用 Jaccard 相似度做轻量重复检测

### Filter C：AlignmentChecker（active, soft-on-failure）

职责：

- 快速判断假设与公式是否语义一致

当前实现：

- 可使用小模型做快速 JSON 判断
- 如果 checker 自身调用失败，默认放行，不因辅助检查阻塞主流程

### Filter D：ConstraintChecker（active, hard gate for `severity=hard`）

职责：

- 消费历史失败约束
- 优先拦截已知坏模式

当前实现：

- `severity=hard` 的约束直接拒绝
- warning 级别保留给上游 prompt 或报告，不在此层一刀切

### Filter E：RegimeFilter（active, conditional hard gate）

职责：

- 当 note 显式声明 `applicable_regimes` / `invalid_regimes` 时，检查与当前 `MarketContextMemo.market_regime` 的兼容性

当前实现：

- regime 缺失时放行
- note 未声明 regime 时放行
- 明确不兼容时拒绝

---

## 5. Diagnostics

Stage 3 应输出结构化 `prefilter_diagnostics`，至少包含：

- `input_count`
- `approved_count`
- `rejection_counts_by_filter`
- `sample_rejections`

诊断的目标是帮助快速定位“为什么被拒绝”，不是替代完整审计存档。

---

## 6. Prompt / 测试 / Runtime 一致性要求

以下三层必须共享同一口径：

- `Researcher` 公式生成提示词
- `tests/test_prefilter.py` 等测试样例
- `Validator.validate() -> parse_and_check_ast()` runtime 主链

不得出现：

- prompt 鼓励一种写法，而 runtime 拒绝
- 测试通过一种安全叙事，而 runtime 实际不接受
- 文档仍把 legacy validator 当作 Stage 3 主入口

---

## 7. 实现收口要求

当前主线应按这个顺序推进：

1. 明确 `PreFilter.Validator -> parse_and_check_ast` 为唯一真相
2. 把 prompt、docs、tests 收口到同一数学安全语义
3. 把 legacy `src/agents/validator.py` 从主路径和高信任文档里退出
4. 只在 canonical path 上继续补数学安全与算子签名测试

---

## 8. 测试要求

至少应覆盖以下场景：

- `Ref($close, -N)` 被拒绝
- `Log()` 危险定义域被拒绝
- 可能除零的分母被拒绝
- 未注册字段和未批准算子被拒绝
- alignment checker 失败时批次仍可继续
- novelty / constraint / regime 的拒绝原因会进入结构化 diagnostics
