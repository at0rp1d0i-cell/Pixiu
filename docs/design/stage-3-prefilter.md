# Pixiu v2 Stage 3：前置过滤层规格

> 版本：2.0
> 创建：2026-03-07
> 前置依赖：`interface-contracts.md`
> 文件位置：`src/agents/prefilter.py`（扩展现有 `validator.py`）

---

## 1. 职责

在进入昂贵回测（Stage 4）之前，用三个串行过滤器筛选 `FactorResearchNote` 批次，只放行 Top K（默认 K=5）最有潜力的候选。

**无回测，无 LLM（前两个过滤器），成本极低。**

---

## 2. 三个过滤器

### Filter A：Validator（A 股硬约束，已有，扩展）

**现有代码**：`src/agents/validator.py`（保留，迁移到新接口）

检查规则（从现有代码迁移，补充新规则）：
```
1. Qlib 字段名合法性：只允许 $close, $open, $high, $low, $volume, $factor
2. Ref() 偏移符号：Ref($close, -N) 是未来数据，必须拒绝（只允许正整数）
3. Log() 安全性：Log 参数必须保证 > 0（检查是否有 +1 保护）
4. 括号匹配：所有 ([ 必须有对应 )]
5. 算子白名单：表达式只能使用 approved_operators 列表中的算子
   approved_operators = [
       "Mean", "Std", "Var", "Max", "Min", "Sum",
       "Ref", "Delta", "Slope", "Rsquare", "Resi",
       "Rank", "Abs", "Sign",
       "Log", "Power", "Sqrt",
       "Corr", "Cov",
       "If", "Gt", "Lt", "Ge", "Le", "Eq", "Ne",
       "And", "Or", "Not",
       "Add", "Sub", "Mul", "Div",
       "IdxMax", "IdxMin", "Comb", "Count", "Mad",
       "WMA", "EMA",
   ]
6. 公式非空且长度合理（5 < len < 500 字符）
```

**接口（更新为新 schema）**：
```python
from src.schemas.research_note import FactorResearchNote

def validate(note: FactorResearchNote) -> tuple[bool, str]:
    """
    返回 (passed: bool, reason: str)
    passed=False 时 reason 说明拦截原因
    """
    formula = note.final_formula or note.proposed_formula
    # ... 规则检查逻辑 ...
```

---

### Filter B：NoveltyFilter（新颖性过滤，新增）

**目标**：防止重复探索已有因子，提高研究效率。

**实现方式**：AST 相似度（不用向量，用字符串/token 级别相似度即可）

```python
# src/agents/prefilter.py

import ast
import re
from src.factor_pool.pool import FactorPool

class NoveltyFilter:
    def __init__(self, pool: FactorPool, threshold: float = 0.3):
        """
        threshold：AST 相似度超过此值则认为是重复因子
        值越低，筛选越严格（0.3 = 允许30%相似度）
        """
        self.pool = pool
        self.threshold = threshold

    def check(self, note: FactorResearchNote) -> tuple[bool, str]:
        formula = note.final_formula or note.proposed_formula
        tokens_new = self._tokenize(formula)

        # 从 FactorPool 获取同 Island 的历史因子
        existing = self.pool.get_island_factors(
            island=note.island,
            limit=50,
        )

        for existing_factor in existing:
            tokens_existing = self._tokenize(existing_factor["formula"])
            similarity = self._jaccard(tokens_new, tokens_existing)
            if similarity > self.threshold:
                return False, (
                    f"与已有因子 {existing_factor['factor_id']} 相似度过高 "
                    f"({similarity:.2f} > {self.threshold})，"
                    f"已有因子：{existing_factor['formula'][:80]}"
                )

        return True, "通过新颖性检查"

    def _tokenize(self, formula: str) -> set:
        """
        将 Qlib 公式分解为 token 集合。
        例："Mean(Abs($close/Ref($close,1)-1), 20)"
        → {"Mean", "Abs", "$close", "Ref", "1", "20"}
        """
        # 提取算子名、字段名、数字常量
        tokens = set(re.findall(r'\$\w+|[A-Za-z]+|\d+', formula))
        return tokens

    def _jaccard(self, a: set, b: set) -> float:
        if not a and not b:
            return 1.0
        return len(a & b) / len(a | b)
```

---

### Filter C：AlignmentChecker（语义一致性，新增）

**目标**：检验公式与经济直觉是否一致，拦截"公式看起来合法但与假设无关"的情况。

**实现**：LLM 快速调用（使用小/快速模型，如 deepseek-chat，温度=0）

