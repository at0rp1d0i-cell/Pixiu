# FactorPool ChromaDB 数据层 — 实施规格说明书

> 面向 Gemini 的执行文档
> 版本：1.0 | 日期：2026-03-05
> 前置条件：结构化输出 + Critic 增强任务已完成（schemas.py 存在）

---

## 任务背景

当前系统每次回测的结果只写在内存 AgentState 里，进程结束后全部丢失。
Researcher 下一轮只能靠 `error_message` 字符串了解上次失败原因，无法查询历史。

本任务目标：
1. 建立 **FactorPool**（ChromaDB 持久化），存储所有历史因子实验
2. 建立 **Island 概念**（因子家族），为后续进化调度做数据基础
3. 通过 **`chromadb_server.py`** 把 FactorPool 暴露为 MCP 工具，Researcher 可调用查询
4. 在 **`orchestrator.py`** 中注册每轮回测结果到 FactorPool

**本任务不做：** Island 选择/调度逻辑（下一个任务做），并发回测（更后面）

---

## 交付物清单

1. `src/factor_pool/__init__.py` — 空文件
2. `src/factor_pool/pool.py` — FactorPool 核心类（ChromaDB 封装）
3. `src/factor_pool/islands.py` — Island 定义（静态常量）
4. `mcp_servers/chromadb_server.py` — MCP Server，暴露 4 个查询工具
5. `src/core/orchestrator.py` — 修改，在 critic 之后注册因子到 FactorPool
6. `tests/test_factor_pool.py` — 验收测试

**不要动的文件：** `researcher.py`、`critic.py`、`coder.py`、`validator.py`、`schemas.py`、`state.py`

---

## 任务 1：创建目录结构

```bash
mkdir -p EvoQuant/src/factor_pool
touch EvoQuant/src/factor_pool/__init__.py
```

---

## 任务 2：创建 `src/factor_pool/islands.py`

**完整文件内容：**

```python
"""
EvoQuant: Island 定义
每个 Island 代表一个因子研究方向（家族）。
Island 概念来自 FunSearch 进化算法，用于防止搜索陷入局部最优。
"""

# Island 名称 → 描述（用于 Researcher 的 System Prompt 上下文注入）
ISLANDS: dict[str, dict] = {
    "momentum": {
        "name": "动量族",
        "description": "基于价格/成交量的动量与反转因子。如近N日收益率、量价相关性、强弱指标。",
        "seed_keywords": ["momentum", "return", "roc", "rsi", "macd"],
    },
    "northbound": {
        "name": "北向资金族",
        "description": "基于沪深港通北向资金流向的因子。北向资金代表外资机构行为，具有趋势性。",
        "seed_keywords": ["northbound", "hsgt", "foreign", "fund_flow"],
    },
    "valuation": {
        "name": "估值族",
        "description": "基于估值指标的因子。如PE分位、PB分位、行业估值相对强弱。",
        "seed_keywords": ["pe", "pb", "valuation", "ratio", "percentile"],
    },
    "volatility": {
        "name": "波动率族",
        "description": "基于价格波动特征的因子。如历史波动率、ATR、波动率偏度。",
        "seed_keywords": ["volatility", "std", "atr", "vix", "vol"],
    },
    "volume": {
        "name": "量价族",
        "description": "量价关系类因子。大单净流入、量价背离、成交量异动。",
        "seed_keywords": ["volume", "turnover", "amount", "big_order"],
    },
    "sentiment": {
        "name": "情绪族",
        "description": "基于市场情绪的因子。研报评级、分析师预期修正、新闻情绪分。",
        "seed_keywords": ["sentiment", "analyst", "rating", "news"],
    },
}

# 默认启动时激活的 Island（按优先级排列）
DEFAULT_ACTIVE_ISLANDS = ["momentum", "northbound", "valuation", "volatility"]
```

---

## 任务 3：创建 `src/factor_pool/pool.py`

**完整文件内容：**

