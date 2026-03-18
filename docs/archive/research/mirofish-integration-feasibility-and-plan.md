# Pixiu × MiroFish 集成可行性分析与落地方案（v1.1 对齐版）

> ⚠️ **此文档已被 v2 设计取代**
> 当前有效方案：参见 `docs/plans/current_implementation_plan.md` Phase 3D（MiroFish 协议层）
> v1 定位（情绪管道）已被证明与 MiroFish 实际能力不符，保留仅供参考。

---

> 目标：在不破坏 Pixiu 当前主线收敛节奏的前提下，评估并设计 MiroFish 的可执行集成路径。
> 结论先行：**可行性中高，推荐 v1 采用 offline-first（离线批处理特征）集成**。

---

## 1. 背景与目标

Pixiu 当前是 A 股量化研究漏斗系统，主链路围绕 Stage 1→5 运行。项目近期重点不是“增加更多能力点”，而是“收敛边界、稳定执行路径与测试入口”。

本报告回答三个问题：

1. MiroFish 是否适合融合到 Pixiu？
2. 以何种方式融合风险最低、收益最高？
3. 如何让方案与 Pixiu 官方文档主线优先级保持一致？

本报告同时给出：
- 模式对比（离线批处理 / 在线微服务 / 嵌入式）
- v1 推荐架构
- Gate-0 + Week1~Week4 分阶段方案
- 量化验收门槛（Quant / Reliability / Cost）

---

## 2. MiroFish 能力画像（能力 / 依赖 / 部署）

### 2.1 核心能力

MiroFish 本质是一个 LLM 驱动的多智能体仿真与分析系统，适合“信息理解、叙事推演、情境预测”。其优势在于结构化地把新闻/政策/舆情转为可分析对象，而不是直接替代回测引擎。

### 2.2 运行时与依赖特征

| 维度 | 观察 | 对 Pixiu 的含义 |
|---|---|---|
| 依赖栈 | Python + Flask + OpenAI 兼容 LLM + Zep + OASIS/CAMEL | 外部依赖较重，不适合直接侵入 Pixiu 执行层 |
| 成本形态 | LLM 调用密集 | 在线强耦合会放大成本不确定性 |
| 可重复性 | 受 LLM 随机性影响 | 必须通过离线快照 + 版本化补足可复现性 |
| 部署方式 | 独立服务更自然 | 适合做“上游特征生产器”，不适合直接改 Stage4/5 |

### 2.3 许可证与合规边界

- MiroFish 与 Pixiu 均为 AGPL-3.0。  
- 当前目标为内部使用场景，合规风险可控，但仍需保留依赖与版本审计链路。

---

## 3. Pixiu 当前架构与约束（含路径证据）

以下约束来自当前有效文档（不使用 archive 作为主真相）：

- `AGENTS.md`
- `docs/overview/05_spec-execution-audit.md`
- `docs/plans/current_implementation_plan.md`
- `docs/design/21_stage-2-hypothesis-expansion.md`
- `docs/design/25_stage-45-golden-path.md`
- `docs/design/15_data-sources.md`
- `docs/design/16_test-pipeline.md`

### 3.1 非协商约束（Non-negotiables）

1. 优先级顺序明确：文档/规格准确 → 测试收敛 → Stage4 单路径收敛 → Stage5 对齐 → 再扩数据源面（`AGENTS.md`）。
2. Stage 4→5 必须维持 deterministic golden path（`25_stage-45-golden-path.md`）。
3. Stage 2 是当前战略重点：扩大 hypothesis space，不扩大 execution power（`21_stage-2-hypothesis-expansion.md`）。
4. Layer 4（新闻/情绪）默认用于 Agent 上下文，不默认直接进入回测公式（`15_data-sources.md`）。
5. 必须遵守 point-in-time 防前视：**`available_time <= decision_time`**。
6. 测试分层必须遵守 smoke/unit/integration/live/e2e 体系，默认 merge gate 不依赖 live/e2e（`16_test-pipeline.md`）。

### 3.2 对集成意味着什么

- MiroFish 在 v1 应定位为 **Layer 4 上下文增强 + 离线特征快照生产**。
- v1 不应改变 Stage4/5 的唯一 deterministic 执行真路径。

---

## 4. 集成可行性结论（高/中/低）

**结论：中高（Medium-High）**。

原因：

- 正向：
  - Pixiu 已有 sentiment/上下文相关链路，天然存在接入位点；
  - MiroFish 在“信息结构化与叙事推演”上有增益；
  - 离线集成可把随机性和成本风险隔离在上游。
- 约束：
  - 当前 Pixiu 主线优先级是收敛 Stage4/5，不宜大规模扩面；
  - 在线强耦合将放大漂移风险、成本风险与故障传播。

因此，“可行”不等于“马上全量在线接入”，而是“可按收敛优先级做分阶段接入”。

---

## 5. 可选集成模式对比

| 模式 | 描述 | 优点 | 风险 | 适配 Pixiu 当前阶段 |
|---|---|---|---|---|
| 离线批处理（推荐） | MiroFish 离线生成特征快照，Pixiu按批消费 | 可复现、可审计、低耦合、便于防泄漏 | 不是秒级响应 | **高** |
| 在线微服务 | Pixiu 运行时实时调用 MiroFish API | 实时性强、反馈快 | 成本/时延/稳定性压力高，易扩散到执行层 | 中低 |
| 嵌入式（库级） | 直接把 MiroFish 模块嵌入 Pixiu | 理论上调用直接 | 依赖链重、升级困难、边界易混 | 低 |

结论：v1 选离线批处理最符合 Pixiu 的当前演进秩序。

---

## 6. 推荐方案（v1 offline-first）

