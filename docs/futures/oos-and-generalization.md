# Pixiu v2 OOS 与泛化验证

> 版本：2.0
> 创建：2026-03-09
> 前置依赖：`.../overview/03_architecture-overview.md`、`24_stage-5-judgment.md`
> 状态：**Planned**

---

## 1. 问题

传统量化的前向偏差（用未来数据计算因子）已有解决方案。LLM 系统还有一种更隐蔽的偏差：

> LLM 的训练数据包含大量量化研究文献，模型容易复述“已知有效因子”，而不是发现真正可泛化的新规律。

因此，Pixiu 不仅要防价格数据层面的 look-ahead bias，也要防知识层面的伪发现。

---

## 2. 发现日期戳

`FactorResearchNote` 新增字段：

```python
discovered_at_date: date
discovery_data_cutoff: date
```

规则：

- 发现日期之前的数据可用于提出假设
- 发现日期之后的数据自动进入 OOS 窗口

---

## 3. 强制 OOS 验证

```
发现日期 → 冻结数据边界
  发现日期之前：用于生成假设
  发现日期之后：OOS 窗口

OOS 窗口：oos_start = discovered_at_date + 1天，长度 21 天

Critic 规则：
  OOS pending → 不注册正式区，只标记候选
  OOS 完成 + oos_sharpe ≥ 1.5 → 注册
  OOS 完成 + oos_sharpe < 1.5 → 归入失败
```

---

## 4. 泛化评分

```python
class OOSReport(BaseModel):
    factor_id: str
    backtest_sharpe: float
    oos_sharpe: float
    sharpe_degradation: float
    generalization_score: float
    recommendation: Literal["accept", "caution", "reject"]
```

建议口径：

- `accept`: degradation < 0.20
- `caution`: 0.20 <= degradation < 0.30
- `reject`: degradation >= 0.30

---

## 5. OOS 数据来源

使用**掘金量化模拟盘**（`gm` SDK，myquant.cn）作为 OOS 数据源。

适用边界：

- 适合 A 股日线级中低频因子
- 不适合高频策略

---

## 6. 实施备注

- 该规格目前仍是验证层前瞻设计，不应阻塞 Stage 4/5 的最小运行时闭环。
- 在真正实施前，需要先明确 `BacktestReport`、`RiskAuditReport` 与 `OOSReport` 的关系。