```python
"""
EvoQuant: FactorPool — 因子实验历史库
基于 ChromaDB 持久化，支持：
  - 存储因子假设 + 回测指标
  - 按 Island 分组管理
  - 向量相似检索（相似因子、相似失败案例）
  - Island 排行榜查询
"""
import json
import logging
import os
from datetime import datetime
from typing import Optional

import chromadb
from chromadb.config import Settings

from src.agents.schemas import BacktestMetrics, FactorHypothesis
from .islands import ISLANDS

logger = logging.getLogger(__name__)

# ChromaDB 持久化路径
_DEFAULT_DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "factor_pool_db")
)

# ChromaDB collection 名称
COLLECTION_NAME = "factor_experiments"


class FactorPool:
    """因子实验历史库，支持 Island 分组和向量相似检索。"""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH):
        os.makedirs(db_path, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            # 使用默认的 all-MiniLM-L6-v2 嵌入模型
            # 文档：因子公式 + 假设描述的拼接文本
        )
        logger.info("[FactorPool] 初始化完成，数据库路径：%s", db_path)
        logger.info("[FactorPool] 当前存储因子数量：%d", self._collection.count())

    # ─────────────────────────────────────────────
    # 写入：注册新因子实验
    # ─────────────────────────────────────────────
    def register(
        self,
        hypothesis: FactorHypothesis,
        metrics: BacktestMetrics,
        island_name: str,
        run_id: Optional[str] = None,
    ) -> str:
        """将一次因子实验结果存入 FactorPool。

        Args:
            hypothesis: Researcher 提出的结构化因子假设
            metrics: Critic 解析的回测指标
            island_name: 所属 Island 名称（如 'momentum'）
            run_id: 可选的唯一标识符，默认自动生成

        Returns:
            factor_id: 存储的唯一 ID
        """
        if not run_id:
            run_id = f"{island_name}_{hypothesis.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 向量化文档：公式 + 假设 + 逻辑（用于相似检索）
        document = (
            f"公式: {hypothesis.formula}\n"
            f"假设: {hypothesis.hypothesis}\n"
            f"逻辑: {hypothesis.rationale}"
        )

        # 元数据：所有可查询的结构化字段
        metadata = {
            "island": island_name,
            "factor_name": hypothesis.name,
            "formula": hypothesis.formula,
            "hypothesis": hypothesis.hypothesis,
            "rationale": hypothesis.rationale,
            "expected_direction": hypothesis.expected_direction,
            "market_observation": hypothesis.market_observation or "",
            # 回测指标
            "sharpe": metrics.sharpe,
            "ic": metrics.ic,
            "icir": metrics.icir,
            "turnover": metrics.turnover,
            "annualized_return": metrics.annualized_return,
            "max_drawdown": metrics.max_drawdown,
            "parse_success": metrics.parse_success,
            # 时间戳
            "registered_at": datetime.now().isoformat(),
            # 是否达到基线（方便过滤）
            "beats_baseline": metrics.sharpe > 2.67 and metrics.parse_success,
        }

        self._collection.upsert(
            ids=[run_id],
            documents=[document],
            metadatas=[metadata],
        )
        logger.info(
            "[FactorPool] 注册因子 %s → Island=%s, Sharpe=%.2f",
            hypothesis.name, island_name, metrics.sharpe,
        )
        return run_id

    # ─────────────────────────────────────────────
    # 读取：Island 最优因子
    # ─────────────────────────────────────────────
    def get_island_best_factors(self, island_name: str, top_k: int = 3) -> list[dict]:
        """获取指定 Island 中 Sharpe 最高的 top_k 个因子。

        Args:
            island_name: Island 名称
            top_k: 返回数量，默认 3

        Returns:
            list of dict，每个 dict 包含因子的完整元数据
        """
        results = self._collection.get(
            where={"island": island_name},
            include=["metadatas", "documents"],
        )

        if not results["ids"]:
            return []

        # 按 Sharpe 降序排列
        items = list(zip(results["metadatas"], results["documents"], results["ids"]))
        items.sort(key=lambda x: x[0].get("sharpe", 0.0), reverse=True)

        return [
            {**meta, "document": doc, "id": fid}
            for meta, doc, fid in items[:top_k]
        ]

    # ─────────────────────────────────────────────
    # 读取：相似失败案例（error-driven RAG）
    # ─────────────────────────────────────────────
    def get_similar_failures(self, formula: str, top_k: int = 3) -> list[dict]:
        """查找与给定公式最相似的历史失败因子及其失败原因。

        失败定义：parse_success=True 但 Sharpe <= 2.67（已回测但未达标）。

        Args:
            formula: 当前因子的 Qlib 公式（用于向量相似检索）
            top_k: 返回数量

        Returns:
            list of dict，包含失败因子的元数据和失败上下文
        """
        # 只查失败的（已回测 + 未达标）
        results = self._collection.query(
            query_texts=[formula],
            n_results=min(top_k * 3, max(self._collection.count(), 1)),  # 多取一些再过滤
            where={"$and": [
                {"parse_success": True},
                {"beats_baseline": False},
            ]},
            include=["metadatas", "documents", "distances"],
        )

        if not results["ids"] or not results["ids"][0]:
            return []

        items = list(zip(
            results["metadatas"][0],
            results["documents"][0],
            results["distances"][0],
            results["ids"][0],
        ))
        # 按向量距离排序（最相似在前）
        items.sort(key=lambda x: x[2])

        return [
            {
                **meta,
                "document": doc,
                "similarity_distance": dist,
                "id": fid,
                "failure_reason": _summarize_failure(meta),
            }
            for meta, doc, dist, fid in items[:top_k]
        ]

    # ─────────────────────────────────────────────
    # 读取：Island 排行榜
    # ─────────────────────────────────────────────
    def get_island_leaderboard(self) -> list[dict]:
        """获取所有 Island 的表现排行榜。

        Returns:
            list of dict，每个 Island 一条记录，包含：
            island_name、factor_count、best_sharpe、avg_sharpe、best_factor_name
        """
        all_results = self._collection.get(include=["metadatas"])

        if not all_results["ids"]:
            return []

        # 按 Island 分组统计
        island_stats: dict[str, list[float]] = {}
        island_best: dict[str, dict] = {}

        for meta in all_results["metadatas"]:
            iname = meta.get("island", "unknown")
            sharpe = meta.get("sharpe", 0.0)

            if iname not in island_stats:
                island_stats[iname] = []
                island_best[iname] = meta

            island_stats[iname].append(sharpe)

            if sharpe > island_best[iname].get("sharpe", 0.0):
                island_best[iname] = meta

        leaderboard = []
        for iname, sharpes in island_stats.items():
            best_meta = island_best[iname]
            leaderboard.append({
                "island": iname,
                "island_display_name": ISLANDS.get(iname, {}).get("name", iname),
                "factor_count": len(sharpes),
                "best_sharpe": max(sharpes),
                "avg_sharpe": sum(sharpes) / len(sharpes),
                "best_factor_name": best_meta.get("factor_name", ""),
                "best_factor_formula": best_meta.get("formula", ""),
            })

        # 按 best_sharpe 降序
        leaderboard.sort(key=lambda x: x["best_sharpe"], reverse=True)
        return leaderboard

    # ─────────────────────────────────────────────
    # 读取：全局统计
    # ─────────────────────────────────────────────
    def get_stats(self) -> dict:
        """获取 FactorPool 全局统计信息。"""
        count = self._collection.count()
        if count == 0:
            return {"total_factors": 0, "beats_baseline_count": 0}

        all_results = self._collection.get(include=["metadatas"])
        sharpes = [m.get("sharpe", 0.0) for m in all_results["metadatas"]]
        beats = sum(1 for m in all_results["metadatas"] if m.get("beats_baseline", False))

        return {
            "total_factors": count,
            "beats_baseline_count": beats,
            "global_best_sharpe": max(sharpes) if sharpes else 0.0,
            "global_avg_sharpe": sum(sharpes) / len(sharpes) if sharpes else 0.0,
        }


# ─────────────────────────────────────────────
# 内部辅助函数
# ─────────────────────────────────────────────
def _summarize_failure(meta: dict) -> str:
    """从元数据生成人类可读的失败原因摘要（注入给 Researcher）。"""
    reasons = []
    sharpe = meta.get("sharpe", 0.0)
    ic = meta.get("ic", 0.0)
    icir = meta.get("icir", 0.0)
    turnover = meta.get("turnover", 0.0)

    if sharpe <= 2.67:
        reasons.append(f"Sharpe={sharpe:.2f}（基线2.67）")
    if ic != 0.0 and ic < 0.02:
        reasons.append(f"IC={ic:.4f}（低于0.02）")
    if icir != 0.0 and icir < 0.3:
        reasons.append(f"ICIR={icir:.2f}（不稳定）")
    if turnover != 0.0 and turnover > 50.0:
        reasons.append(f"换手率={turnover:.1f}%（过高）")

    return "；".join(reasons) if reasons else "指标未达标"


# 模块级单例（跨调用复用连接）
_pool_instance: Optional[FactorPool] = None


def get_factor_pool() -> FactorPool:
    """获取 FactorPool 单例。"""
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = FactorPool()
    return _pool_instance
```

