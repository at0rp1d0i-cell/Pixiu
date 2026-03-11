# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pixiu (貔貅) is an LLM-native alpha mining platform for A-share quantitative research. Unlike traditional "AI quant" systems that simulate human research teams, Pixiu is designed around what LLMs do better than humans: parallel hypothesis generation, permanent failure memory, and high-throughput filtering.

**Core Philosophy**: The system is bottlenecked by backtest execution time (5-10 min/run), not by hypothesis generation. Therefore, use cheap LLM stages to generate many candidates, filter through multiple stages, and only run expensive backtests on the best ideas.

## Architecture: 5-Stage High-Throughput Funnel

```
Stage 1: Wide Scan (MarketAnalyst + LiteratureMiner) → MarketContextMemo
Stage 2: Parallel Hypothesis Generation (6 AlphaResearcher agents) → 12-18 candidates
Stage 3: Three-Dimensional Pre-filter (Validator + NoveltyFilter + AlignmentChecker) → Top-K
Stage 4: Execution (ExplorationAgent + Coder) → BacktestReport
Stage 5: Judgment (Critic → RiskAuditor → PortfolioManager) → CIOReport
```

**6 Research Islands**: `momentum`, `northbound`, `valuation`, `volatility`, `volume`, `sentiment`
- Each Island has its own AlphaResearcher, failure history, and softmax-sampled scheduling
- Islands prevent search from converging to local optima (inspired by FunSearch)

## Key Design Decisions

1. **Coder is deterministic** — zero LLM calls in backtest execution. Factor formulas are filled into a Qlib template and executed via Docker subprocess.

2. **Error-driven RAG** — When factors fail, failure reasons are stored in ChromaDB. Next AlphaResearcher retrieves similar past failures as negative examples.

3. **Document-driven interfaces** — All agents communicate through typed Pydantic schemas (`FactorResearchNote`, `BacktestReport`, `CriticVerdict`). No dict passing.

4. **Human-in-the-loop minimally** — System runs autonomously (Stage 1-4). Humans receive `CIOReport` and choose: `approve`, `redirect:<island>`, or `stop`.

## Development Commands

### Environment Setup
```bash
# Create environment
conda create -n pixiu python=3.11
conda activate pixiu
pip install -e .

# Configure credentials
cp .env.example .env
# Edit .env: set RESEARCHER_API_KEY, CODER_MODEL, etc.
```

### Data Pipeline
```bash
# Download A-share data (CSI 300)
python -m src.data_pipeline.data_downloader
python -m src.data_pipeline.format_to_qlib

# Run baseline (establishes benchmark)
python -m src.core.run_baseline
```

### Running Research
```bash
# Single-island research (debug mode)
python -m src.core.orchestrator --mode single --island momentum

# Full evolution loop
python -m src.core.orchestrator --mode evolve --rounds 20

# CLI commands (via pyproject.toml entry point)
pixiu status
pixiu factors --top 10
pixiu approve --factor-id <id>
```

### Testing
```bash
# Run all tests
pytest

# Run specific test modules
pytest tests/test_factor_pool.py
pytest tests/test_market_context.py
pytest tests/test_prefilter.py
pytest tests/test_stage2_batch.py

# Run with verbose output
pytest -v

# Run single test
pytest tests/test_schemas.py::test_specific_function -v
```

### MCP Servers
```bash
# Test AKShare MCP server
pytest tests/test_akshare_mcp.py

# ChromaDB server is auto-initialized by FactorPool
```

## Code Structure

### Core Orchestration
- `src/core/orchestrator.py` — 12-node LangGraph StateGraph implementing the 5-stage funnel
- `src/schemas/state.py` — AgentState for LangGraph state management
- `src/factor_pool/scheduler.py` — IslandScheduler with softmax sampling and temperature annealing
- `src/factor_pool/pool.py` — FactorPool (ChromaDB-backed) for experiment history and RAG retrieval
- `src/factor_pool/islands.py` — Island definitions (6 research directions)

### Stage 1: Market Context
- `src/agents/market_analyst.py` — Generates MarketContextMemo from AKShare data
- `src/agents/literature_miner.py` — Retrieves historical insights from FactorPool
- `src/schemas/market_context.py` — MarketContextMemo schema

