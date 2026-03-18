# SynthesisAgent: 跨 Island 语义关联与去重
Purpose: Define the cross-island synthesis and de-duplication layer in Stage 2.
Status: active
Audience: implementer
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-18

> 版本：1.0 | 日期：2026-03-16
> 依赖：`21_stage-2-hypothesis-expansion.md`, `14_factor-pool.md`
> 实施计划：`docs/archive/plans/phase-2-hypothesis-engine.md` §2.2

---

## 1. 问题定义

当前 `synthesis_node` 是空壳：

```python
def synthesis_node(state: AgentState) -> dict:
    logger.info("[Stage 2b] Synthesis（pass-through）: %d 个候选", len(state.research_notes))
    return {}  # 保持状态不变
```

Stage 2 每轮生成 12-18 个候选，直通 Stage 3。问题：

- **隐性重复**：不同 island 可能独立生成语义相似的假设（如 momentum 和 volume 都生成了"放量突破"因子）
- **缺少 family 意识**：一组相关因子可能是同一 mechanism 的变体，应被识别为 family
- **跨 island 机会丢失**：两个 island 的互补假设可能合并为更强的因子

## 2. 设计目标

1. 确定性去重：语义相似度 > 阈值的 pair，保留更优的一个
2. Factor family 聚类：识别隐含的因子族
3. Cross-island merge 建议：提出跨 island 合并候选
4. 输出结构化的 `SynthesisInsight`
5. 不阻塞主链：去重和聚类失败时降级为 pass-through

## 3. 架构

```
research_notes (12-18 个)
       │
       ▼
┌──────────────────┐
│  1. Vectorize    │  embedding 所有 hypothesis 文本
│     (确定性)      │
├──────────────────┤
│  2. Deduplicate  │  cosine similarity > 0.85 → 合并
│     (确定性)      │
├──────────────────┤
│  3. Cluster      │  层次聚类 → factor families
│     (确定性)      │
├──────────────────┤
│  4. Merge Suggest│  跨 island 互补假设 → 合并候选
│     (LLM 辅助)   │  （可选，降级为空列表）
└──────────────────┘
       │
       ▼
filtered_notes + synthesis_insights
```

### 确定性 vs LLM 分界

| 步骤 | 方法 | 理由 |
|------|------|------|
| Vectorize | TF-IDF / sentence-transformers | 需要数值相似度 |
| Deduplicate | cosine threshold | 可复现、可审计 |
| Cluster | 层次聚类 (scipy) | 无需调参，稳定 |
| Merge suggest | LLM (可选) | 需要语义理解做跨域合并 |

## 4. Schema

已存在于 `src/schemas/research_note.py`：

```python
class SynthesisInsight(PixiuBase):
    island_a: str
    island_b: str
    note_id_a: str
    note_id_b: str
    relationship: str           # "duplicate" | "complement" | "family"
    combined_hypothesis: Optional[str]
    priority: str               # "high" | "medium" | "low"
```

新增输出容器：

```python
class SynthesisResult(PixiuBase):
    """SynthesisAgent 的完整输出"""
    filtered_notes: List[FactorResearchNote]      # 去重后的 notes
    removed_notes: List[str]                       # 被去重移除的 note_id
    insights: List[SynthesisInsight]               # 发现的关联
    families: Dict[str, List[str]]                 # family_label → [note_ids]
    merge_candidates: List[SynthesisInsight]       # 建议合并的 pairs
```

## 5. 实现规格

### 5.1 SynthesisAgent 类

```python
# src/agents/synthesis.py

class SynthesisAgent:
    DEDUP_THRESHOLD = 0.85       # cosine similarity 去重阈值
    FAMILY_THRESHOLD = 0.60      # 聚类阈值
    MAX_MERGE_CANDIDATES = 3     # 最多建议合并数

    def __init__(self, vectorizer: str = "tfidf"):
        """
        vectorizer: "tfidf" (默认，无外部依赖) 或 "sentence-transformers"
        """
        self.vectorizer = vectorizer

    async def synthesize(
        self,
        notes: List[FactorResearchNote],
    ) -> SynthesisResult:
        if len(notes) <= 1:
            return SynthesisResult(
                filtered_notes=notes,
                removed_notes=[],
                insights=[],
                families={},
                merge_candidates=[],
            )

        # Step 1: Vectorize
        vectors = self._vectorize(notes)

        # Step 2: Deduplicate
        filtered, removed, dedup_insights = self._deduplicate(notes, vectors)

        # Step 3: Cluster into families
        families, family_insights = self._cluster_families(filtered, vectors)

        # Step 4: Cross-island merge suggestions (可选 LLM)
        merge_candidates = self._suggest_merges(filtered, vectors)

        return SynthesisResult(
            filtered_notes=filtered,
            removed_notes=removed,
            insights=dedup_insights + family_insights,
            families=families,
            merge_candidates=merge_candidates,
        )
```

