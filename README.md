# Pixiu 貔貅

**An LLM-native Alpha mining platform for quantitative research — not a simulated quant team, but a system designed around what LLMs actually do better than humans.**

> 一个为 Agent 而设计的量化研究平台，不是让 AI 替代人类研究员，而是重新设计研究流程本身。

---

## Why Pixiu?

Traditional quant research is bottlenecked by **human bandwidth** — a researcher reads 10 reports per day, takes days to implement a factor, and forgets failure cases from two years ago.

LLM systems are bottlenecked by **backtest execution time** (5–10 min/run in Qlib).

Most "AI quant" projects ignore this distinction and simply put LLMs in a human's seat. Pixiu doesn't.

| Human team constraint | Pixiu's design choice |
|---|---|
| One researcher, one direction at a time | 6 `AlphaResearcher` agents in parallel — cost scales linearly |
| Researchers forget past failures | `FactorPool` stores every failure permanently; RAG-driven recall |
| Career risk → conservative hypothesis space | Agents explore without bias |
| Days from idea to backtest result | Minutes: `Researcher → Validator → Backtest → Critic` |
| 1 research note per cycle | 12–18 candidates per round, funnel-filtered before backtest |

---

## Architecture

Pixiu uses a **5-stage high-throughput funnel** — wide generation on the cheap, staged filtering, and only the best candidates reach the expensive backtest stage.

```
╔══════════════════════════════════════════════════════════════════╗
║  Stage 1 · Wide Scan                          [cost: near-zero]  ║
║  MarketAnalyst + LiteratureMiner                                 ║
║  → MarketContextMemo (macro signals, northbound flows, themes)   ║
╠══════════════════════════════════════════════════════════════════╣
║  Stage 2 · Parallel Hypothesis Generation          [cost: low]   ║
║  6 × AlphaResearcher (one per Island, async parallel)            ║
║  Each outputs 2–3 FactorResearchNote candidates                  ║
║  → 12–18 candidates total per round                              ║
╠══════════════════════════════════════════════════════════════════╣
║  Stage 3 · Three-Dimensional Pre-filter            [cost: low]   ║
║  Filter A: Validator    — Qlib syntax + A-share constraints      ║
║  Filter B: NoveltyFilter — AST Jaccard vs FactorPool (no LLM)    ║
║  Filter C: AlignmentChecker — semantic consistency (fast LLM)    ║
║  → Top-K (default 5) pass through                                ║
╠══════════════════════════════════════════════════════════════════╣
║  Stage 4 · Execution                              [cost: HIGH]   ║
║  4a. ExplorationAgent — EDA scripts in Docker sandbox (optional) ║
║  4b. Coder — deterministic template + Qlib subprocess, no LLM    ║
║  → BacktestReport (IS/OOS Sharpe, IC, ICIR, turnover)            ║
╠══════════════════════════════════════════════════════════════════╣
║  Stage 5 · Judgment & Synthesis                    [cost: low]   ║
║  Critic → RiskAuditor → PortfolioManager → ReportWriter          ║
║  → CIOReport (human approval via LangGraph interrupt())          ║
╚══════════════════════════════════════════════════════════════════╝
```

**6 Research Islands**: `momentum` · `northbound` · `valuation` · `volatility` · `volume` · `sentiment`

Each Island has its own `AlphaResearcher`, failure history, and softmax-sampled scheduling with temperature annealing.

---

## Key Design Decisions

**Coder is deterministic — zero LLM calls.**
Factor formulas are filled into a standard Qlib backtest template and executed via Docker subprocess. No LLM in the critical path of backtest execution.

**Error-driven RAG.**
When a factor fails, the failure reason is stored in ChromaDB. The next `AlphaResearcher` call retrieves similar past failures and uses them as negative examples. Failure accumulates into knowledge.