---

## 任务 4：创建 `mcp_servers/chromadb_server.py`

**完整文件内容：**

```python
"""
EvoQuant ChromaDB MCP Server
工具：FactorPool 查询（Island 最优、相似失败、排行榜）
注意：只读查询工具，写入通过 orchestrator 直接调用 pool.register()
启动：python mcp_servers/chromadb_server.py
"""
import json
import logging
import sys
import os

# 把项目根目录加入 path（MCP Server 作为独立进程启动）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp.server.fastmcp import FastMCP
from src.factor_pool.pool import get_factor_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("chromadb-mcp")

app = FastMCP("chromadb-mcp")
_pool = get_factor_pool()


@app.tool()
def get_island_best_factors(island_name: str, top_k: int = 3) -> str:
    """获取指定 Island 中历史 Sharpe 最高的因子（供 Researcher 参考）。

    Args:
        island_name: Island 名称，可选值：momentum / northbound / valuation /
                     volatility / volume / sentiment
        top_k: 返回数量，默认 3，最大 5

    返回：JSON 数组，每项包含因子名、公式、Sharpe、IC、ICIR、换手率。
    用途：Researcher 在提新因子前，先了解该方向前人已达到的水平。
    """
    top_k = min(max(top_k, 1), 5)
    try:
        results = _pool.get_island_best_factors(island_name, top_k)
        # 精简返回字段，避免 context 过长
        slim = [
            {
                "factor_name": r["factor_name"],
                "formula": r["formula"],
                "sharpe": r["sharpe"],
                "ic": r["ic"],
                "icir": r["icir"],
                "turnover": r["turnover"],
                "hypothesis": r["hypothesis"],
            }
            for r in results
        ]
        return json.dumps(slim, ensure_ascii=False)
    except Exception as e:
        logger.error("get_island_best_factors error: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@app.tool()
def get_similar_failures(formula: str, top_k: int = 3) -> str:
    """根据当前因子公式，检索历史上相似的失败案例及其原因。

    Args:
        formula: 当前计划提出的 Qlib 因子公式
        top_k: 返回数量，默认 3

    返回：JSON 数组，每项包含相似因子的公式、失败原因摘要。
    用途：避免重蹈覆辙，让 Researcher 知道哪些方向已被验证无效。
    """
    top_k = min(max(top_k, 1), 5)
    try:
        results = _pool.get_similar_failures(formula, top_k)
        slim = [
            {
                "factor_name": r["factor_name"],
                "formula": r["formula"],
                "failure_reason": r["failure_reason"],
                "sharpe": r["sharpe"],
            }
            for r in results
        ]
        return json.dumps(slim, ensure_ascii=False)
    except Exception as e:
        logger.error("get_similar_failures error: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@app.tool()
def get_island_leaderboard() -> str:
    """获取所有 Island 的 Sharpe 排行榜。

    返回：JSON 数组，按 best_sharpe 降序，每项包含 Island 名称、因子数量、
    最高/平均 Sharpe、最优因子名称。
    用途：让 Researcher 了解哪个研究方向目前最有潜力。
    """
    try:
        results = _pool.get_island_leaderboard()
        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        logger.error("get_island_leaderboard error: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@app.tool()
def get_pool_stats() -> str:
    """获取 FactorPool 全局统计（总因子数、超越基线数、全局最优 Sharpe）。

    用途：让 Researcher 了解当前实验进度的全貌。
    """
    try:
        stats = _pool.get_stats()
        return json.dumps(stats, ensure_ascii=False)
    except Exception as e:
        logger.error("get_pool_stats error: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


if __name__ == "__main__":
    logger.info("ChromaDB MCP Server starting...")
    app.run(transport="stdio")
```

