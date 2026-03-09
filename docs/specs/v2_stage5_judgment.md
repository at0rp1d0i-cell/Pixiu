# Pixiu v2 Stage 5：判断与综合层规格

> 版本：2.0
> 创建：2026-03-07
> 前置依赖：`v2_interface_contracts.md`
> 文件位置：`src/agents/judgment.py`（扩展现有 `critic.py`）

> 当前收口顺序：先读 `v2_stage45_golden_path.md`，本文件保留完整 Stage 5 目标形态与扩展设计。

---

## 1. 四个组件

| 组件 | 类型 | 当前状态 |
|---|---|---|
| Critic | 规则 + LLM 归因 | v1 已有，需迁移接口 |
| RiskAuditor | 统计 + LLM 解释 | 新增 |
| PortfolioManager | LLM | 新增 |
| ReportWriter | LLM | 新增 |

---

## 2. Critic（更新接口）

### 判断逻辑（不变，只更新输入输出类型）

```python
# src/agents/judgment.py

from src.schemas.backtest import BacktestReport
from src.schemas.judgment import CriticVerdict, ThresholdCheck
from src.schemas.thresholds import THRESHOLDS

class Critic:
    def evaluate(self, report: BacktestReport) -> CriticVerdict:
        checks = [
            ThresholdCheck(
                metric="sharpe",
                value=report.metrics.sharpe,
                threshold=THRESHOLDS.min_sharpe,
                passed=report.metrics.sharpe >= THRESHOLDS.min_sharpe,
            ),
            ThresholdCheck(
                metric="ic_mean",
                value=report.metrics.ic_mean,
                threshold=THRESHOLDS.min_ic_mean,
                passed=report.metrics.ic_mean >= THRESHOLDS.min_ic_mean,
            ),
            ThresholdCheck(
                metric="icir",
                value=report.metrics.icir,
                threshold=THRESHOLDS.min_icir,
                passed=report.metrics.icir >= THRESHOLDS.min_icir,
            ),
            ThresholdCheck(
                metric="turnover_rate",
                value=report.metrics.turnover_rate,
                threshold=THRESHOLDS.max_turnover_rate,
                passed=report.metrics.turnover_rate <= THRESHOLDS.max_turnover_rate,
            ),
        ]

        overall_passed = all(c.passed for c in checks) and report.error_message is None

        failure_mode, explanation, suggestion = self._diagnose(report, checks)

        return CriticVerdict(
            report_id=report.report_id,
            factor_id=report.factor_id,
            overall_passed=overall_passed,
            checks=checks,
            failure_mode=failure_mode,
            failure_explanation=explanation,
            suggested_fix=suggestion,
            register_to_pool=True,  # 无论成败都写入 FactorPool（error-driven RAG）
            pool_tags=self._build_tags(report, overall_passed, failure_mode),
        )

    def _diagnose(self, report, checks) -> tuple[str | None, str, str | None]:
        if report.error_message:
            return (
                "execution_error",
                f"回测执行失败：{report.error_message}",
                "检查公式中是否有 Qlib 不支持的用法或数据缺失",
            )

        failed = [c for c in checks if not c.passed]
        if not failed:
            return None, "所有指标通过", None

        # 最主要的失败原因（取第一个未通过的指标）
        primary = failed[0]
        mode_map = {
            "sharpe": "low_sharpe",
            "ic_mean": "low_ic",
            "icir": "low_icir",
            "turnover_rate": "high_turnover",
        }
        mode = mode_map.get(primary.metric, "unknown")

        explanations = {
            "low_sharpe": f"Sharpe={primary.value:.2f} < {primary.threshold}。因子收益不稳定或绝对收益不足。",
            "low_ic": f"IC={primary.value:.4f} < {primary.threshold}。因子对未来收益的预测力弱。",
            "low_icir": f"ICIR={primary.value:.2f} < {primary.threshold}。IC 时序不稳定，因子存在周期性失效。",
            "high_turnover": f"换手率={primary.value:.2%} > {primary.threshold:.2%}。因子信号变化过快，实际交易成本会严重拖累收益。",
        }
        suggestions = {
            "low_sharpe": "考虑延长回看窗口，或与低相关因子组合以平滑收益",
            "low_ic": "检查经济假设是否在当前市场制度下成立；尝试缩小股票池",
            "low_icir": "检查因子在不同市场状态（牛/熊/震荡）下的稳定性；考虑加入 regime filter",
            "high_turnover": "增大时间窗口参数（如 Mean(x,5) → Mean(x,20)）以平滑信号",
        }

        return (
            mode,
            explanations.get(mode, "未知失败原因"),
            suggestions.get(mode),
        )

    def _build_tags(self, report, passed, failure_mode) -> list[str]:
        tags = [f"island:{report.island}"]
        tags.append("passed" if passed else f"failed:{failure_mode or 'unknown'}")
        if report.metrics.sharpe > 0:
            tags.append(f"sharpe:{report.metrics.sharpe:.1f}")
        return tags
```

