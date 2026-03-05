# Skills-based Agent Architecture — 实施规格说明书

> 面向 Gemini 的执行文档
> 版本：1.0 | 日期：2026-03-05
> 前置条件：Island 调度器任务已完成

---

## 任务背景

当前 `researcher.py` 的 System Prompt 是一个混杂了角色定位、工具列表、知识库、行为规则、
Island 上下文的巨型 f-string，难以维护，且无法按状态条件动态调整注入内容。

**本任务目标：**
1. 创建 `src/skills/loader.py`（`SkillLoader`），统一管理 Skill 加载逻辑
2. 创建 4 个高质量 Skill 文档（Markdown），覆盖最关键的行为规范
3. 重构 `researcher.py` 的 System Prompt 构建，改用 `SkillLoader`
4. 扩展 `validator.py`，加入 A 股硬约束的代码层检查

---

## 交付物清单

1. `knowledge/skills/constraints/a_share_constraints.md` — 新建（Type A）
2. `knowledge/skills/constraints/qlib_formula_syntax.md` — 新建（Type A）
3. `knowledge/skills/researcher/island_evolution.md` — 新建（Type C）
4. `knowledge/skills/researcher/feedback_interpretation.md` — 新建（Type C）
5. `src/skills/__init__.py` — 新建（空文件）
6. `src/skills/loader.py` — 新建，`SkillLoader` 类
7. `src/agents/researcher.py` — 修改，改用 `SkillLoader`
8. `src/agents/validator.py` — 修改，加入硬约束检查
9. `tests/test_skill_loader.py` — 新建，验收测试

**不要动：** `critic.py`、`coder.py`、`orchestrator.py`、`pool.py`、`scheduler.py`

---

## 任务 1：创建目录结构

```bash
mkdir -p EvoQuant/knowledge/skills/constraints
mkdir -p EvoQuant/knowledge/skills/researcher
mkdir -p EvoQuant/src/skills
touch EvoQuant/src/skills/__init__.py
```

---

## 任务 2：创建 Skill 文档

### 2.1 `knowledge/skills/constraints/a_share_constraints.md`