---

## 任务 5：修改 `src/core/orchestrator.py`

### 5.1 在文件顶部新增 import（在现有 import 块末尾追加）

```python
from src.factor_pool.pool import get_factor_pool
from src.agents.schemas import FactorHypothesis, BacktestMetrics
```

### 5.2 修改 `run_layer1_ab_test()` 函数

**找到：**
```python
def run_layer1_ab_test():
    """
    运行基于 Layer 1 (quant_factors_dictionary) 的控制变量测试实验
    """
    app = build_graph()

    # 初始化状态
    initial_state = {
        "messages": [],
        "factor_proposal": "",
        "code_snippet": "",
        "backtest_result": "",
        "error_message": "",
        "current_iteration": 0,
        "max_iterations": 3 # 允许模型自我反思重写代码 3 次
    }
```

**替换为：**
```python
def run_layer1_ab_test(island_name: str = "momentum"):
    """
    运行基于 Layer 1 (quant_factors_dictionary) 的控制变量测试实验

    Args:
        island_name: 本轮激活的 Island（因子研究方向），默认 'momentum'
    """
    app = build_graph()
    pool = get_factor_pool()

    # 初始化状态（新增 factor_hypothesis、backtest_metrics、island_name）
    initial_state = {
        "messages": [],
        "factor_proposal": "",
        "factor_hypothesis": None,
        "code_snippet": "",
        "backtest_result": "",
        "backtest_metrics": None,
        "error_message": "",
        "current_iteration": 0,
        "max_iterations": 3,
        # Island 信息（注入给 Researcher 的上下文）
        "island_name": island_name,
    }
```

