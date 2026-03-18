# Pixiu v2 FactorPool 规格
Purpose: Define how factors, verdicts, and failure constraints are persisted and queried.
Status: active
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-18

> 版本：2.0
> 创建：2026-03-07
> 前置依赖：`11_interface-contracts.md`
> 文件位置：`src/factor_pool/pool.py`（扩展）

---

## 1. 变更摘要

v2 FactorPool 的 ChromaDB 存储从 v1 的单一 collection 扩展为**三类文档**：

| Collection | 用途 | 写入方 | 读取方 |
|---|---|---|---|
| `factors` | 已执行的因子（含回测结果） | Critic（Stage 5）| LiteratureMiner（Stage 1）、NoveltyFilter（Stage 3）|
| `research_notes` | 研究笔记归档（探索性记录）| Orchestrator | SynthesisAgent（Stage 2）|
| `exploration_results` | EDA 探索结果归档 | ExplorationAgent（Stage 4a）| AlphaResearcher（Stage 2，反馈用）|

---

## 2. ChromaDB Collection Schema

### `factors` collection（扩展 v1）

```python
# 每个因子文档的字段
{
    # ChromaDB 必需
    "id": factor_id,          # "{island}_{date}_{seq}"
    "document": formula,      # Qlib 公式字符串（用于向量检索）

    # 元数据（ChromaDB metadata，支持过滤）
    "metadata": {
        "island": str,
        "note_id": str,
        "formula": str,
        "hypothesis": str,
        "economic_rationale": str,
        "backtest_report_id": str,
        "verdict_id": str,
        "passed": bool,
        "decision": str,
        "score": float,
        "sharpe": float,
        "ic_mean": float,
        "icir": float,
        "turnover": float,
        "max_drawdown": float,
        "coverage": float,
        "failure_mode": str,
        "reason_codes": str,
        "overfitting_score": float,
        "date": str,
        "tags": str,
        "subspace_origin": str,
    }
}
```

### `research_notes` collection（新增）

```python
{
    "id": note_id,
    "document": hypothesis,   # 用于语义检索

    "metadata": {
        "island": str,
        "proposed_formula": str,
        "final_formula": str,
        "status": str,         # "completed" | "filtered" | "failed"
        "date": str,
        "had_exploration": bool,
    }
}
```

### `exploration_results` collection（新增）

```python
{
    "id": request_id,
    "document": findings,     # EDA 发现（自然语言）

    "metadata": {
        "note_id": str,
        "island": str,
        "question": str,
        "refined_formula_suggestion": str,
        "date": str,
    }
}
```

---

## 3. FactorPool 类更新