```markdown
# A 股市场硬约束规范

> **Type A — 强制规则。无论何种因子、何种 Island，以下规则必须遵守。**
> 违反这些规则会导致回测结果虚假，或实盘无法执行。

---

## 1. 前视偏差（Look-ahead Bias）防护

### 1.1 Qlib 表达式时间偏移
- `Ref($close, N)` 中 N 必须为**正整数**，表示 N 日前的价格
- **禁止** `Ref($close, -1)`（使用明日数据）
- **禁止** `Ref($close, 0)`（等同于当日收盘价，无意义）
- 正确示例：`$close / Ref($close, 1) - 1`（昨日到今日的收益率）

### 1.2 财务数据的点时间（Point-in-Time）
- 季报/年报数据必须使用**实际公告日期**，非报告期末日期
- 错误：用 2024-03-31（季报期末）的 EPS 数据
- 正确：用该季报的实际公告日（通常在 4 月末到 5 月初）
- 原因：投资者在 4 月才知道一季报数据，不是 3 月 31 日

### 1.3 指数成分股生存偏差
- CSI300/CSI500 成分股每半年调整一次
- 必须使用调整时间节点对应的成分股列表，不能用当前成分股回测历史
- Qlib 的 `instruments` 参数若指定固定列表，需确认该列表为历史时点数据

---

## 2. T+1 规则对因子设计的影响

A 股实行 T+1 制度：**今日买入的股票，最早明日才能卖出**。

### 2.1 因子信号的时效性
- 今日收盘后计算的信号，执行时间是**明日开盘**
- 因此，持仓周期 ≤ 1 日的因子在 A 股无法执行
- **建议最短持仓周期：≥ 5 个交易日**

### 2.2 高频因子的衰减
- 1 日动量因子（隔夜收益率）理论上有效，但 T+1 的执行延迟会大幅衰减 IC
- 更稳健的选择：5 日、10 日、20 日的中低频因子

---

## 3. 涨跌停规则对执行的影响

A 股每日价格波动上限为 ±10%（ST 股为 ±5%）。

### 3.1 涨停板无法买入
- 涨停板当日，委托买单通常无法成交（市场挂单已满）
- 因子生成的买入信号若目标股票处于涨停，**该信号应被跳过**
- Qlib 的 TopK 策略不会自动处理此情况，需外部过滤

### 3.2 跌停板无法卖出
- 处于跌停板的股票同样无法正常卖出
- 回测中若不处理此情景，持仓损失会被低估

### 3.3 对因子的影响
- 追涨类因子（买入近期涨幅大的股票）在 A 股因涨停板而执行困难
- 建议：因子选股后，过滤掉当日涨幅 > 8% 的股票（接近涨停板）

---

## 4. 停牌股处理规范

### 4.1 NaN 的来源
- 股票停牌期间无成交数据，Qlib 会产生 NaN
- 连续停牌（如重大资产重组）可能导致数十日为 NaN

### 4.2 规范做法
- **禁止**用停牌前最后价格填充（`fillna(method='ffill')`）：这会制造虚假的"零动量"信号
- **推荐**：Qlib 的 `Mean`、`Std`、`Corr` 等算子在遇到 NaN 时自动跳过，因子公式应优先使用这些算子
- 停牌股不应进入 TopK 选股池（Qlib 的 `Filter` 算子可过滤）

---

## 5. ST 股过滤规范

- ST（特别处理）和 *ST（退市警告）股票风险极高，不纳入常规策略
- CSI300/CSI500 成分股天然排除大多数 ST 股
- 若使用全市场股票池，必须在因子计算前过滤 ST 股

---

## 6. 最小存活规则

- 新股上市后 **前 60 个交易日** 不纳入因子计算（价格不稳定，动量因子会产生极端值）
- 月均成交金额 < 500 万元的股票视为极低流动性，不纳入选股池

---

*最后更新：2026-03-05 | 来源：A 股市场规则 + Qlib 数据管线实践经验*
```

---

### 2.2 `knowledge/skills/constraints/qlib_formula_syntax.md`

```markdown
# Qlib 因子表达式语法规范

> **Type A — 强制规则。所有 Qlib 表达式必须符合以下语法，否则 Validator 会拦截。**

---

## 合法字段（数据源）

```
$open    $high    $low    $close    $volume    $vwap    $factor
```

- 前缀 `$` 是必须的
- 字段名区分大小写，全部小写
- 不存在 `$price`、`$turnover_rate` 等字段（换手率需用 $volume/$float_shares 计算）

---

## 合法算子（完整列表）

### 时序算子（需要 lookback 参数 N）
| 算子 | 含义 | 示例 |
|---|---|---|
| `Ref(expr, N)` | N 日前的值 | `Ref($close, 5)` |
| `Mean(expr, N)` | N 日均值 | `Mean($volume, 20)` |
| `Std(expr, N)` | N 日标准差 | `Std($close/Ref($close,1)-1, 20)` |
| `Sum(expr, N)` | N 日求和 | `Sum($volume, 5)` |
| `Max(expr, N)` | N 日最大值 | `Max($high, 20)` |
| `Min(expr, N)` | N 日最小值 | `Min($low, 20)` |
| `Slope(expr, N)` | N 日线性回归斜率 | `Slope($close, 20)` |
| `Rsquare(expr, N)` | N 日线性回归 R² | `Rsquare($close, 20)` |
| `Resi(expr, N)` | N 日线性回归残差 | `Resi($close, 20)` |
| `WMA(expr, N)` | N 日加权移动均值 | `WMA($close, 10)` |
| `EMA(expr, N)` | N 日指数移动均值 | `EMA($close, 12)` |
| `Corr(e1, e2, N)` | N 日相关系数 | `Corr($close/Ref($close,1), $volume/Ref($volume,1), 20)` |
| `Cov(e1, e2, N)` | N 日协方差 | `Cov($close, $volume, 10)` |

### 截面算子（在同一天所有股票间计算）
| 算子 | 含义 |
|---|---|
| `CSRank(expr)` | 截面排名（0~1） |
| `CSZScore(expr)` | 截面 Z-score 标准化 |
| `CSMax(expr)` | 截面最大值 |
| `CSMin(expr)` | 截面最小值 |

### 数学算子
| 算子 | 含义 |
|---|---|
| `Abs(expr)` | 绝对值 |
| `Sign(expr)` | 符号（-1/0/1） |
| `Log(expr)` | 自然对数（expr 必须 > 0） |
| `Power(expr, n)` | 幂次 |
| `If(cond, t, f)` | 条件表达式 |

---

## 常见语法错误（Validator 会拦截）

```python
# ❌ 负数时间偏移（未来数据）
Ref($close, -1)