### 5.3 修改 `try` 块内部，在 `app.invoke()` 之后添加注册逻辑

**找到（try 块内）：**
```python
    try:
        final_state = app.invoke(initial_state)
        logging.info("\n=== 回测探索结束 ===")
        logging.info(f"最终状态迭代次数: {final_state['current_iteration']}")
        if "夏普比率" in final_state.get('backtest_result', ''):
             logging.info(f"最后一次策略输出摘录:\n{final_state['backtest_result'][-500:]}")
    except Exception as e:
        logging.info(f"执行引擎异常退出: {e}")
```

**替换为：**
```python
    try:
        final_state = app.invoke(initial_state)
        logging.info("\n=== 回测探索结束 ===")
        logging.info(f"最终状态迭代次数: {final_state['current_iteration']}")

        # ── 注册最终因子到 FactorPool ───────────────────────────
        hypothesis = final_state.get("factor_hypothesis")
        metrics = final_state.get("backtest_metrics")

        if hypothesis and metrics and metrics.parse_success:
            pool.register(
                hypothesis=hypothesis,
                metrics=metrics,
                island_name=island_name,
            )
            logging.info(
                "[Orchestrator] 因子已注册到 FactorPool → Island=%s, Sharpe=%.2f",
                island_name, metrics.sharpe,
            )
        else:
            logging.info("[Orchestrator] 本轮无有效回测结果，跳过 FactorPool 注册")

        # 打印排行榜
        leaderboard = pool.get_island_leaderboard()
        if leaderboard:
            logging.info("\n=== Island 排行榜 ===")
            for rank, item in enumerate(leaderboard, 1):
                logging.info(
                    "  #%d %s（%s）: best_sharpe=%.2f, 已实验=%d 个因子",
                    rank, item["island_display_name"], item["island"],
                    item["best_sharpe"], item["factor_count"],
                )

    except Exception as e:
        logging.info(f"执行引擎异常退出: {e}")
```

### 5.4 同步修改 AgentState（在 state.py 新增 island_name 字段）

在 `src/agents/state.py` 的 `AgentState` 类中，在 `# ── 状态追踪` 部分新增一行：

```python
    # ── 状态追踪 ───────────────────────────────────────────────
    current_iteration: int
    max_iterations: int
    error_message: str
    island_name: str   # ← 新增：当前激活的 Island 名称
```

---

## 任务 6：在 `researcher.py` 中注入 FactorPool 上下文

Researcher 需要知道：(a) 自己属于哪个 Island，(b) 该 Island 的历史成果。

### 6.1 在 `_MCP_CLIENT` 初始化字典中，新增 chromadb_server 连接

**找到：**
```python
_MCP_CLIENT = MultiServerMCPClient(
    {
        "akshare": {
            "command": "python3",
            "args": [MCP_SERVER_PATH],
            "transport": "stdio",
        }
    }
)
```

