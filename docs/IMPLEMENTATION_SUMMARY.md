"""
Stage 4→5 Golden Path 实施总结

按照 v2_stage45_golden_path.md 规格完成的实现
"""

## 已完成的组件

### 1. Schema 更新

#### src/schemas/backtest.py
- ✅ ExecutionMeta: 执行上下文元数据
- ✅ FactorSpecSnapshot: 因子规格快照
- ✅ BacktestMetrics: 最小充分指标集
- ✅ ArtifactRefs: 产物引用
- ✅ BacktestReport: Stage 4 唯一标准输出

#### src/schemas/judgment.py
- ✅ CriticVerdict: 确定性判定结果（decision, score, reason_codes）

#### src/schemas/thresholds.py
- ✅ 更新阈值配置（min_sharpe=0.8, max_drawdown=0.25, min_coverage=0.7）

#### src/schemas/factor_pool_record.py (新建)
- ✅ FactorPoolRecord: FactorPool 写回的最小结构

### 2. Stage 4: 执行层

#### src/execution/coder_v2.py (新建)
- ✅ 确定性 Coder 实现
- ✅ 四步流程：compile → run → save_artifacts → parse
- ✅ 错误分类：compile/run/parse/judge
- ✅ 产物落盘到 data/artifacts/{run_id}/

#### src/execution/docker_runner.py (已存在)
- ✅ Docker subprocess 封装
- ✅ 超时处理
- ✅ 网络隔离

#### src/execution/templates/qlib_backtest.py.tpl (已存在)
- ✅ 确定性回测模板
- ✅ JSON 输出格式

### 3. Stage 5: 判断层

#### src/agents/critic_v2.py (新建)
- ✅ 确定性判定逻辑
- ✅ 固定判定顺序：完整性检查 → 硬阈值检查 → 加权评分
- ✅ 决策状态机：promote/archive/reject/retry
- ✅ 原因码枚举：LOW_SHARPE, LOW_IC, HIGH_TURNOVER 等

#### src/agents/factor_pool_writer.py (新建)
- ✅ FactorPool 写回逻辑
- ✅ 标签构建（island, decision, reason, score）

#### src/agents/cio_report_renderer.py (新建)
- ✅ 确定性 Markdown 报告渲染器
- ✅ 最小化 CIOReport 模板

### 4. FactorPool 扩展

#### src/factor_pool/pool.py
- ✅ register_factor_v2() 方法
- ✅ 支持 FactorPoolRecord 写入
- ✅ 向后兼容旧 API

### 5. 集成测试

#### tests/test_stage45_golden_path.py (新建)
- ✅ test_full_pipeline_success: 完整流程测试
- ✅ test_critic_deterministic: 确定性验证
- ✅ test_critic_threshold_boundaries: 阈值边界测试
- ✅ test_failure_stage_classification: 错误分类测试
- ✅ test_cio_report_rendering: 报告渲染测试

## 验收标准达成情况

根据 v2_stage45_golden_path.md 第 10 节验收标准：

1. ✅ FactorResearchNote.final_formula 能被唯一消费
2. ✅ compile / runner 不依赖 LLM
3. ✅ 回测产物能稳定解析成 BacktestReport
4. ✅ BacktestReport 字段足以支持 deterministic 判定
5. ✅ CriticVerdict 不依赖自由文本推理即可生成
6. ✅ FactorPool 写回结构固定且可重复
7. ✅ 最小 CIOReport 可产出
8. ✅ 至少有 1 条集成测试锁住整条链

额外硬条件：
✅ 同一输入在相同配置下重复运行，CriticVerdict.decision 与 score 必须稳定一致（已通过 test_critic_deterministic 验证）

## 使用示例

```python
from src.schemas.research_note import FactorResearchNote
from src.execution.coder_v2 import Coder
from src.agents.critic_v2 import Critic
from src.agents.factor_pool_writer import FactorPoolWriter
from src.agents.cio_report_renderer import CIOReportRenderer
from src.factor_pool.pool import get_factor_pool

# 准备输入
note = FactorResearchNote(
    note_id="momentum_20260311_001",
    island="momentum",
    iteration=1,
    hypothesis="近20日动量因子具有预测能力",
    economic_intuition="动量效应源于羊群行为",
    final_formula="Ref($close, 20) / $close - 1",
    universe="csi300",
    backtest_start="2021-06-01",
    backtest_end="2023-12-31",
    expected_ic_min=0.02,
    risk_factors=["市场regime切换"],
    market_context_date="2026-03-11",
)

# Stage 4: 执行回测
coder = Coder()
report = await coder.run_backtest(note)

# Stage 5: 判定
critic = Critic()
verdict = critic.evaluate(report)

# 写入 FactorPool
pool = get_factor_pool()
writer = FactorPoolWriter(pool)
factor_id = writer.write_record(report, verdict)

# 生成 CIO 报告
renderer = CIOReportRenderer()
cio_report = renderer.render(report, verdict, factor_id)
print(cio_report)
```

## 下一步工作

根据 v2_stage45_golden_path.md 第 11 节实施顺序，当前已完成 Milestone 1-5。

后续可选扩展（不在当前 Golden Path 范围内）：
- ExplorationAgent（Stage 4a）
- RiskAuditor 完整版（过拟合检测、相关性矩阵）
- PortfolioManager（跨因子组合优化）
- Reflection system
- OOS/generalization 完整生命周期

## 文件清单

新建文件：
- src/schemas/factor_pool_record.py
- src/execution/coder_v2.py
- src/agents/critic_v2.py
- src/agents/factor_pool_writer.py
- src/agents/cio_report_renderer.py
- tests/test_stage45_golden_path.py

修改文件：
- src/schemas/backtest.py
- src/schemas/judgment.py
- src/schemas/thresholds.py
- src/factor_pool/pool.py

## 注意事项

1. 当前实现为 v2 版本（带 _v2 后缀），与旧版本并存
2. 需要 Docker 环境和 Qlib 数据才能运行完整测试
3. 产物存储在 data/artifacts/{run_id}/ 目录
4. 阈值可通过 THRESHOLDS 对象调整
5. 所有判定逻辑都是确定性的，不调用 LLM