---

## 3. RiskAuditor（新增）

### 过拟合检测

通过比较 In-Sample（IS）和 Out-of-Sample（OOS）的 Sharpe，判断过拟合风险：

```python
# 需要 Coder 回测时同时输出 IS 和 OOS 的 Sharpe
# IS：2021-06-01 ~ 2024-06-30
# OOS：2024-07-01 ~ 2025-03-31

class RiskAuditor:
    def __init__(self, factor_pool: FactorPool):
        self.pool = factor_pool

    def audit(
        self,
        report: BacktestReport,
        verdict: CriticVerdict,
    ) -> RiskAuditReport:
        # 1. 过拟合检测
        # 需要 BacktestReport 包含分段 Sharpe（更新 Coder 模板输出两段）
        is_sharpe = report.metrics.get("is_sharpe", report.metrics.sharpe)
        oos_sharpe = report.metrics.get("oos_sharpe", report.metrics.sharpe)

        if is_sharpe > 0:
            oos_is_ratio = oos_sharpe / is_sharpe
        else:
            oos_is_ratio = 0.0

        # OOS/IS 比值 < 0.6 认为存在明显过拟合
        overfitting_score = max(0.0, 1.0 - oos_is_ratio)
        overfitting_flag = overfitting_score > THRESHOLDS.max_overfitting_score

        # 2. 与现有因子的相关性检测
        correlation_flags = self._check_correlations(report)

        # 3. 综合建议
        if overfitting_flag:
            rec = "reject"
            notes = f"OOS/IS Sharpe 比值 = {oos_is_ratio:.2f}，存在明显过拟合风险"
        elif any(f.flag_reason == "too_similar" for f in correlation_flags):
            rec = "approve_with_caution"
            notes = "与已有因子高度相关，加入组合的边际贡献有限"
        else:
            rec = "approve"
            notes = "风险审计通过"

        return RiskAuditReport(
            factor_id=report.factor_id,
            overfitting_score=round(overfitting_score, 3),
            overfitting_flag=overfitting_flag,
            correlation_flags=correlation_flags,
            recommendation=rec,
            audit_notes=notes,
        )

    def _check_correlations(self, report: BacktestReport) -> list[CorrelationFlag]:
        """
        从 FactorPool 获取近期通过因子，
        用 Jaccard token 相似度（快速近似）检测高相关性。
        生产环境中可替换为真实因子值的 Pearson 相关性。
        """
        existing = self.pool.get_passed_factors(island=report.island, limit=20)
        flags = []
        for existing_factor in existing:
            sim = _jaccard_tokens(report.formula, existing_factor["formula"])
            if sim > 0.7:
                flags.append(CorrelationFlag(
                    existing_factor_id=existing_factor["factor_id"],
                    correlation=sim,
                    flag_reason="too_similar",
                ))
        return flags
```

---

## 4. PortfolioManager（新增）

