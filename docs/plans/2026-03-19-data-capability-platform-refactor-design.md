# Data Capability Platform Refactor Design

Status: active
Owner: coordinator
Last Reviewed: 2026-03-19

Purpose: Turn Pixiu's dataset/download/normalize/runtime-capability path into one coherent platform instead of a collection of per-dataset adapters.

---

## Problem

当前数据面已经从 `qlib price-volume` 扩展到了：

- `fina_indicator`
- `daily_basic`
- `moneyflow`
- `stk_limit`
- `moneyflow_hsgt`

但系统仍然是“dataset by dataset”接入：

- 每个下载脚本重复一套 batch 逻辑
- 每个 `src/data_pipeline/*.py` 模块单独维护字段与清洗规则
- runtime capability 只在 [capabilities.py](/home/torpedo/Workspace/ML/Pixiu/src/formula/capabilities.py) 暴露一部分字段
- skills / Stage 2 / Stage 3 仍有机会和真实数据面漂移

这意味着：

- 新增一个数据集时，要同时改 staging、normalize、capability、prompt、validator 多处
- “本地数据是否真的可用”没有一个可审计的单点答案

---

## Goal

建立一个统一的数据能力平台，覆盖：

- dataset metadata
- staging contract
- normalize contract
- qlib materialization contract
- runtime capability exposure

让“可下载”“已下载”“已转换”“可在 Stage 2/3 使用”成为同一条流水线，而不是四套口径。

---

## Recommended Design

### 1. 引入 dataset registry

新增一个统一 registry，例如：

- `src/data_pipeline/datasets.py`

每个 dataset 用结构化 spec 描述：

- dataset name
- source type
- staging path
- key columns
- field mapping
- normalize entrypoint
- qlib field exposure
- readiness policy

### 2. 分离 staging truth 和 runtime truth

需要显式区分：

- `staged`: parquet 已落地
- `materialized`: qlib bins 已生成
- `runtime_available`: 覆盖率达到阈值，可进入 Stage 2/3

### 3. 让 capability 从 dataset registry 派生

`src/formula/capabilities.py` 不再手写字段语义，而是从 registry + 本地覆盖率扫描派生出：

- base fields
- experimental fields
- per-field readiness
- prompt-friendly capability text

### 4. 统一下载脚本框架

当前 `tushare_batch.py` 只是第一层抽象。最终目标不是只有“共用 batch loop”，而是：

- 下载脚本只负责 dataset-specific API call
- dataset spec 决定 progress file / staging dir / normalize / readiness policy

### 5. skills 不再硬编码数据 availability

skills 只保留研究方法，不再写死：

- 哪些字段一定可用
- 哪些数据源一定存在

这类信息由 runtime capability 注入。

---

## Proposed Module Shape

- `src/data_pipeline/datasets.py`
  - canonical dataset specs
- `src/data_pipeline/tushare_batch.py`
  - shared batch download runtime
- `src/data_pipeline/readiness.py`
  - staged/materialized/runtime_available 判定
- `src/formula/capabilities.py`
  - 只消费 registry + readiness，不再自己演化成第二份 truth

---

## Non-Goals

- 不在这期里把所有 dataset 都变成 Stage 1 MCP tools
- 不在这期里引入新的向量库或 graph memory
- 不改变 Stage 4/5 执行层逻辑

---

## Exit Criteria

- 新增一个 dataset 时，只需要新增一份 dataset spec + dataset-specific fetch/normalize 逻辑
- Stage 2/3 的可用字段来自统一 capability source
- `skills` 不再硬编码 runtime availability
- 覆盖率、可用性、下载完成度可以被统一报告
