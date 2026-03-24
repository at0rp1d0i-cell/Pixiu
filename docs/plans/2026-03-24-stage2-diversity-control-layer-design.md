**Date:** 2026-03-24
**Status:** Approved for implementation

# Stage 2 Diversity Control Layer Design

## Goal

为 `Stage 2` 增加一层正式的 `diversity control layer`，让 `factor_algebra` 的家族坍缩在本地预筛阶段被识别和限制，而不是继续主要依赖：

- prompt 提示
- Stage 3 novelty 事后拦截

这层的目标不是提高所有子空间质量，而是先解决当前最贵的 waste source：

- `factor_algebra` 的 same-family collapse
- 同一批里同一 family 的重复扩张

## Why Now

截至 2026-03-24，`FormulaSketch Lite v1`、`factor_gene v1`、gene-aware novelty 都已进入主线，低级 contract 错误已经显著下降。

当前真实瓶颈变成：

- `factor_algebra` 仍然在同一轮里重复长出同 family 变体
- `Stage 3` 的 novelty 继续替上游的 collapse 背锅
- prompt-only 的 family steering 已验证不够强

所以下一步不能继续加提示词，而必须正式引入一个新的运行时层。

## Alternatives

### Option 1: Continue prompt steering

做法：

- 继续增强 anti-collapse prompt
- 增加更多 family memory 示例

优点：

- 改动最小

缺点：

- 已经验证不够强
- 本质仍然是语言提醒，不是控制层

### Option 2: Stage 2 local diversity control layer

做法：

- 在 `researcher._local_prescreen_notes()` 中加入本地 family budget / saturation gate
- 只对 `factor_algebra` 生效
- 独立记录 `anti_collapse`

优点：

- 正式补上缺失架构层
- 能直接减少 Stage 3 novelty 背锅
- 可测试、可诊断

缺点：

- 会引入新的本地过滤语义

### Option 3: Pre-generation family quota planner

做法：

- 在生成前就先按 family 配额调度
- 甚至让 Stage 2 先选 family，再让 LLM 只在选中的 family 周围生成

优点：

- 长期更强

缺点：

- 当前太重
- 需要更完整的 family archive / scheduler 联动

## Chosen Now

选择 **Option 2**。

也就是：

> 在 Stage 2 本地预筛里新增 `diversity control layer`，先只处理 `factor_algebra`。

## Placement

这层放在：

- `src/agents/researcher.py`
- `AlphaResearcher._local_prescreen_notes()`

顺序固定为：

1. `recipe / validator`
2. `diversity control`
3. `novelty`
4. `pass`

原因：

- 低级 recipe/validator 错误先吃掉
- family collapse 先在本地控制
- Stage 3 novelty 只处理剩余未被 Stage 2 吃掉的历史重复

## Scope

In scope:

- `factor_algebra` only
- same-batch family budget
- historical saturated-family gate
- `anti_collapse` diagnostics

Out of scope:

- 其他 subspace
- scheduler-level diversity weights
- pre-generation family planning
- schema 变更

## Rules

### Rule 1: Same-batch family budget

同一批生成候选中：

- 同一个 `family_gene_key` 最多保留 `1` 个

其余候选：

- 本地拒绝
- filter 记为 `anti_collapse`

### Rule 2: Historical saturated-family gate

若当前 island 历史里同一个 `family_gene_key` 的已知变体数达到阈值，则本轮新候选直接记为：

- `anti_collapse`

`v1` 默认阈值：

- `2`

这里的“历史”优先读取：

- `get_passed_factors(island=...)`

若拿不到，再回退：

- `get_island_factors(island=...)`

### Rule 3: Diagnostics split

`anti_collapse` 必须从 `novelty` 中独立出来。

也就是说，artifact 里要能单独看到：

- `validator`
- `anti_collapse`
- `novelty`

避免后面继续把 `same-family collapse` 误判成 Stage 3 问题。

## Data Sources

本层只依赖当前已有对象：

- `factor_gene_by_note_id`
- `family_gene_key`
- `variant_gene_key`
- `FactorPool`

不新增 schema，不新增持久化对象。

## Why This Is Not A Patch

这层不是“又加一个 if”，而是把缺失的控制面正式收成一个阶段层：

- `FormulaSketch` 负责 contract
- `factor_gene` 负责表示
- `diversity control layer` 负责 Stage 2 的本地多样性控制
- `Stage 3 novelty` 负责剩余历史重复

它是缺失架构层，不是现象级修补。

## Testing

### Validation Mode

- `Fast feedback`

### Command

```bash
uv run pytest -q tests/test_stage2.py -k "anti_collapse or factor_gene or diversity"
env QLIB_DATA_DIR=/home/torpedo/Workspace/ML/Pixiu/data/qlib_bin REPORT_EVERY_N_ROUNDS=999 PIXIU_LLM_DEFAULT_PROVIDER=openai PIXIU_HUMAN_GATE_AUTO_ACTION=approve uv run pixiu run --mode single --island momentum
```

### Proof Artifact

- `data/experiment_runs/{run_id}/round_000.json`

成功标准：

- `factor_algebra` 的 `anti_collapse` 出现在 diagnostics 中
- `novelty` 不再继续吞同批 same-family 重复
- `factor_algebra` 的 delivered 不因同批 family 扩张而归零

## Runtime Concession Check

Concession check: 不新增新的 runtime concession。

理由：

- 这是 Stage 2 缺失的正式控制层
- 不是 experiment-only shortcut
- 不是 fallback 或 compat bridge

若后续演化成 profile-only 开关，再考虑进入 `06_runtime-concessions.md`。