# ❌ 字段名无 $ 前缀
Mean(close, 5)

# ❌ 括号不匹配
Corr($close, $volume, 20

# ❌ 不存在的算子
MovingAverage($close, 5)   # 应该用 Mean

# ❌ 对数的参数可能为负
Log($close - Ref($close, 1))   # 日收益率可能为负
# 应改为：Log($close / Ref($close, 1))
```

---

## 推荐的常用模板

```python
# 日收益率（最基础的动量信号）
$close / Ref($close, 1) - 1

# N 日收益率
$close / Ref($close, N) - 1

# 量价相关性（捕捉放量上涨 vs 缩量上涨）
Corr($close / Ref($close, 1), $volume / Ref($volume, 1), 20)

# 相对成交量（当日成交量 vs 近期均量）
$volume / Mean($volume, 20)

# 截面动量排名
CSRank($close / Ref($close, 20) - 1)

# 波动率
Std($close / Ref($close, 1) - 1, 20)
```

---

*最后更新：2026-03-05*
```

---

### 2.3 `knowledge/skills/researcher/island_evolution.md`

```markdown
# Island 进化研究规范

> **Type C — 条件注入：当 current_iteration > 0（非第一轮）时注入。**
> 本规范描述在 Island 进化框架下，Researcher 如何利用历史知识进行结构化探索。

---

## 你的研究定位

你属于某一个 **Island（因子研究方向）** 的研究员。
Island 制度的目的是：防止系统在单一方向反复试错，确保多维度并行探索。

你的两个核心职责：
1. **在本 Island 方向上持续改进**（利用历史成果）
2. **提出与现有因子有差异的新假设**（避免重复劳动）

---

## 强制工作流程（每轮必须按顺序执行）

```
Step 1 → get_island_best_factors(island_name, top_k=3)
         了解本 Island 历史最优因子和已达到的 Sharpe 水平

Step 2 → get_pool_stats()
         了解整体实验进度（总因子数、已突破基线数、全局最优）

Step 3 → [如果已有方向想法] get_similar_failures(formula, top_k=3)
         用你初步想到的公式，检索历史上类似的失败案例，主动规避

Step 4 → 调用 1-2 个 AKShare 工具，获取今日市场数据（北向资金或行业估值）

Step 5 → 综合以上信息，输出结构化因子假设（JSON 格式）
```

**禁止跳过 Step 1 和 Step 2。** 不了解历史就提假设，等于无视已有的集体知识。

---

## 创新约束（避免无效重复）

### 相似度检查
在提出新因子之前，请自行检查：
- 新公式与 `get_island_best_factors` 返回的公式**是否本质相同**？
  - 例：`Mean($close, 5) / Ref($close, 5)` 和 `$close / Ref(Mean($close, 5), 1)` 虽然写法不同，
    经济含义几乎一样，这种改动无效
- 建议改变：时间窗口（N的值）变化 > 50%，或引入全新信号维度（价→量、价格→资金流）

### Island 方向约束
你的因子核心变量必须符合所在 Island 的方向：

| Island | 核心变量要求 |
|---|---|
| `momentum` | 主变量来自价格或成交量的时序特征（收益率、量比等） |
| `northbound` | 主变量**必须包含**北向资金相关数据（净流入、持股变化） |
| `valuation` | 主变量必须是某种估值比率或行业估值分位数 |
| `volatility` | 主变量来自价格波动特征（历史波动率、ATR、偏度） |
| `volume` | 主变量来自资金流向（主力净流入、大单净流入、量价背离） |
| `sentiment` | 主变量来自情绪代理（研报评级、分析师预期修正） |

---

## 失败模式诊断与对策

拿到 Critic 的评估反馈后，按以下决策树判断下一步方向：

### 情况 1：Sharpe 低（< 2.67），但 IC 中等（> 0.02）
**诊断：因子有预测力，但换手率过高，手续费吃掉收益**
- ✅ 对策：将滚动窗口从 N 天延长到 2N 天（降低信号频率）
- ✅ 对策：对因子值做截面排名后取分位数（CSRank + 设置死区）
- ❌ 不要：把这个方向整个放弃

### 情况 2：IC 低（< 0.01）且 ICIR 低
**诊断：因子本身没有预测能力，信号来源有问题**
- ✅ 对策：更换信号来源，换一个截然不同的经济逻辑
- ✅ 对策：考虑向 Orchestrator 建议切换 Island 方向
- ❌ 不要：继续在同一个公式上微调参数（如 N=5 改 N=6）

### 情况 3：IC 中等（0.01~0.02），ICIR 低（< 0.3）
**诊断：因子在某些市场状态下有效，但不稳定**
- ✅ 对策：加入市场状态过滤
  ```
  趋势市场判断：Mean($close, 20) / Mean($close, 60) > 1.02
  震荡市场判断：Std($close/Ref($close,1)-1, 20) < 0.015
  ```
- ✅ 对策：因子乘以市场状态权重（趋势市放大，震荡市缩小）

### 情况 4：代码执行报错（error_message 非空）
**优先排查顺序：**
1. Qlib 算子名称拼写（对照 `qlib_formula_syntax.md` 的合法算子列表）
2. `$` 字段名是否存在（只有 `$open/$high/$low/$close/$volume/$vwap/$factor` 合法）
3. `Ref()` 的第二个参数是否为正整数
4. `Log()` 的参数是否可能为负数或零
5. 括号是否匹配（逐层检查）

### 情况 5：换手率高（> 50%）且 Sharpe 未达标
**诊断：信号过于敏感，持仓频繁切换**
- ✅ 对策：在因子外层套 `Mean(factor, 5)`（平滑信号）
- ✅ 对策：使用 `Slope` 替代 `Ref`（趋势而非时点差值）

---

## 输出标准提醒

最终输出必须是合法 JSON（Validator 会检查）：
```json
{
  "name": "island_方向_描述_滚动窗口",
  "formula": "合法的 Qlib 表达式",
  "hypothesis": "因子的中文假设（1-3句）",
  "market_observation": "今日工具调用观察到的关键数据",
  "expected_direction": "positive 或 negative",
  "rationale": "A 股市场下的经济逻辑（1-3句）"
}
```

命名规范：`{island}_{signal_type}_{window}d`
例：`northbound_flow_momentum_5d`、`momentum_vol_adj_corr_20d`

---

*最后更新：2026-03-05*
```

---

### 2.4 `knowledge/skills/researcher/feedback_interpretation.md`

```markdown
# 回测反馈解读规范

> **Type C — 条件注入：当 error_message 非空（上一轮有失败记录）时注入。**
> 本规范帮助 Researcher 系统性地解读 Critic 的失败反馈，避免随机试错。

---

## 反馈解读的基本原则

1. **失败是信息，不是惩罚。** 每次失败都缩小了搜索空间。
2. **一次只改一个变量。** 如果同时换因子逻辑和调整窗口，无法判断是哪个改动起了作用。
3. **记录改动原因。** 在你的 `rationale` 字段中说明本次相对上一版本改了什么、为什么。

---

## 上一次失败的错误消息解读

系统会将上一轮的 `error_message` 注入到你的输入中。
以下是常见错误消息的含义和对策：

| 错误消息关键词 | 含义 | 建议对策 |
|---|---|---|
| `夏普比率 X.XX 未超越基线` | 因子已回测，但 Sharpe 不够高 | 参考 `island_evolution.md` 中的失败诊断 |
| `IC均值 X.XX 低于门槛` | 因子预测能力不足 | 更换信号来源，勿微调 |
| `ICIR X.XX 低于门槛` | 因子不稳定 | 加入市场状态过滤 |
| `换手率 XX% 过高` | 信号频繁切换 | 延长窗口，平滑信号 |
| `Qlib 表达式语法` | 代码语法错误 | 对照合法算子列表修正 |
| `KeyError`、`ValueError` | 数据字段不存在 | 检查 `$` 前缀和字段名 |
| `未能从回测日志解析` | Coder 未输出标准格式 | 尝试更简单的因子，先验证流程 |

---

## 本轮修改的文档规范

在你输出的 JSON 中，`rationale` 字段需要包含以下结构：

```
1. 上一版本问题：[简述为什么上一个因子失败]
2. 本次改动：[具体改了什么，只改一个方向]
3. 预期效果：[为什么这个改动应该改善指标]
```

示例：
```json
{
  "rationale": "上一版本问题：换手率78%过高，手续费吃掉超额收益。本次改动：将滚动窗口从5日延长至20日，降低信号翻转频率。预期效果：保持IC不变，换手率应降至30%以下。"
}
```

---

*最后更新：2026-03-05*
```

---

## 任务 3：创建 `src/skills/loader.py`

```python
"""
EvoQuant: SkillLoader — 统一管理 Skill 文档的加载与条件注入
"""
import logging
import os
from typing import Optional

from src.agents.state import AgentState

logger = logging.getLogger(__name__)

_SKILLS_BASE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "knowledge", "skills")
)


class SkillLoader:
    """按 Agent 角色和 AgentState 动态加载 Skill 文档。

    三类 Skill：
      Type A (Rules)  — 永久注入，硬约束
      Type B (Process)— 永久注入，流程规范
      Type C (Context)— 按 AgentState 条件注入
    """

    def load_for_researcher(self, state: AgentState) -> str:
        """为 Researcher Agent 加载完整的 Skill 上下文。"""
        parts = []

        # ── Type A: 永久注入（硬约束）─────────────────────────
        parts.append(self._load("constraints/a_share_constraints.md", required=True))
        parts.append(self._load("constraints/qlib_formula_syntax.md", required=True))

        # ── Type B: 永久注入（流程规范）───────────────────────
        parts.append(self._load("researcher/alpha_generation.md", required=True))

        # ── Type C: 条件注入（上下文感知）─────────────────────
        # 非第一轮：注入 Island 进化规范
        if state.get("current_iteration", 0) > 0:
            parts.append(self._load("researcher/island_evolution.md"))

        # 有失败记录：注入失败解读规范
        if state.get("error_message"):
            parts.append(self._load("researcher/feedback_interpretation.md"))

        # 过滤掉加载失败的（None）
        valid_parts = [p for p in parts if p]

        logger.debug("[SkillLoader] Researcher 加载了 %d 个 Skill 文档", len(valid_parts))
        return "\n\n---\n\n".join(valid_parts)

    def load_for_coder(self) -> str:
        """为 Coder Agent 加载 Skill 上下文（无状态依赖）。"""
        parts = [
            self._load("constraints/qlib_formula_syntax.md", required=True),
            self._load("coder/qlib_debugging.md", required=True),
        ]
        return "\n\n---\n\n".join(p for p in parts if p)

    def load_for_critic(self) -> str:
        """为 Critic Agent 加载 Skill 上下文。"""
        parts = [
            self._load("constraints/a_share_constraints.md", required=True),
        ]
        return "\n\n---\n\n".join(p for p in parts if p)

    # ─────────────────────────────────────────────
    def _load(self, relative_path: str, required: bool = False) -> Optional[str]:
        """加载单个 Skill 文档。

        Args:
            relative_path: 相对于 knowledge/skills/ 的路径
            required: True 时加载失败会打印 warning；False 时静默失败

        Returns:
            文件内容字符串，或 None（加载失败时）
        """
        full_path = os.path.join(_SKILLS_BASE, relative_path)
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            if required:
                logger.warning("[SkillLoader] 必要的 Skill 文档缺失：%s", full_path)
            return None
        except Exception as e:
            logger.error("[SkillLoader] 加载 Skill 文档失败 %s: %s", full_path, e)
            return None
```

---

## 任务 4：重构 `src/agents/researcher.py`

改动范围：只修改 `_load_knowledge_base()` 函数和 `_research_node_async()` 中构建 system_prompt 的部分。

### 4.1 在 import 块末尾新增

```python
from src.skills.loader import SkillLoader

_SKILL_LOADER = SkillLoader()  # 模块级单例
```

### 4.2 删除旧的 `_load_knowledge_base()` 函数

找到并**完整删除**以下函数（约 10 行）：

```python
def _load_knowledge_base() -> str:
    parts = []
    for label, path in [("Layer 1 Factor Dictionary", DICTIONARY_PATH),
                        ("Agent Skills Methodology", SKILL_PATH)]:
        try:
            ...
```

### 4.3 修改 `_research_node_async()` 中的 system_prompt 构建

**找到：**
```python
    # 3. 加载知识库
    layer_1_kb = _load_knowledge_base()

    # 4. 构建 System Prompt
    system_prompt = f"""你是一名顶尖的量化研究员，专注于 A 股市场 Alpha 因子发现。
...（大段 f-string）...
```

**替换为：**
```python
    # 3. 加载 Skills（按状态条件动态组合）
    skill_context = _SKILL_LOADER.load_for_researcher(state)

    # 同时加载因子字典（Layer 1 知识库，独立于 Skills）
    factor_dict = ""
    try:
        with open(DICTIONARY_PATH, "r", encoding="utf-8") as f:
            factor_dict = f.read()
    except Exception as e:
        logger.warning("因子字典加载失败: %s", e)

    # 4. 构建 System Prompt（结构清晰：角色 + Skills + 工具列表）
    island_name = state.get("island_name", "momentum")
    from src.factor_pool.islands import ISLANDS
    island_info = ISLANDS.get(island_name, {})

    system_prompt = f"""你是一名顶尖的量化研究员，专注于 A 股市场 Alpha 因子发现。

## 当前研究 Island
- 代号：{island_name}（{island_info.get('name', '')}）
- 方向：{island_info.get('description', '')}

## 行为规范与约束
{skill_context}

## 因子参考字典
{factor_dict}

## 可用实时数据工具
- get_northbound_flow_today()：今日北向资金
- get_northbound_flow_history(days)：北向历史序列
- get_market_fund_flow(days)：全市场主力资金
- get_northbound_top_holdings(market, top_n)：北向持股变化
- get_research_reports(symbol, limit)：券商研报
- get_industry_pe(classification, query_date)：行业 PE
- get_individual_fund_flow_rank(period, top_n)：个股资金排行
- get_island_best_factors(island_name, top_k)：本 Island 历史最优 ← 必须调用
- get_similar_failures(formula, top_k)：相似失败案例
- get_island_leaderboard()：所有 Island 排行
- get_pool_stats()：全局实验统计

当前迭代：{state['current_iteration']}/{state['max_iterations']}
"""
```

---

## 任务 5：扩展 `src/agents/validator.py`

在现有的括号匹配检查之后，新增 A 股硬约束检查。

**找到现有 validator 文件，在其中新增以下函数，并在 `validator_node` 中调用：**

```python
import re

def _check_no_future_leak(formula: str) -> tuple[bool, str]:
    """检查 Ref() 是否使用了负数偏移（未来数据）。"""
    if re.search(r'Ref\s*\([^)]+,\s*-\d+', formula):
        return False, "[Validator 拦截] 检测到 Ref() 使用负数偏移（未来数据），这会引入前视偏差。请使用正整数偏移。"
    return True, ""


def _check_valid_fields(formula: str) -> tuple[bool, str]:
    """检查 $ 字段名是否合法。"""
    valid_fields = {"open", "high", "low", "close", "volume", "vwap", "factor"}
    # 找出所有 $xxx 形式的字段名
    used_fields = re.findall(r'\$(\w+)', formula)
    invalid = [f for f in used_fields if f not in valid_fields]
    if invalid:
        return False, f"[Validator 拦截] 使用了不存在的字段：{invalid}。合法字段：{sorted(valid_fields)}"
    return True, ""


def _check_log_safety(formula: str) -> tuple[bool, str]:
    """检查 Log() 的参数是否可能为负。"""
    # 检测 Log($close - ...) 或 Log($close/Ref... - 1) 等危险模式
    if re.search(r'Log\s*\(\s*\$\w+\s*[-]', formula):
        return False, "[Validator 拦截] Log() 的参数可能为负数，请改用 Log($close / Ref($close, N)) 形式。"
    return True, ""
```

在 `validator_node()` 函数中，在现有检查之后追加：

```python
    # A 股硬约束检查
    formula = ""
    hypothesis = state.get("factor_hypothesis")
    if hypothesis:
        formula = hypothesis.formula

    if formula:
        for check_fn in [_check_no_future_leak, _check_valid_fields, _check_log_safety]:
            ok, err_msg = check_fn(formula)
            if not ok:
                return {
                    "error_message": err_msg,
                    "factor_proposal": state.get("factor_proposal", ""),
                }
```

---

## 任务 6：创建 `tests/test_skill_loader.py`

```python
"""验收测试：SkillLoader 条件注入逻辑。"""
import os, sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.skills.loader import SkillLoader


@pytest.fixture()
def loader():
    return SkillLoader()


def _state(iteration=0, error=""):
    return {"current_iteration": iteration, "error_message": error,
            "max_iterations": 3, "island_name": "momentum"}


class TestSkillLoader:
    def test_type_a_always_injected(self, loader):
        """A 股约束和 Qlib 语法规范在任何状态下都必须存在。"""
        result = loader.load_for_researcher(_state(iteration=0))
        assert "T+1" in result or "前视偏差" in result  # a_share_constraints
        assert "Ref(expr, N)" in result or "合法算子" in result  # qlib_formula_syntax

    def test_island_evolution_not_injected_first_round(self, loader):
        """第一轮（iteration=0）不注入 island_evolution.md。"""
        result = loader.load_for_researcher(_state(iteration=0))
        assert "强制工作流程" not in result

    def test_island_evolution_injected_after_first_round(self, loader):
        """第二轮起注入 island_evolution.md。"""
        result = loader.load_for_researcher(_state(iteration=1))
        assert "强制工作流程" in result

    def test_feedback_not_injected_without_error(self, loader):
        """没有错误时不注入 feedback_interpretation.md。"""
        result = loader.load_for_researcher(_state(error=""))
        assert "上一次失败的错误消息解读" not in result

    def test_feedback_injected_with_error(self, loader):
        """有错误记录时注入 feedback_interpretation.md。"""
        result = loader.load_for_researcher(_state(error="Sharpe 2.1 未超越基线"))
        assert "上一次失败的错误消息解读" in result

    def test_both_context_skills_injected(self, loader):
        """iteration>0 且有 error 时，两个 Type C Skill 都应注入。"""
        result = loader.load_for_researcher(_state(iteration=2, error="IC低"))
        assert "强制工作流程" in result
        assert "上一次失败的错误消息解读" in result

    def test_coder_skill_loads(self, loader):
        result = loader.load_for_coder()
        assert len(result) > 100  # 至少有内容

    def test_missing_skill_returns_none(self, loader):
        result = loader._load("nonexistent/file.md", required=False)
        assert result is None


class TestValidatorConstraints:
    """验证 validator.py 新增的硬约束检查。"""

    def test_future_ref_detected(self):
        from src.agents.validator import _check_no_future_leak
        ok, msg = _check_no_future_leak("Ref($close, -1)")
        assert not ok
        assert "前视偏差" in msg or "负数" in msg

    def test_positive_ref_passes(self):
        from src.agents.validator import _check_no_future_leak
        ok, _ = _check_no_future_leak("Ref($close, 5)")
        assert ok

    def test_invalid_field_detected(self):
        from src.agents.validator import _check_valid_fields
        ok, msg = _check_valid_fields("Mean($price, 5)")
        assert not ok
        assert "price" in msg

    def test_valid_fields_pass(self):
        from src.agents.validator import _check_valid_fields
        ok, _ = _check_valid_fields("Mean($close, 5) / Ref($volume, 1)")
        assert ok

    def test_log_negative_detected(self):
        from src.agents.validator import _check_log_safety
        ok, msg = _check_log_safety("Log($close - Ref($close, 1))")
        assert not ok

    def test_log_ratio_passes(self):
        from src.agents.validator import _check_log_safety
        ok, _ = _check_log_safety("Log($close / Ref($close, 1))")
        assert ok


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

---

## 验收清单

```bash
# Step 1: 运行 SkillLoader 测试
cd EvoQuant
conda activate evoquant
python3 -m pytest tests/test_skill_loader.py -v
# 预期：全部 PASSED（14 个测试）

# Step 2: 验证 SkillLoader 条件注入（手动检查输出）
python3 -c "
from src.skills.loader import SkillLoader
loader = SkillLoader()
# 第一轮，无错误
s1 = loader.load_for_researcher({'current_iteration': 0, 'error_message': '', 'island_name': 'momentum', 'max_iterations': 3})
print('第一轮 Skills 字数:', len(s1))
# 第二轮，有错误
s2 = loader.load_for_researcher({'current_iteration': 1, 'error_message': 'Sharpe低', 'island_name': 'momentum', 'max_iterations': 3})
print('第二轮 Skills 字数:', len(s2))
print('第二轮比第一轮多:', len(s2) - len(s1), '字（应为正数）')
"

# Step 3: 端到端验证 Validator 新增检查
python3 -c "
from src.agents.validator import _check_no_future_leak, _check_valid_fields
print(_check_no_future_leak('Ref(\$close, -1)'))   # 应该拦截
print(_check_no_future_leak('Ref(\$close, 5)'))    # 应该通过
print(_check_valid_fields('Mean(\$price, 5)'))     # 应该拦截
"

# Step 4: 完整系统跑一轮（观察 SkillLoader 日志）
python3 EvoQuant/src/core/orchestrator.py --mode single --island momentum
# 确认日志出现：[SkillLoader] Researcher 加载了 N 个 Skill 文档
```

---

## 注意事项

1. `SkillLoader` 是模块级单例（`_SKILL_LOADER`），文件只读一次后缓存在内存里——但若 Skill 文档在运行中被修改，不会热更新（下次启动生效）
2. 旧的 `SKILL_PATH`（`knowledge/agent_skills/researcher_alpha_generation.md`）文件**不要删除**，只是不再通过旧路径加载；新路径是 `knowledge/skills/researcher/alpha_generation.md`——Gemini 需要把旧文件内容**复制**到新路径
3. `factor_dict`（因子字典）依然独立于 Skills 系统加载，保持单独注入
4. Validator 的硬约束检查只检查 `factor_hypothesis` 对象里的 `formula` 字段；若 `factor_hypothesis` 为 None（降级模式），跳过硬约束检查（容错）
5. Skill 文档用 `---` 分隔，不要用其他分隔符破坏 Markdown 结构