**Document-driven interfaces.**
Every agent communicates through typed Pydantic schemas (`FactorResearchNote`, `BacktestReport`, `CriticVerdict`, etc.). No dict passing between agents.

**Human stays in the loop — minimally.**
The system runs autonomously (Stage 1–4). Humans receive a `CIOReport` and choose: `approve`, `redirect:<island>`, or `stop`. Nothing else requires human attention.

---

## Quick Start

```bash
# 1. Set up environment
conda create -n pixiu python=3.11
conda activate pixiu
pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env
# Edit .env: set RESEARCHER_API_KEY, CODER_MODEL, etc.

# 3. Download A-share data (CSI 300)
python -m src.data_pipeline.data_downloader
python -m src.data_pipeline.format_to_qlib

# 4. Run baseline (establishes benchmark)
python -m src.core.run_baseline

# 5. Start single-island research (debug mode)
python -m src.core.orchestrator --mode single --island momentum

# 6. Start full evolution loop
python -m src.core.orchestrator --mode evolve --rounds 20

# 7. Check status / approve factors
pixiu status
pixiu factors --top 10
pixiu approve --factor-id <id>
```

---

## Benchmark

> Results pending. The table below will be updated with OOS (out-of-sample) numbers once the system has completed sufficient research rounds.

| Strategy | OOS Sharpe | OOS IC | Notes |
|---|---|---|---|
| CSI 300 Equal-Weight (B0) | — | — | Minimum baseline |
| Alpha158 + LightGBM (B1) | — | — | ML baseline, to be rerun OOS |
| Pixiu Best Factor | — | — | 🔄 in progress |
| Pixiu Portfolio | — | — | 🔄 in progress |

---

## Academic Foundation

Pixiu's architecture is grounded in recent literature on LLM-driven quantitative research:

| Paper | arXiv | Contribution to Pixiu |
|---|---|---|
| AlphaAgent | 2502.16789 | Three-dimensional pre-filter design (Stage 3) |
| RD-Agent (Microsoft) | 2505.15155 | Document-driven interface principle |
| QuantaAlpha | 2602.07085 | Exploration agent design (Stage 4a) |
| CogAlpha | 2511.18850 | Multi-agent quality hierarchy |
| QuantAgent (Huawei) | 2402.03755 | Dual-loop island evolution |

---

## Roadmap

| Phase | Status | Goal |
|---|---|---|
| **Skateboard** | ✅ Done | Data pipeline + Alpha158/LightGBM baseline (Sharpe 2.67 IS) |
| **Bicycle** | 🔄 In Progress | LangGraph funnel + Island evolution + FactorPool |
| **Car** | Planned | Terminal CLI + Web dashboard + CIO approval flow |
| **Expansion** | Future | Multi-market: HK, US equities, futures, crypto |

---

## Data Sources

| Layer | Source | Status |
|---|---|---|
| Price / Volume | BaoStock (free) | ✅ Live |
| Northbound flows, sector PE, research report metadata | AKShare (free) | ✅ Live |
| Macro indicators, margin trading, financial summaries | AKShare extensions | 🔄 Planned |
| Fundamentals: PE/PB/ROE, analyst estimates | Tushare Pro (free tier) | 🔄 Planned |
| News retrieval | Tavily (1000 req/mo free) | 🔄 Optional |

---

## License

Pixiu is released under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

- ✅ Free for personal use, academic research, and open-source projects
- ✅ You may modify and distribute under the same license
- ⚠️ If you deploy Pixiu as a network service (SaaS), you must open-source your modifications
- 💼 Commercial license available for proprietary deployment — contact us

---

## Contributing

Issues and PRs welcome. Please start with `docs/README.md`, then read `docs/specs/v2_architecture_overview.md` before contributing.

---

*Pixiu (貔貅) is a mythical creature in Chinese culture known for attracting wealth. Unlike its name, the system makes no guarantees of financial returns. Past backtest performance does not predict future results. This software is for research purposes only.*
