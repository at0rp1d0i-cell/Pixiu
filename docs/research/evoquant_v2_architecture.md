# EvoQuant v2 架构设计：LLM 原生量化研究漏斗

> 创建：2026-03-07
> 状态：讨论中，待确认

---

## 核心设计原则

### 从"模仿人类团队"到"LLM 原生设计"

传统量化基金的瓶颈是**人力**（研究员每天读10份报告，开发需要几天实现因子）。
LLM 系统的瓶颈是**Qlib 回测执行时间**（5-10分钟/次）。

因此，最优设计不是线性管线，而是**高通量漏斗**：用 LLM 廉价阶段大量生成候选，逐层筛选，只把最有希望的推进到昂贵的回测阶段。

| 优势 | 人类团队 | LLM 系统 |
|---|---|---|
| 阅读速度 | 5-10份/天 | 数百份/轮，近乎免费 |
| 并行假设 | 1个研究员=1个方向 | N个Researcher并行，成本线性 |
| 跨域知识 | 需开会协调 | 单个LLM同时整合多领域 |
| 探索性分析 | 需要几天 | 分钟级生成EDA脚本 |

---

## 学术参考

| 论文 | 核心贡献 | 与本设计的关联 |
|---|---|---|
| AlphaAgent (arXiv:2502.16789) | 三维前置过滤漏斗（复杂度/语义对齐/新颖性）| Stage 3 前置过滤 |
| RD-Agent (arXiv:2505.15155) | 文档驱动接口，Research→Development分离 | 核心接口设计 |
| QuantaAlpha (arXiv:2602.07085) | 探索性轨迹变异+语义一致性约束 | Exploration Agent |
| CogAlpha (arXiv:2511.18850) | 七层智能体层次+21个Agent的质量检验 | Agent 团队设计参考 |
| QuantAgent (arXiv:2402.03755) | 双循环：内循环精炼+外循环市场验证 | Island 进化外循环 |
| AlphaGen (KDD 2023) | Python RL+LLM 混合因子挖掘 | 开源实现参考 |

---

## 漏斗架构（五阶段）

```
════════════════════════════════════════════════════════════════
  Stage 1: 宽扫描                        [成本：极低]
════════════════════════════════════════════════════════════════
  输入：新闻 RSS / AKShare 实时数据 / FactorPool 历史

  Market Analyst    → 每日 MarketContextMemo（宏观/北向/热点）
  Literature Miner  → 从 FactorPool + 学术库检索相关历史因子
  Data Scanner      → 原始数据中的统计异常点

  输出：MarketContextMemo（结构化）
════════════════════════════════════════════════════════════════
  Stage 2: 并行假设生成                  [成本：低，可大量并行]
════════════════════════════════════════════════════════════════
  输入：MarketContextMemo + Island 上下文 + FactorPool

  Alpha Researcher × N（每个 Island 一个，并行）
  → 生成 FactorResearchNote（含经济直觉+探索性问题+初步公式方向）

  Synthesis Agent → 检测跨 Island 的关联假设

  输出：批量 FactorResearchNote（初版）
════════════════════════════════════════════════════════════════
  Stage 3: 前置过滤（三维）              [成本：低，无回测]
════════════════════════════════════════════════════════════════
  输入：批量 FactorResearchNote

  Filter A - Validator：Qlib 语法 + A股硬约束（T+1/Ref符号/Log安全）
  Filter B - Novelty：AST 相似度 vs FactorPool（防止重复探索）
  Filter C - Alignment：LLM 检验经济直觉与公式方向的语义一致性

  通过 Top K（默认 K=5），淘汰明显无效的

  输出：精选 FactorResearchNote 列表
════════════════════════════════════════════════════════════════
  Stage 4: 执行                          [成本：高，限流入]
════════════════════════════════════════════════════════════════
  输入：精选 FactorResearchNote

  Exploration Agent（按需调用）：
  → 接收 Researcher 的探索性问题（"高换手时动量效应如何？"）
  → 生成 pandas/numpy EDA 脚本 → Docker 沙箱执行 → 返回统计结果
  → 结果反馈给 Researcher，帮助确定最终 Qlib 公式

  Coder（确定性执行）：
  → 接收最终 Qlib 公式 → 填入回测模板 → Docker 执行
  → 解析 stdout JSON → 返回 BacktestReport

  输出：BacktestReport（结构化，含 Sharpe/IC/ICIR/换手率）
════════════════════════════════════════════════════════════════
  Stage 5: 判断与综合                    [成本：低]
════════════════════════════════════════════════════════════════
  输入：BacktestReport

  Critic：多维评估（Sharpe>2.67 AND IC>0.02 AND ICIR>0.3 AND 换手率<50%）
  Risk Auditor：过拟合检测 + 与现有因子相关性

  [通过] → FactorPool 注册 → Portfolio Manager 更新组合
  [失败] → 失败归因 → 写回 FactorPool（error-driven RAG）→ 反馈 Stage 2

  Portfolio Manager：跨 Island 因子组合 + 权重分配
  Report Writer：生成 CIO 可读报告 → interrupt() 等待审批
════════════════════════════════════════════════════════════════
```

