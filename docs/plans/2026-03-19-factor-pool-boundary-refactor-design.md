# FactorPool Boundary Refactor Design

Status: active
Owner: coordinator
Last Reviewed: 2026-03-19

Purpose: Split FactorPool into explicit storage, write, archive, constraint, and query responsibilities so contract evolution stops concentrating in one file.

---

## Problem

[pool.py](/home/torpedo/Workspace/ML/Pixiu/src/factor_pool/pool.py) 当前同时承担：

- Chroma bootstrap
- embedding function wiring
- factor write path
- note archive
- exploration archive
- failure constraint write path
- ranking / query / similarity search
- 兼容 metadata 翻译

这会带来两个问题：

1. 任一 contract 变化都要穿过同一个大类  
2. Stage 5 写回、历史查询、失败约束之间难以形成清晰的边界

---

## Goal

把 FactorPool 从“全能对象”拆成有明确职责的边界层，同时保持外部 API 的渐进兼容。

---

## Recommended Design

### 1. 拆分 storage bootstrap

新增基础设施层，例如：

- `src/factor_pool/storage.py`

只负责：

- client 初始化
- collection 获取
- embedding function 绑定

### 2. 拆分写入服务

按对象类型拆写入：

- `factor_writer.py`
- `notes_archive.py`
- `exploration_archive.py`
- `constraint_store.py`

### 3. 拆分读取服务

将查询接口按用途拆开：

- `ranking.py`
- `similarity.py`
- `history_queries.py`

### 4. 保留一个 Facade，但不再承载全部逻辑

`FactorPool` 可以保留为 facade，向下组装这些组件，避免一次性打断调用方。

### 5. 收口唯一写回路径

重点要求：

- Stage 5 对“通过因子写入”只能走一条 canonical path
- metadata shape translation 只允许在 facade 边界发生一次

---

## Migration Strategy

### Phase 1

- 先抽 storage bootstrap
- 再抽 factor writer / constraint store
- 让现有 facade 继续对外工作

### Phase 2

- 抽 query / ranking / similarity
- 缩小 `pool.py` 到 façade + wiring

### Phase 3

- 清掉遗留兼容 shape
- 更新文档与审计

---

## Non-Goals

- 不替换 Chroma
- 不在这期里做 graph memory
- 不把 FactorPool 变成控制平面数据库

---

## Exit Criteria

- `pool.py` 不再是唯一事实中心
- Stage 5 写回路径唯一
- notes / exploration / constraints / factors 的读写职责分离
- 新 contract 变更不再需要同时编辑多个平行 metadata shape