### 5.2 向量化策略

**MVP (TF-IDF)**：
- 拼接 `hypothesis + economic_intuition + proposed_formula` 作为文档
- 使用 `sklearn.feature_extraction.text.TfidfVectorizer`
- 优点：无外部模型依赖，速度快
- 缺点：对中文语义理解有限

**进阶 (sentence-transformers)**：
- 使用 `paraphrase-multilingual-MiniLM-L12-v2`（支持中文）
- 在候选数量 < 50 时延迟开销可接受
- 通过环境变量 `SYNTHESIS_VECTORIZER=sentence-transformers` 启用

### 5.3 去重逻辑

```python
def _deduplicate(self, notes, vectors) -> Tuple[list, list, list]:
    from sklearn.metrics.pairwise import cosine_similarity

    sim_matrix = cosine_similarity(vectors)
    removed_ids = set()
    insights = []

    for i in range(len(notes)):
        if notes[i].note_id in removed_ids:
            continue
        for j in range(i + 1, len(notes)):
            if notes[j].note_id in removed_ids:
                continue
            if sim_matrix[i][j] > self.DEDUP_THRESHOLD:
                # 保留公式更复杂的（启发式：更长的公式通常更有信息量）
                keep, drop = (i, j) if len(notes[i].proposed_formula) >= len(notes[j].proposed_formula) else (j, i)
                removed_ids.add(notes[drop].note_id)
                insights.append(SynthesisInsight(
                    island_a=notes[keep].island,
                    island_b=notes[drop].island,
                    note_id_a=notes[keep].note_id,
                    note_id_b=notes[drop].note_id,
                    relationship="duplicate",
                    combined_hypothesis=None,
                    priority="low",
                ))

    filtered = [n for n in notes if n.note_id not in removed_ids]
    return filtered, list(removed_ids), insights
```

### 5.4 Family 聚类

```python
def _cluster_families(self, notes, vectors) -> Tuple[dict, list]:
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    from sklearn.metrics.pairwise import cosine_similarity

    if len(notes) < 3:
        return {}, []

    sim_matrix = cosine_similarity(vectors)
    dist_matrix = 1 - sim_matrix
    # 确保对角线为 0，防止浮点误差
    for i in range(len(dist_matrix)):
        dist_matrix[i][i] = 0.0
        for j in range(i):
            dist_matrix[i][j] = dist_matrix[j][i] = max(0, (dist_matrix[i][j] + dist_matrix[j][i]) / 2)

    condensed = squareform(dist_matrix)
    linkage_matrix = linkage(condensed, method='average')
    labels = fcluster(linkage_matrix, t=1 - self.FAMILY_THRESHOLD, criterion='distance')

    # 按 label 分组
    families = {}
    for note, label in zip(notes, labels):
        key = f"family_{label}"
        families.setdefault(key, []).append(note.note_id)

    # 只保留 size > 1 的 family
    families = {k: v for k, v in families.items() if len(v) > 1}

    insights = []
    for family_label, note_ids in families.items():
        # 为 family 中每对生成 insight
        for a, b in zip(note_ids, note_ids[1:]):
            insights.append(SynthesisInsight(
                island_a=self._get_island(notes, a),
                island_b=self._get_island(notes, b),
                note_id_a=a,
                note_id_b=b,
                relationship="family",
                combined_hypothesis=None,
                priority="medium",
            ))

    return families, insights
```

### 5.5 Merge 建议（可选 LLM）

只在跨 island 的高相似度 pair 上触发，且限制数量：