---

## Agent 团队完整清单

### Research Group（Stage 1-2）
| Agent | 模型建议 | 职责 |
|---|---|---|
| Market Analyst | deepseek-chat | 每日 context memo：北向/宏观/新闻 |
| Literature Miner | deepseek-chat | FactorPool RAG + 学术因子检索 |
| Alpha Researcher × N | deepseek-chat | 并行假设生成（每 Island 一个） |
| Synthesis Agent | deepseek-chat | 跨 Island 关联发现 |

### Screening Group（Stage 3）
| Agent | 模型建议 | 职责 |
|---|---|---|
| Validator | 规则引擎（无LLM） | Qlib语法 + A股硬约束 |
| Novelty Filter | 向量相似度（无LLM） | AST 相似度 vs FactorPool |
| Alignment Checker | 小模型（快速） | 语义一致性验证 |

### Execution Group（Stage 4）
| Agent | 模型建议 | 职责 |
|---|---|---|
| Exploration Agent | GLM-5 / deepseek-chat | EDA 脚本生成 + 沙箱执行 |
| Coder | 确定性模板（无LLM主体） | Qlib 公式 → 回测脚本 → 执行 |

### Judgment Group（Stage 5）
| Agent | 模型建议 | 职责 |
|---|---|---|
| Critic | 规则引擎 + LLM 归因 | 通过/拒绝 + 失败原因 |
| Risk Auditor | 统计模型 | 过拟合检测 + 因子相关性 |
| Portfolio Manager | deepseek-chat | 跨 Island 组合优化 |
| Report Writer | claude-sonnet | 生成 CIO 报告 |

---

## 关键接口契约（文档驱动）

### MarketContextMemo
```json
{
  "date": "2026-03-07",
  "northbound_flow": {"net_buy_bn": 12.3, "top_sectors": ["科技", "消费"]},
  "macro_signals": ["美联储暂停加息", "PMI超预期"],
  "hot_themes": ["AI算力", "红利"],
  "suggested_directions": ["momentum", "northbound"]
}
```

### FactorResearchNote
```json
{
  "island": "momentum",
  "hypothesis": "AI算力板块资金持续流入时，短期动量效应更强",
  "economic_intuition": "机构资金集中买入形成趋势惯性",
  "exploration_questions": ["高换手时动量效应是否衰减？"],
  "proposed_formula": "($close/Ref($close,20)-1) / Mean($volume/Mean($volume,60),20)",
  "universe": "csi300",
  "expected_ic_range": [0.02, 0.05],
  "risk_factors": ["趋势反转", "换手率突变"]
}
```

### BacktestReport
```json
{
  "factor_id": "momentum_20260307_001",
  "formula": "...",
  "metrics": {
    "sharpe": 2.81,
    "ic_mean": 0.031,
    "icir": 0.42,
    "turnover": 0.35
  },
  "passed": true,
  "failure_mode": null
}
```

---

## 人机交互设计

### 产品形态
- **Terminal CLI**（主要）：`evoquant run --mode evolve`，流式输出研究进度
- **Web Dashboard**（后台监控）：因子池状态、Island 进度、异常警报（后台自动运行时使用）

### 人类介入层次（三层）
1. **自动层**：Stage 1-4 全自动，无需人类介入
2. **通知层**：异常警报（系统崩溃、连续失败 > 10 次、Sharpe 大幅下跌）
3. **审批层**：Report Writer 生成报告后 `interrupt()`，CIO 审批 → `/approve` `/redirect` `/stop`

---

## 实施路线图

### Phase 2B（当前，优先完成）
- [ ] 运行 20 轮进化循环，验证基础 Pipeline
- [ ] 修复 Coder 执行层（去掉 Claude Code，改为模板+subprocess）
- [ ] 规范化 FactorResearchNote schema

### Phase 3（下一步）
- [ ] 实现 Market Analyst + Literature Miner（Stage 1）
- [ ] 实现 Stage 3 三维前置过滤
- [ ] 实现 Exploration Agent（EDA 探索）
- [ ] Terminal CLI + Web Dashboard 双模式

### Phase 4（未来）
- [ ] Portfolio Manager 跨 Island 组合优化
- [ ] Report Writer + LangGraph interrupt()
- [ ] 券商 API 实盘对接