### Stage 2: Hypothesis Generation
- `src/agents/researcher.py` — AlphaResearcher agent (batch generation: 2-3 notes per call)
- `src/schemas/research_note.py` — FactorResearchNote and AlphaResearcherBatch schemas

### Stage 3: Pre-filtering
- `src/agents/prefilter.py` — Three-dimensional filter (Validator + NoveltyFilter + AlignmentChecker)
- `src/agents/validator.py` — Qlib syntax validation and A-share constraints

### Stage 4: Execution (v2 Golden Path - Deterministic)
- `src/execution/coder.py` — **确定性回测执行器**（零 LLM 调用，纯模板化）
- `src/execution/docker_runner.py` — Docker subprocess 封装
- `src/execution/templates/qlib_backtest.py.tpl` — Qlib 回测模板
- `src/execution/exploration_agent.py` — Optional EDA scripts (不在 Golden Path 范围内)
- `src/schemas/backtest.py` — BacktestReport (ExecutionMeta, FactorSpecSnapshot, BacktestMetrics, ArtifactRefs)

### Stage 5: Judgment (v2 Golden Path - Deterministic)
- `src/agents/critic.py` — **确定性判定引擎**（零 LLM 调用，纯规则引擎）
- `src/agents/factor_pool_writer.py` — FactorPool 写回逻辑
- `src/agents/cio_report_renderer.py` — 确定性 Markdown 报告渲染器
- `src/schemas/judgment.py` — CriticVerdict (decision, score, reason_codes)
- `src/schemas/factor_pool_record.py` — FactorPoolRecord 写回结构

### Data & API
- `src/data_pipeline/data_downloader.py` — BaoStock data fetcher
- `src/data_pipeline/format_to_qlib.py` — Convert to Qlib format
- `src/api/server.py` — FastAPI backend (6 endpoints)
- `src/cli/main.py` — Typer CLI (7 commands)

### MCP Servers
- `mcp_servers/akshare_server.py` — AKShare data provider (northbound flows, sector PE, etc.)
- `mcp_servers/chromadb_server.py` — ChromaDB vector store interface

### Skills & Utilities
- `src/skills/loader.py` — Dynamic skill loading system
- `src/schemas/thresholds.py` — Backtest quality thresholds (Sharpe, IC, ICIR)

## v2 Golden Path 确定性闭环（重要）

根据 `docs/specs/v2_stage45_golden_path.md` 实现的确定性流程：

```python
# Stage 4: 确定性回测执行
from src.execution.coder import Coder
from src.schemas.research_note import FactorResearchNote

note = FactorResearchNote(
    note_id="momentum_001",
    island="momentum",
    final_formula="Ref($close, 20) / $close - 1",
    # ... 其他字段
)

coder = Coder()
report = await coder.run_backtest(note)  # 返回 BacktestReport

# Stage 5: 确定性判定
from src.agents.critic import Critic
from src.agents.factor_pool_writer import FactorPoolWriter
from src.agents.cio_report_renderer import CIOReportRenderer

critic = Critic()
verdict = critic.evaluate(report)  # 返回 CriticVerdict (decision, score, reason_codes)

# 写入 FactorPool
writer = FactorPoolWriter(pool)
factor_id = writer.write_record(report, verdict)

# 生成 CIO 报告
renderer = CIOReportRenderer()
cio_report = renderer.render(report, verdict, factor_id)
```

**关键特性**：
- Stage 4 和 Stage 5 都是**零 LLM 调用**
- 相同输入产生相同输出（确定性）
- 错误分类：compile/run/parse/judge
- 产物落盘到 `data/artifacts/{run_id}/`

## Important Patterns

### Pydantic Schemas Are Immutable
All agent outputs use Pydantic models. To modify a schema instance:
```python
# WRONG: memo.field = new_value  # Raises ValidationError
# CORRECT:
memo = memo.model_copy(update={"field": new_value})
```

### LangGraph State Updates
State updates in orchestrator nodes must return dicts:
```python
def node_function(state: AgentState) -> dict:
    # Process state...
    return {"field_to_update": new_value}  # Partial update
```