**替换为：**
```python
_CHROMADB_SERVER_PATH = os.path.abspath(
    os.path.join(_BASE, "..", "..", "mcp_servers", "chromadb_server.py")
)

_MCP_CLIENT = MultiServerMCPClient(
    {
        "akshare": {
            "command": "python3",
            "args": [MCP_SERVER_PATH],
            "transport": "stdio",
        },
        "chromadb": {
            "command": "python3",
            "args": [_CHROMADB_SERVER_PATH],
            "transport": "stdio",
        },
    }
)
```

### 6.2 在 System Prompt 中注入 Island 上下文和 FactorPool 工具说明

**找到 `system_prompt` 字符串开头的工具列表部分，在工具列表末尾追加：**

在：
```
- get_individual_fund_flow_rank(period, top_n)：个股资金流入排行
```

之后添加：
```
- get_island_best_factors(island_name, top_k)：查询本 Island 历史最优因子（必须调用！）
- get_similar_failures(formula, top_k)：查找相似失败案例，避免重复错误
- get_island_leaderboard()：查看所有 Island 的竞争排行
- get_pool_stats()：查看全局实验统计
```

**在 `system_prompt` 中的"当前迭代"行之前，插入 Island 上下文：**

```python
island_name = state.get("island_name", "momentum")
from src.factor_pool.islands import ISLANDS
island_info = ISLANDS.get(island_name, {})
```

然后在 system_prompt 末尾（`当前迭代` 之前）插入：

```
**你当前所在的研究 Island：**
- Island 代号：{island_name}
- Island 方向：{island_info.get('name', island_name)}
- 研究范围：{island_info.get('description', '')}

**你的工作流程（严格按此顺序）：**
1. 调用 get_island_best_factors('{island_name}') 了解本方向历史最优水平
2. 调用 get_pool_stats() 查看全局进度
3. 调用 1 个市场数据工具（AKShare）了解当前行情
4. 基于以上信息，提出改进或突破性新因子（避免与现有因子相关性>0.8）
5. 以 JSON 格式输出因子假设
```

---

## 任务 7：安装新依赖

```bash
pip install "chromadb>=0.5.0"
```

注意：chromadb 默认使用 `all-MiniLM-L6-v2` 嵌入模型，首次运行会自动下载（约 80MB）。
若网络受限，可预先运行：
```bash
python3 -c "from chromadb.utils import embedding_functions; embedding_functions.DefaultEmbeddingFunction()()"
```

---

## 任务 8：创建 `tests/test_factor_pool.py`