```python
# src/agents/judgment.py（续）

PORTFOLIO_SYSTEM_PROMPT = """你是量化基金的组合管理经理。
你的工作是基于最新通过审核的因子，更新多因子组合配置。

目标：
1. 最大化组合 Sharpe（不是单因子 Sharpe 的简单加权）
2. 控制因子间相关性（多样化）
3. 每个 Island 的权重在 [0.05, 0.40] 之间（防止过度集中）

输出必须是严格 JSON，符合 PortfolioAllocation schema。
"""

class PortfolioManager:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=os.getenv("RESEARCHER_MODEL", "deepseek-chat"),
            base_url=os.getenv("RESEARCHER_BASE_URL"),
            api_key=os.getenv("RESEARCHER_API_KEY"),
            temperature=0.1,
        )

    async def rebalance(
        self,
        new_verdicts: list[CriticVerdict],
        risk_reports: list[RiskAuditReport],
        current_allocation: PortfolioAllocation | None,
        factor_pool: FactorPool,
    ) -> PortfolioAllocation:
        # 获取所有历史通过因子（含本轮新通过的）
        all_passed = factor_pool.get_top_factors(limit=20)

        context = self._build_context(all_passed, new_verdicts, risk_reports, current_allocation)
        response = await self.llm.ainvoke([
            SystemMessage(content=PORTFOLIO_SYSTEM_PROMPT),
            HumanMessage(content=context),
        ])

        return self._parse_allocation(response.content)

    def _build_context(self, all_passed, new_verdicts, risk_reports, current) -> str:
        lines = ["当前因子池中所有通过因子：\n"]
        for f in all_passed:
            lines.append(f"- {f['factor_id']} ({f['island']}): Sharpe={f['sharpe']:.2f}, IC={f['ic_mean']:.4f}")

        lines.append("\n本轮新通过因子：")
        for v in new_verdicts:
            if v.overall_passed:
                lines.append(f"- {v.factor_id}")

        if current:
            lines.append(f"\n当前组合配置：{current.dict()}")

        return "\n".join(lines)
```

---

## 5. ReportWriter（新增）

```python
REPORT_WRITER_PROMPT = """你是量化基金的研究报告撰写员，为 CIO 撰写简洁的决策报告。
报告面向非技术决策者，语言简洁，重点突出。

报告格式（Markdown）：
## 摘要（3行以内）
## 本轮发现
## 组合变化
## 风险提示
## 建议行动

禁止：堆砌数字、超过500字。"""

class ReportWriter:
    def __init__(self):
        self.llm = ChatOpenAI(
            model="claude-sonnet-4-6",
            base_url=os.getenv("ANTHROPIC_BASE_URL"),
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            temperature=0.3,
        )

    async def write(
        self,
        state: AgentState,
        current_round: int,
    ) -> CIOReport:
        passed_this_round = [v for v in state.critic_verdicts if v.overall_passed]
        best = max(passed_this_round, key=lambda v: v.factor_id, default=None)

        context = self._build_context(state, passed_this_round)
        response = await self.llm.ainvoke([
            SystemMessage(content=REPORT_WRITER_PROMPT),
            HumanMessage(content=context),
        ])

        return CIOReport(
            report_id=str(uuid.uuid4()),
            period=f"{today_str()} 第{current_round}轮进化",
            total_factors_tested=len(state.backtest_reports),
            new_factors_approved=len(passed_this_round),
            best_new_factor=best.factor_id if best else None,
            best_new_sharpe=None,  # from backtest report
            current_portfolio=state.portfolio_allocation,
            portfolio_change_summary="",
            highlights=self._extract_highlights(response.content),
            risks=self._extract_risks(response.content),
            full_report_markdown=response.content,
            suggested_actions=["approve_portfolio"],
            requires_human_decision=True,
        )
```

---

## 6. 协同调用顺序（在 Orchestrator judgment_node 中）

```python
async def judgment_node(state: AgentState) -> AgentState:
    critic = Critic()
    risk_auditor = RiskAuditor(factor_pool=pool)

    verdicts = []
    risk_reports = []

    for report in state.backtest_reports:
        verdict = critic.evaluate(report)
        verdicts.append(verdict)

        risk_report = risk_auditor.audit(report, verdict)
        risk_reports.append(risk_report)

        # FactorPool 写入（附带 verdict 和 risk 信息）
        pool.register_factor(
            report=report,
            verdict=verdict,
            risk_report=risk_report,
        )

    return {
        **state.dict(),
        "critic_verdicts": verdicts,
        "risk_audit_reports": risk_reports,
    }
```