### FactorPool RAG Pattern
```python
from src.factor_pool.pool import get_factor_pool

pool = get_factor_pool()  # Singleton pattern

# Store experiment
pool.register(hypothesis, metrics, island_name="momentum")

# Retrieve similar failures
failures = pool.query_similar_failures(
    query_text="momentum reversal factor",
    island_name="momentum",
    top_k=5
)
```

### Island Scheduling
```python
from src.factor_pool.scheduler import IslandScheduler

scheduler = IslandScheduler(pool=pool)
next_island = scheduler.select_next_island()  # Softmax sampling
scheduler.record_result(island_name, sharpe_ratio)  # Update weights
```

### Async Agent Calls
Stage 2 runs 6 AlphaResearchers in parallel:
```python
tasks = [researcher.generate_batch(island, context) for island in ACTIVE_ISLANDS]
results = await asyncio.gather(*tasks)
```

## Data Sources

- **Price/Volume**: BaoStock (free, no API key required)
- **Northbound flows, sector PE**: AKShare (free, via MCP server)
- **Factor storage**: ChromaDB (local persistent, path: `data/factor_pool_db/`)
- **Backtest engine**: Qlib (subprocess execution in Docker)

## Environment Variables (.env)

```bash
# LLM API Keys
RESEARCHER_API_KEY=sk-...          # For AlphaResearcher (Stage 2)
CODER_MODEL=gpt-4                  # Not used (Coder is deterministic)
CRITIC_API_KEY=sk-...              # For Critic (Stage 5)

# System Config
MAX_ROUNDS=100                     # Evolution loop limit
ACTIVE_ISLANDS=momentum,northbound,valuation,volatility,volume,sentiment
REPORT_EVERY_N_ROUNDS=5            # CIO report frequency
MAX_CONCURRENT_BACKTESTS=2         # Parallel backtest limit

# Feature Flags
FUNDAMENTAL_FIELDS_ENABLED=false   # Enable $pe_ttm, $pb, $roe, etc.
```

## Qlib Field Constraints

**Always available**: `$close`, `$open`, `$high`, `$low`, `$volume`, `$factor`, `$amount`, `$vwap`

**Conditional** (requires `FUNDAMENTAL_FIELDS_ENABLED=true`): `$pe_ttm`, `$pb`, `$roe`, `$revenue_yoy`, `$profit_yoy`, `$turnover_rate`, `$float_mv`

**Forbidden**: `Ref($close, -N)` (future data leakage), unregistered field names

## Academic References

The architecture is grounded in recent LLM-quant research:
- **AlphaAgent** (arXiv:2502.16789) — Three-dimensional pre-filter design
- **RD-Agent** (arXiv:2505.15155) — Document-driven interface principle
- **QuantaAlpha** (arXiv:2602.07085) — Exploration agent design
- **CogAlpha** (arXiv:2511.18850) — Multi-agent quality hierarchy
- **QuantAgent** (arXiv:2402.03755) — Dual-loop island evolution

## Documentation

- `docs/specs/v2_architecture_overview.md` — **Read this first** (P0 dependency for all other specs)
- `docs/specs/v2_orchestrator.md` — LangGraph implementation details
- `docs/specs/v2_stage2_hypothesis_generation.md` — AlphaResearcher batch generation
- `docs/specs/v2_stage4_execution.md` — Coder + ExplorationAgent
- `docs/specs/v2_stage5_judgment.md` — Critic + RiskAuditor + PortfolioManager
- `docs/plans/` — Implementation plans and roadmap
- `README.md` — Project overview and quick start

## Common Pitfalls

1. **Don't modify Coder to use LLMs** — It's intentionally deterministic. LLM calls belong in Researcher/Critic, not execution.

2. **Don't bypass the funnel** — Every candidate must go through Stage 3 pre-filter before backtest. No shortcuts.

3. **Don't forget Island context** — AlphaResearcher prompts must include Island description and historical failures from that Island.

4. **Don't use `Ref($close, -N)`** — This is future data leakage. Use `Ref($close, N)` (positive N = lookback).

5. **ChromaDB path is relative** — FactorPool stores data in `data/factor_pool_db/` relative to project root. Don't hardcode absolute paths.

6. **LangGraph checkpoints** — Orchestrator uses MemorySaver for state persistence. Don't assume state is lost between runs.