```python
"""验收测试：FactorPool ChromaDB 数据层。"""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.schemas import BacktestMetrics, FactorHypothesis
from src.factor_pool.pool import FactorPool


@pytest.fixture()
def pool(tmp_path):
    """每个测试用独立临时数据库，互不干扰。"""
    return FactorPool(db_path=str(tmp_path / "test_db"))


def _make_hypothesis(name="test_factor", formula="Mean($close, 5) / Ref($close, 5)"):
    return FactorHypothesis(
        name=name,
        formula=formula,
        hypothesis="测试因子",
        rationale="用于单元测试",
    )


def _make_metrics(sharpe=2.0, ic=0.03, icir=0.4, turnover=20.0, success=True):
    return BacktestMetrics(
        sharpe=sharpe, ic=ic, icir=icir, turnover=turnover,
        parse_success=success,
    )


class TestRegister:
    def test_register_basic(self, pool):
        h = _make_hypothesis()
        m = _make_metrics()
        fid = pool.register(h, m, island_name="momentum")
        assert "momentum" in fid
        assert pool._collection.count() == 1

    def test_register_multiple(self, pool):
        for i in range(3):
            pool.register(
                _make_hypothesis(name=f"factor_{i}"),
                _make_metrics(sharpe=2.0 + i * 0.3),
                island_name="momentum",
            )
        assert pool._collection.count() == 3


class TestGetIslandBest:
    def test_returns_sorted_by_sharpe(self, pool):
        pool.register(_make_hypothesis("low"), _make_metrics(sharpe=1.5), "momentum")
        pool.register(_make_hypothesis("mid"), _make_metrics(sharpe=2.5), "momentum")
        pool.register(_make_hypothesis("high"), _make_metrics(sharpe=3.1), "momentum")

        results = pool.get_island_best_factors("momentum", top_k=2)
        assert len(results) == 2
        assert results[0]["sharpe"] == pytest.approx(3.1)
        assert results[1]["sharpe"] == pytest.approx(2.5)

    def test_empty_island(self, pool):
        results = pool.get_island_best_factors("northbound", top_k=3)
        assert results == []

    def test_cross_island_isolation(self, pool):
        pool.register(_make_hypothesis("mom_factor"), _make_metrics(sharpe=3.0), "momentum")
        pool.register(_make_hypothesis("nb_factor"), _make_metrics(sharpe=2.0), "northbound")

        mom = pool.get_island_best_factors("momentum", top_k=5)
        nb = pool.get_island_best_factors("northbound", top_k=5)

        assert all(r["factor_name"] == "mom_factor" for r in mom)
        assert all(r["factor_name"] == "nb_factor" for r in nb)


class TestLeaderboard:
    def test_leaderboard_sorted(self, pool):
        pool.register(_make_hypothesis("a"), _make_metrics(sharpe=2.1), "momentum")
        pool.register(_make_hypothesis("b"), _make_metrics(sharpe=3.2), "northbound")
        pool.register(_make_hypothesis("c"), _make_metrics(sharpe=1.8), "valuation")

        lb = pool.get_island_leaderboard()
        assert lb[0]["island"] == "northbound"
        assert lb[0]["best_sharpe"] == pytest.approx(3.2)

    def test_empty_pool(self, pool):
        assert pool.get_island_leaderboard() == []


class TestStats:
    def test_beats_baseline_count(self, pool):
        pool.register(_make_hypothesis("winner"), _make_metrics(sharpe=2.9), "momentum")
        pool.register(_make_hypothesis("loser"), _make_metrics(sharpe=2.0), "momentum")

        stats = pool.get_stats()
        assert stats["total_factors"] == 2
        assert stats["beats_baseline_count"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

---

## 验收清单

```bash
# Step 1: 安装依赖
pip install "chromadb>=0.5.0"

# Step 2: 运行单元测试
cd EvoQuant
python3 -m pytest tests/test_factor_pool.py -v
# 预期：全部 PASSED

# Step 3: 手动测试 FactorPool 写入和查询
python3 -c "
from src.agents.schemas import FactorHypothesis, BacktestMetrics
from src.factor_pool.pool import get_factor_pool

pool = get_factor_pool()
h = FactorHypothesis(name='test_mom', formula='Mean(\$close,5)/Ref(\$close,5)',
    hypothesis='测试动量因子', rationale='验证数据层')
m = BacktestMetrics(sharpe=2.8, ic=0.035, icir=0.45, turnover=18.0, parse_success=True)
pool.register(h, m, island_name='momentum')
print('排行榜:', pool.get_island_leaderboard())
print('统计:', pool.get_stats())
"

# Step 4: 测试 ChromaDB MCP Server 启动
python3 mcp_servers/chromadb_server.py
# 应看到：ChromaDB MCP Server starting...（Ctrl+C 退出）

# Step 5: 端到端跑一次完整循环（观察注册日志）
python3 EvoQuant/src/core/orchestrator.py
# 确认日志中出现：
#   [FactorPool] 初始化完成
#   [Orchestrator] 因子已注册到 FactorPool → Island=momentum, Sharpe=X.XX
#   === Island 排行榜 ===
```

---

## 注意事项

1. ChromaDB 数据库路径是 `EvoQuant/data/factor_pool_db/`，确保 `data/` 目录在 `.gitignore` 中（已有）
2. `get_factor_pool()` 是模块级单例——不要在 MCP Server 和 Orchestrator 之间共享同一个进程实例（它们是不同进程），ChromaDB 的 `PersistentClient` 会自动处理多进程并发写入
3. `get_similar_failures()` 在 pool 为空时（`count()=0`）会直接返回空列表，不会抛异常
4. `island_name` 字段在 `AgentState` 中是新增的，`orchestrator.py` 的 `run_layer1_ab_test()` 默认传 `"momentum"`，暂时固定；Island 自动选择逻辑是下一个任务
5. ChromaDB 默认嵌入模型需要联网下载，若在离线环境运行，需要提前缓存模型文件