```python
# src/agents/prefilter.py（续）

ALIGNMENT_PROMPT = """你是量化因子审核员。判断以下因子的经济假设与公式是否一致。

假设：{hypothesis}
公式：{formula}

判断标准：
- 公式的计算逻辑是否能捕捉假设描述的市场现象？
- 公式的时间窗口和操作符是否与假设的持仓周期 / 观测窗口匹配？

只输出 JSON，不输出其他内容：
{{"aligned": true/false, "reason": "一句话说明"}}
"""

class AlignmentChecker:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=os.getenv("RESEARCHER_MODEL", "deepseek-chat"),
            base_url=os.getenv("RESEARCHER_BASE_URL"),
            api_key=os.getenv("RESEARCHER_API_KEY"),
            temperature=0,
            max_tokens=200,  # 输出很短
        )

    async def check(self, note: FactorResearchNote) -> tuple[bool, str]:
        formula = note.final_formula or note.proposed_formula
        prompt = ALIGNMENT_PROMPT.format(
            hypothesis=note.hypothesis[:300],
            formula=formula,
        )

        try:
            response = await self.llm.ainvoke(prompt)
            import json
            result = json.loads(response.content.strip())
            return result["aligned"], result["reason"]
        except Exception as e:
            # AlignmentChecker 失败时放行（不因辅助检查阻塞主流程）
            return True, f"AlignmentChecker 调用失败，跳过：{e}"
```

---

## 3. 三维过滤器的组合执行

```python
# src/agents/prefilter.py

from src.schemas.thresholds import THRESHOLDS

class PreFilter:
    def __init__(self, factor_pool: FactorPool):
        self.validator = Validator()
        self.novelty = NoveltyFilter(pool=factor_pool, threshold=THRESHOLDS.min_novelty_threshold)
        self.alignment = AlignmentChecker()

    async def filter_batch(
        self,
        notes: list[FactorResearchNote],
    ) -> tuple[list[FactorResearchNote], int]:
        """
        返回 (approved_notes, filtered_count)
        approved_notes 数量 <= THRESHOLDS.stage3_top_k
        """
        candidates = []

        for note in notes:
            formula = note.final_formula or note.proposed_formula

            # Filter A（同步，最快）
            passed, reason = self.validator.validate(note)
            if not passed:
                logger.info(f"[Filter A] 拒绝 {note.note_id}: {reason}")
                continue

            # Filter B（同步，无 LLM）
            passed, reason = self.novelty.check(note)
            if not passed:
                logger.info(f"[Filter B] 拒绝 {note.note_id}: {reason}")
                continue

            # Filter C（异步，LLM）
            passed, reason = await self.alignment.check(note)
            if not passed:
                logger.info(f"[Filter C] 拒绝 {note.note_id}: {reason}")
                continue

            candidates.append(note)

        # 如果通过数量 > Top K，按优先级排序后截断
        # 优先级规则：有 exploration_questions 的排后（先回测简单的）
        candidates.sort(key=lambda n: len(n.exploration_questions))
        approved = candidates[:THRESHOLDS.stage3_top_k]
        filtered_count = len(notes) - len(approved)

        logger.info(
            f"[Stage 3] {len(notes)} 个候选 → "
            f"{len(approved)} 个通过（淘汰 {filtered_count} 个）"
        )
        return approved, filtered_count
```

---

## 4. 测试要求

扩展 `tests/test_validator.py`，新增：

```python
# 现有测试保留，新增以下

def test_novelty_filter_identical_formula():
    """与 FactorPool 中完全相同的公式应被拒绝"""

def test_novelty_filter_similar_formula():
    """相似度超过阈值的公式应被拒绝"""

def test_novelty_filter_novel_formula():
    """全新公式应通过"""

def test_alignment_checker_consistent():
    """公式与假设一致时应返回 aligned=True"""

def test_alignment_checker_failure_graceful():
    """AlignmentChecker LLM 调用失败时应放行（不阻塞流程）"""

def test_prefilter_top_k_limit():
    """通过的候选数量不超过 THRESHOLDS.stage3_top_k"""

def test_prefilter_empty_result():
    """全部被过滤时返回空列表，不报错"""
```

---

## 5. 与 v1 的差异

| 对比项 | v1 Validator | v2 PreFilter |
|---|---|---|
| 过滤维度 | 1（语法规则）| 3（语法 + 新颖性 + 语义对齐）|
| 输入 | `factor_hypothesis` dict | `FactorResearchNote` Pydantic 模型 |
| 输出 | boolean | `(approved_notes, filtered_count)` |
| Novelty | 无 | AST Jaccard 相似度 vs FactorPool |
| 语义检查 | 无 | LLM 快速调用（可降级）|
| Top K 限流 | 无 | 最多放行 K=5 个进回测 |
