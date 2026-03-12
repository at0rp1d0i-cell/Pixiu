# Pixiu v2 反思系统（Reflection System）

> 版本：2.0
> 创建：2026-03-09
> 前置依赖：`.../overview/architecture-overview.md`、`interface-contracts.md`
> 状态：**Planned**

---

## 1. 设计动机

FactorPool 只存储结果（公式、Sharpe、失败原因），缺少过程知识。反思系统让 AlphaResearcher 具备跨轮学习能力，记录“为什么失败”和“哪些发现值得复用”。

---

## 2. 三层生命周期

```
Layer 1：动态反思（Dynamic）
  存储：data/reflections/dynamic/{island}/
  内容：单个因子的失败/成功经验（50-200 字）
  生命周期：2-4 周，可修改
  触发：满足触发条件（见 3）后由 ReflectionAgent 生成

Layer 2：元反思（Meta）
  存储：data/reflections/meta/{island}/
  内容：聚合 N 条动态反思后的模式识别结论
  生命周期：1-3 个月
  触发：每 10-20 轮，ReflectionAgent 主动扫描整理（非被动）

Layer 3：永久 Skills（Permanent）
  存储：knowledge/skills/discovered/（私有仓库）
  内容：从元反思沉淀出的永久规范，注入 AlphaResearcher system prompt
  生命周期：永久（除非市场制度变化）
  触发：月度总结时，ReflectionAgent 提案 → BP-5 断点人工审批
  格式：YAML，含 version、evidence、expiration_condition 字段
```

---

## 3. 触发条件

`CriticVerdict` 新增两个字段：

- `strategy_validity: bool`
- `novelty_score: float`

| Sharpe | strategy_validity | novelty_score | 触发类型 |
|---|---|---|---|
| 失败 | False（策略有误）| 任意 | `failure_learning` |
| 失败 | True（策略无误）| 任意 | 不触发 |
| 成功 | True | > 0.3（新颖）| `success_recording` |
| 成功 | True | ≤ 0.3（平庸）| 不触发 |

目标是主动筛选，避免把市场噪音写成经验库。

---

## 4. 版本化存储

```
git（文本版本化）：
  每次修改产生 commit，保留演化历史
  commit message："reflection(momentum): refine factor_abc based on Round 23"
  时间线元数据存储为 JSON sidecar（factor_abc_timeline.json）

ChromaDB（语义检索）：
  只存储当前版本（最新状态）+ embedding
  AlphaResearcher RAG 检索时命中当前最优版本

反思可以被"修改"而非简单"删除"：
  追加新条件
  升级为元反思
  标注为"已被后续实验推翻"
```

---

## 5. 冷启动期策略

**Day 1-30（冷启动期）**：使用 deepseek-reasoner 深度推理每条反思，token 成本更高，但优先建立高质量反思库。

**Day 30+（常规期）**：切换 deepseek-chat 做浅反思，deepseek-reasoner 仅在月度汇总时使用。

---

## 6. 实施备注

- 该系统尚未进入当前主运行时，属于架构前瞻规格。
- 在进入实现前，应先完成 Stage 4/5 的基础闭环和测试管线收敛。