### 6.1 架构定位

```
MiroFish (offline producer)
  -> 结构化特征快照（版本化）
  -> Pixiu Stage1/2 上下文消费 + 受控特征桥接
  -> Stage3/4/5 按现有 deterministic 路径执行
```

### 6.2 关键设计原则

1. **不改 Stage4/5 单路径执行真值**。  
2. **先 context 增强，后回测字段扩展**（回测扩展设条件触发）。  
3. **先版本化快照，再进入研究/回测链路**。  
4. 所有 join 均执行 `available_time <= decision_time`。  

### 6.3 特征范围（v1）

- 情绪方向/强度
- 事件热度/传播速度
- 主体分歧度
- 政策/监管标签

---

## 7. 与 Pixiu 官方文档主线对比矩阵

| 维度 | 官方主线要求 | 本方案状态 | 说明 |
|---|---|---|---|
| 收敛优先级 | 先 Stage4/5 收敛，再扩数据源 | 对齐（需 Gate-0） | 增加 Gate-0 保证启动时机 |
| Stage 2 重点 | 假设空间扩展优先 | 对齐 | MiroFish 首先增强 Stage1/2 上下文与假设输入 |
| Stage4/5 边界 | deterministic 单路径 | 对齐 | v1 明确不改执行真路径 |
| 数据层边界 | Layer4 默认 context | 对齐 | v1 不直接把原始新闻喂回测 |
| 测试策略 | 分层，live/e2e 非默认门禁 | 对齐 | 新增测试优先 unit/integration |

### 7.1 冲突点与修正

| 潜在冲突 | 风险 | 修正建议 |
|---|---|---|
| 过早扩回测输入层 | 执行层漂移 | 将回测字段扩展放到 Gate C 后条件任务 |
| 上线即在线调用 | 成本与稳定性扩散 | v1 禁止在线阻塞依赖 |
| 测试门禁过重 | 阻塞开发节奏 | 默认 gate 维持 smoke/unit + 必要 integration |

---

## 8. 分阶段落地方案（Gate-0 + Week1~Week4）

### Gate-0（启动前置条件）

仅当以下条件满足，才启动 MiroFish 主集成波次：

1. Stage4/5 当前回归自检通过；
2. 测试入口稳定（至少 smoke/unit 绿）；
3. 本轮不引入 execution single-path 变更。

### Week 1：契约与确定性基线

- 定义特征契约与快照 manifest；
- 固化 determinism 配置与快照 hash 规则；
- 验证重复输入的一致性。

### Week 2：离线特征生产

- 实现四类特征抽取；
- 加入数据完整性与字段校验；
- 建立失败重试与错误归因。

### Week 3：Pixiu 集成（不改执行单路径）

- 进行 point-in-time join；
- 强化 Stage1/2 上下文输入；
- 仅在受控条件下准备回测桥接。

### Week 4：试点评估与决策

- 运行 4 周评估窗口统计；
- 对照 Quant / Reliability / Cost 门槛；
- 给出 go/no-go 与下一阶段建议。

---

## 9. 风险清单与缓解策略

| 风险 | 触发方式 | 缓解策略 |
|---|---|---|
| 前视偏差/泄漏 | 错误使用 event_time | 强制 `available_time <= decision_time` + 泄漏测试 |
| 结果不可复现 | LLM 非确定性 | 快照版本化、固定参数、重复运行 hash 校验 |
| 成本失控 | 在线高频调用 | v1 仅离线批处理，按日批次执行 |
| 架构漂移 | 侵入 Stage4/5 | 明确非目标：不改 execution single-path |
| 依赖不稳定 | 外部服务波动 | 与 Pixiu 主链解耦，失败时回退基线流程 |

---

## 10. 验收标准（Quant / Reliability / Cost）

| 维度 | 指标 | 通过阈值（建议） |
|---|---|---|
| Quant | OOS IC 或 rank-IC 提升 | 达到预设 uplift（如 IC +0.01 量级） |
| Reliability | 日级 E2E 成功率 | ≥ 95% |
| Reliability | 泄漏测试通过率 | 100% |
| Cost | 日增量计算/推理成本 | 不超过批准预算上限 |

> 注：阈值可按交易频率与资产池规模校准，但必须在试点前冻结。

---

## 11. 非目标与边界（v1 不做）

1. 不做实时交易执行联动。  
2. 不做对外服务化产品封装。  
3. 不将 MiroFish 直接嵌入 Stage4/5 执行路径。  
4. 不以 live/e2e 作为默认开发门禁。  
5. 不使用 `docs/archive/*` 作为当前架构依据。

---

## 12. 下一步执行建议

1. 先做 Gate-0 自检与资源排期。  
2. 以离线快照契约为第一交付物启动 Week 1。  
3. 将“回测字段扩展”设为条件任务，避免与 Stage4/5 收敛冲突。  
4. 建立试点日报：覆盖率、泄漏检查、IC 变化、成本曲线。  
5. Week4 结束后做 go/no-go：若 Quant 未达标，优先回溯特征定义与对齐逻辑，而非加大在线耦合。

---

## 参考证据（当前有效文档）

- `Pixiu/AGENTS.md`
- `Pixiu/docs/overview/05_spec-execution-audit.md`
- `Pixiu/docs/plans/current_implementation_plan.md`
- `Pixiu/docs/design/21_stage-2-hypothesis-expansion.md`
- `Pixiu/docs/design/25_stage-45-golden-path.md`
- `Pixiu/docs/design/15_data-sources.md`
- `Pixiu/docs/design/16_test-pipeline.md`
- `.sisyphus/plans/pixiu-mirofish-integration.md`
- `.sisyphus/drafts/pixiu-docs-scheme-comparison.md`
