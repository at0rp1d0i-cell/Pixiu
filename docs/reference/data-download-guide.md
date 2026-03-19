# Pixiu Data Download Guide

Purpose: Explain how to prepare, refresh, and validate the local market data assets used by Pixiu experiments.
Status: active
Audience: both
Canonical: no
Owner: research infra
Last Reviewed: 2026-03-19

## 1. Scope

这篇文档回答的是“本地数据怎么下、先下什么、哪些是当前主路径必需品”。

如果你想看数据层边界和当前运行时真相，先读：

- `docs/design/15_data-sources.md`

这里更偏运维和执行，不重复系统设计。

## 2. Data Assets Map

| 资产 | 当前用途 | 是否主路径必需 | 产物位置 | 脚本 |
|---|---|---|---|---|
| A 股价量 Qlib 数据 | Stage 4 回测直接读取 | 是 | `data/qlib_bin/` | `scripts/download_qlib_data.py` |
| 基本面 parquet 暂存 | 基本面原始 staging | 否 | `data/fundamental_staging/fina_indicator/` | `scripts/download_fundamental_data.py` |
| 基本面 Qlib bins | 供实验扩展字段使用 | 否 | `data/qlib_bin/features/{symbol}/` | `scripts/convert_fundamental_to_qlib.py` |
| 融资融券历史 parquet | 结构化 staging / 后续特征扩展 | 否 | `data/fundamental_staging/margin_history/margin_history.parquet` | `scripts/download_margin_history.py` |

最小可运行集只有一项：

- `data/qlib_bin/` 必须存在且完整，否则 Stage 4 回测跑不起来

## 3. Prerequisites

### 环境

```bash
uv sync --dev
```

### 凭证

以下脚本依赖 `TUSHARE_TOKEN`：

- `scripts/download_fundamental_data.py`
- `scripts/download_margin_history.py`

推荐在 shell 或 `.env` 中设置：

```bash
export TUSHARE_TOKEN=<your_token>
```

### 目录预期

脚本都会自动创建目标目录，但你至少应知道关键产物会出现在哪里：

- `data/qlib_bin/`
- `data/parquet_staging/baostock_raw/`
- `data/fundamental_staging/fina_indicator/`
- `data/fundamental_staging/margin_history/`
- `logs/`

## 4. Recommended Order

### 4.1 只想把 Pixiu 主流程跑起来

只做这一步：

```bash
uv run python scripts/download_qlib_data.py
```

这个脚本会完成三件事：

1. 扩展交易日历到 `data/qlib_bin/calendars/day.txt`
2. 下载全市场 A 股价量数据到 `data/parquet_staging/baostock_raw/`
3. 构建 `data/qlib_bin/` 下的 Qlib 二进制特征

特点：

- 使用 BaoStock
- 支持断点续跑
- 进度写到 `data/qlib_download_progress.json`
- 日志写到 `logs/qlib_download.log`

脚本头部注明，全量大约需要 `2-4` 小时，重跑即可续传。

### 4.2 想补基本面实验字段

先下载原始基本面 parquet：

```bash
uv run python scripts/download_fundamental_data.py
```

可选 dry-run：

```bash
uv run python scripts/download_fundamental_data.py --list-only
```

特点：

- 使用 Tushare `fina_indicator`
- 产物写到 `data/fundamental_staging/fina_indicator/`
- 进度写到 `data/fundamental_download_progress.json`
- 日志写到 `logs/fundamental_download.log`

然后把基本面转成 Qlib bins：

```bash
uv run python scripts/convert_fundamental_to_qlib.py
```

这个脚本的关键前提是：

- `data/fundamental_staging/fina_indicator/` 已有 parquet
- `data/qlib_bin/calendars/day.txt` 已存在

也就是说，它默认依赖你已经先跑过 `download_qlib_data.py`。

### 4.3 想补融资融券历史

```bash
uv run python scripts/download_margin_history.py
```

特点：

- 使用 Tushare `pro.margin`
- 输出单个 parquet：`data/fundamental_staging/margin_history/margin_history.parquet`
- 支持增量更新
- 日志写到 `logs/margin_download.log`

这份数据现在更像结构化 staging，不是当前 Stage 4 主路径直接消费的数据。

## 5. Script-by-script Notes

### `scripts/download_qlib_data.py`

当前最关键的下载脚本。

适用场景：

- 新机器初始化
- 重建 `data/qlib_bin/`
- 扩展 price-volume 回测底座

关键文件：

- `data/qlib_bin/`
- `data/parquet_staging/baostock_raw/`
- `data/qlib_download_progress.json`
- `logs/qlib_download.log`

常用命令：

```bash
uv run python scripts/download_qlib_data.py
tail -f logs/qlib_download.log
```

### `scripts/download_fundamental_data.py`

适用场景：

- 想引入 `eps / roe / roa / gross_margin` 等基本面字段
- 想为后续 PIT 转换准备原始数据

关键文件：

- `data/fundamental_staging/fina_indicator/{ts_code}.parquet`
- `data/fundamental_download_progress.json`
- `logs/fundamental_download.log`

### `scripts/convert_fundamental_to_qlib.py`

适用场景：

- 已经拿到基本面 parquet
- 需要把基本面按 point-in-time 语义写入 Qlib bins

关键事实：

- 脚本按 `ann_date <= t` 做 PIT forward-fill
- 写入位置和价量 bins 共用 `data/qlib_bin/features/{symbol}/`
- 这一步不负责下载，只负责转换

### `scripts/download_margin_history.py`

适用场景：

- 想补融资融券历史
- 想保留可增量更新的结构化 staging 数据

关键文件：

- `data/fundamental_staging/margin_history/margin_history.parquet`
- `logs/margin_download.log`

## 6. Validation Checklist

### 主路径最小检查

```bash
test -f data/qlib_bin/calendars/day.txt && echo ok
find data/qlib_bin/features -maxdepth 2 -name '*.day.bin' | head
```

### 基本面检查

```bash
find data/fundamental_staging/fina_indicator -maxdepth 1 -name '*.parquet' | head
find data/qlib_bin/features -maxdepth 2 \\( -name 'roe.day.bin' -o -name 'roa.day.bin' \\) | head
```

### 融资融券检查

```bash
test -f data/fundamental_staging/margin_history/margin_history.parquet && echo ok
```

### 运行时检查

下载完成后，至少做一次：

```bash
uv run python -m src.core.run_baseline
```

如果你要直接验证 Pixiu 主流程，再跑：

```bash
uv run pixiu run --mode single --island momentum
```

## 7. Operational Notes

- `download_qlib_data.py` 是主路径硬依赖；其余脚本都属于增强项
- 基本面和融资融券数据即使下载完成，也不代表当前默认回测模板会自动使用它们
- 想排查下载进度，优先看 `logs/*.log` 和 `data/*_progress.json`
- 多个脚本都设计成可重跑，不建议手动删进度文件后“硬重来”，除非你明确要全量重建