```python
# src/factor_pool/pool.py（扩展，不重写）

class FactorPool:
    # ─── 新增方法 ────────────────────────────────────────────

    def register_factor(
        self,
        report: BacktestReport,
        verdict: CriticVerdict,
        risk_report: RiskAuditReport,
        hypothesis: str = "",
        note: Optional[FactorResearchNote] = None,
    ) -> None:
        """将完整执行结果写入 factors collection"""
        factor_spec = report.factor_spec
        subspace_origin = (
            note.exploration_subspace.value if note and note.exploration_subspace else None
        )
        record = FactorPoolRecord(
            factor_id=report.factor_id,
            note_id=report.note_id,
            formula=factor_spec.formula if factor_spec else report.formula,
            hypothesis=factor_spec.hypothesis if factor_spec else hypothesis,
            economic_rationale=factor_spec.economic_rationale if factor_spec else "",
            backtest_report_id=report.report_id,
            verdict_id=verdict.verdict_id,
            decision=verdict.decision or "",
            score=verdict.score,
            sharpe=report.metrics.sharpe,
            ic_mean=report.metrics.ic_mean,
            icir=report.metrics.icir,
            turnover=report.metrics.turnover_rate,
            max_drawdown=report.metrics.max_drawdown,
            coverage=report.metrics.coverage,
            tags=verdict.pool_tags,
            subspace_origin=subspace_origin,
        )
        self.factors_collection.upsert(
            ids=[report.factor_id],
            documents=[record.formula],
            metadatas=[{
                "island": report.island,
                "note_id": record.note_id,
                "formula": record.formula,
                "hypothesis": record.hypothesis,
                "economic_rationale": record.economic_rationale,
                "backtest_report_id": record.backtest_report_id,
                "verdict_id": record.verdict_id,
                "passed": verdict.overall_passed,
                "decision": record.decision,
                "score": record.score,
                "sharpe": record.sharpe,
                "ic_mean": record.ic_mean,
                "icir": record.icir,
                "turnover": record.turnover,
                "max_drawdown": record.max_drawdown,
                "coverage": record.coverage if record.coverage is not None else 0.0,
                "failure_mode": verdict.failure_mode or "",
                "reason_codes": json.dumps(verdict.reason_codes),
                "overfitting_score": risk_report.overfitting_score,
                "date": today_str(),
                "tags": json.dumps(record.tags),
                "subspace_origin": subspace_origin or "",
            }],
        )

    def get_passed_factors(
        self,
        island: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """获取通过审核的因子，用于 RiskAuditor 相关性检测"""
        where = {"passed": True}
        if island:
            where["island"] = island
        results = self.factors_collection.query(
            query_texts=[""],
            n_results=limit,
            where=where,
        )
        return self._format_results(results)

    def get_common_failure_modes(
        self,
        island: str,
        limit: int = 10,
    ) -> list[dict]:
        """获取某 Island 的常见失败模式（给 LiteratureMiner 用）"""
        results = self.factors_collection.query(
            query_texts=[""],
            n_results=limit,
            where={"island": island, "passed": False},
        )
        from collections import Counter
        modes = Counter(
            r["failure_mode"]
            for r in self._format_results(results)
            if r.get("failure_mode")
        )
        return [{"failure_mode": k, "count": v} for k, v in modes.most_common()]

    def get_top_factors(self, limit: int = 20) -> list[dict]:
        """获取全局 Sharpe 最高的因子（给 PortfolioManager 用）"""
        # ChromaDB 不支持 ORDER BY，用 query 后排序
        results = self.factors_collection.query(
            query_texts=[""],
            n_results=min(limit * 3, 100),
            where={"passed": True},
        )
        factors = self._format_results(results)
        factors.sort(key=lambda x: x.get("sharpe", 0), reverse=True)
        return factors[:limit]

    def archive_research_note(self, note: FactorResearchNote) -> None:
        """将 FactorResearchNote 存入 research_notes collection"""
        self.notes_collection.upsert(
            ids=[note.note_id],
            documents=[note.hypothesis],
            metadatas=[{
                "island": note.island,
                "proposed_formula": note.proposed_formula,
                "final_formula": note.final_formula or "",
                "status": note.status,
                "date": today_str(),
                "had_exploration": len(note.exploration_questions) > 0,
            }],
        )

    # ─── 保留 v1 方法（保持向后兼容）───────────────────────
    # get_island_best_factors()  ← 已有，保留
    # get_similar_failures()     ← 已有，保留
    # get_factor_leaderboard()   ← 已有，保留
    # get_global_statistics()    ← 已有，保留
```

当前代码已经支持 `subspace_origin` 写回，但 Stage 5 现行调用链还没有把 `note` 传进 `register_factor()`，所以这条溯源信息仍未端到端落库。最新偏差以 `../overview/05_spec-execution-audit.md` 为准。

---

## 4. 数据库初始化

```python
# src/factor_pool/pool.py __init__ 更新

def __init__(self, persist_directory: str = "data/factor_pool_db"):
    self.client = chromadb.PersistentClient(path=persist_directory)

    # v1 已有
    self.factors_collection = self.client.get_or_create_collection(
        name="factors",
        metadata={"hnsw:space": "cosine"},
    )

    # v2 新增
    self.notes_collection = self.client.get_or_create_collection(
        name="research_notes",
        metadata={"hnsw:space": "cosine"},
    )
    self.explorations_collection = self.client.get_or_create_collection(
        name="exploration_results",
        metadata={"hnsw:space": "cosine"},
    )
```

---

## 5. 测试要求

更新 `tests/test_factor_pool.py`：

```python
def test_register_factor_full():
    """register_factor 应写入 BacktestReport + CriticVerdict + RiskAuditReport"""

def test_get_passed_factors_filter():
    """get_passed_factors(island="momentum") 只返回该 Island 的通过因子"""

def test_get_top_factors_sorted():
    """get_top_factors 应按 Sharpe 降序返回"""

def test_get_common_failure_modes():
    """应正确统计并排序失败模式频率"""

def test_archive_research_note():
    """archive_research_note 应写入 notes collection"""

def test_backward_compatibility():
    """v1 方法（get_island_best_factors 等）在 v2 中仍可调用"""
```