```python
def _suggest_merges(self, notes, vectors) -> List[SynthesisInsight]:
    from sklearn.metrics.pairwise import cosine_similarity

    sim_matrix = cosine_similarity(vectors)
    candidates = []

    for i in range(len(notes)):
        for j in range(i + 1, len(notes)):
            # 只关注跨 island 的相似对
            if notes[i].island == notes[j].island:
                continue
            sim = sim_matrix[i][j]
            if 0.50 < sim < self.DEDUP_THRESHOLD:  # 相似但不重复
                candidates.append((i, j, sim))

    # 取 top-K
    candidates.sort(key=lambda x: x[2], reverse=True)
    candidates = candidates[:self.MAX_MERGE_CANDIDATES]

    merge_insights = []
    for i, j, sim in candidates:
        merge_insights.append(SynthesisInsight(
            island_a=notes[i].island,
            island_b=notes[j].island,
            note_id_a=notes[i].note_id,
            note_id_b=notes[j].note_id,
            relationship="complement",
            combined_hypothesis=None,  # LLM 填充（Phase 2.2 后续迭代）
            priority="high" if sim > 0.70 else "medium",
        ))

    return merge_insights
```

## 6. Orchestrator 集成

### 6.1 synthesis_node 更新

```python
# src/core/orchestrator/nodes/stage2.py

def synthesis_node(state: AgentState) -> dict:
    from src.agents.synthesis import SynthesisAgent

    notes = state.research_notes
    if len(notes) <= 1:
        logger.info("[Stage 2b] Synthesis: <= 1 个候选，跳过")
        return {}

    logger.info("[Stage 2b] Synthesis: 处理 %d 个候选...", len(notes))

    async def _run():
        agent = SynthesisAgent()
        return await agent.synthesize(notes)

    try:
        result = asyncio.run(_run())
        removed = len(notes) - len(result.filtered_notes)
        logger.info(
            "[Stage 2b] Synthesis 完成：去重 %d 个，识别 %d 个 family，%d 个 merge 建议",
            removed, len(result.families), len(result.merge_candidates),
        )
        return {
            "research_notes": result.filtered_notes,
            "synthesis_insights": result.insights + result.merge_candidates,
        }
    except Exception as e:
        logger.warning("[Stage 2b] Synthesis 失败（降级为 pass-through）: %s", e)
        return {}
```

### 6.2 AgentState 扩展

需要在 `src/schemas/state.py` 中添加字段：

```python
class AgentState(PixiuBase):
    # ... 现有字段 ...
    synthesis_insights: List[SynthesisInsight] = []
```

## 7. 降级策略

SynthesisAgent 必须是 **best-effort**，任何失败都不应阻塞主链：

| 失败场景 | 降级行为 |
|----------|----------|
| vectorizer 不可用 | 跳过去重，直接 pass-through |
| 聚类失败（notes < 3） | 跳过 family 检测 |
| LLM 调用失败 | 跳过 merge 建议 |
| 任何未知异常 | 返回空 dict（等效 pass-through） |

## 8. 测试要求

### 8.1 单元测试

- `test_dedup_identical_hypotheses`：两个相同假设 → 保留一个
- `test_dedup_different_hypotheses`：两个不同假设 → 保留两个
- `test_family_clustering`：3 个相关假设 → 识别为 1 个 family
- `test_cross_island_merge`：不同 island 的互补假设 → 产出 merge 建议
- `test_empty_input`：0 个输入 → 空输出
- `test_single_input`：1 个输入 → 直通

### 8.2 集成测试

- `test_synthesis_node_not_passthrough`：验证 synthesis_node 实际调用 SynthesisAgent
- `test_e2e_with_synthesis`：mock 环境下 e2e 测试包含 synthesis 去重

### 8.3 回归

- 现有 `test_e2e_pipeline.py` 的 3 个 smoke test 必须继续通过（synthesis 对 mock 数据降级为 pass-through 即可）

## 9. 依赖

新增运行时依赖：
- `scikit-learn` — TF-IDF + cosine similarity（已在 `pyproject.toml` 中）
- `scipy` — 层次聚类（已在 `pyproject.toml` 中）

可选：
- `sentence-transformers` — 进阶向量化（暂不添加，通过环境变量启用时再安装）
