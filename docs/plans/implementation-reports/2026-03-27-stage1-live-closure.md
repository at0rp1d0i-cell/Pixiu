# Implementation Report: Stage 1 Live Closure

## Consumed Sprint Contract

docs/plans/sprint-contracts/2026-03-27-stage1-live-closure.md

## Generator Summary

Closed the current Stage 1 live blocker by aligning `pixiu run` env truth with `doctor/preflight`, replacing LLM-mediated blocking-tool discovery with deterministic Tushare blocking-core prefetch, and updating Stage 1 live tests to the current runtime path.

## Files Touched

- `src/core/orchestrator/_entrypoints.py`
- `src/agents/market_analyst.py`
- `tests/test_stage1.py`
- `tests/integration/test_stage1_live.py`
- `docs/overview/05_spec-execution-audit.md`
- `docs/overview/06_runtime-concessions.md`
- `docs/plans/current_implementation_plan.md`

## Tests Run

- `uv run pytest -q tests/test_stage1.py -m unit`
- `uv run python scripts/doctor.py --mode core`
- `uv run python scripts/experiment_preflight.py --profile config/experiments/default.json --json`
- `uv run python - <<'PY' ... subprocess.run(['uv', 'run', 'pytest', '-q', 'tests/integration/test_stage1_live.py', '-m', 'live', '-v', '-s'], env=env)`
- `timeout 120 uv run pixiu run --mode single --island momentum`

## Follow-Ups

- Align the generic live/e2e env helper with current runtime truth so live tests no longer require manual `RESEARCHER_API_KEY` backfill.

## What changed

- `src/core/orchestrator/_entrypoints.py`
  - `pixiu run` now resolves repo `.env` explicitly by default instead of relying on caller-side dotenv behavior.
- `src/agents/market_analyst.py`
  - Replaced the fragile blocking-core LLM tool-selection path with deterministic prefetch of `get_moneyflow_hsgt` and `get_margin_data`.
  - Stage 1 now injects prefetched blocking payloads into the summary prompt and only exposes enrichment tools to the LLM.
  - Reliability diagnostics now mark prefetched blocking tools as used.
- `tests/test_stage1.py`
  - Added coverage for prefetched blocking payload injection, repo-env default resolution, and enrichment-only tool binding after blocking-core prefetch.
  - Updated Stage 1 runtime tests to reflect direct blocking-tool prefetch.
- `tests/integration/test_stage1_live.py`
  - Live Stage 1 tests now resolve Tushare env truth with the same layered env helper as doctor/preflight.
  - Added a live Stage 1 end-to-end assertion that the current Tushare blocking-core path returns a non-degraded market context.
- `docs/overview/05_spec-execution-audit.md`
  - Recorded Stage 1 live closure and moved the mainline bottleneck emphasis downstream to Stage 2/value-density and validation.
- `docs/overview/06_runtime-concessions.md`
  - Updated the Stage 1 concession entry to match the new `blocking core prefetch + async enrichment` runtime.
- `docs/plans/current_implementation_plan.md`
  - Marked Phase 2 Stage 1 live-closure items complete.

## Why

- `pixiu run`, `doctor`, and `preflight` needed the same repo-env fallback semantics for the known current Tushare path.
- Direct Tushare tool discovery and payload fetches were fast in runtime evidence; the Stage 1 degradation came from the LLM-mediated blocking-tool loop, not from MCP discovery itself.
- Deterministic prefetch closes the current blocking-core path without widening scope into Stage 2/3/4/5 or profile redesign.

Source checked: current repo runtime behavior, `scripts/doctor.py`, `scripts/experiment_preflight.py`, Stage 1 unit/live tests, and live Tushare tool discovery/runtime output.

## Verification

- `uv run pytest -q tests/test_stage1.py -m unit`
  - Result: `59 passed`
- `uv run python scripts/doctor.py --mode core`
  - Result: pass; blocking data/tool checks passed with `TUSHARE_TOKEN` and `QLIB_DATA_DIR` resolved from `repo_env`
- `uv run python scripts/experiment_preflight.py --profile config/experiments/default.json --json`
  - Result: `{"ok": true, ... "tushare_token_source": "repo_env", "qlib_data_dir_source": "repo_env"}`
- `uv run python - <<'PY' ... subprocess.run(['uv', 'run', 'pytest', '-q', 'tests/integration/test_stage1_live.py', '-m', 'live', '-v', '-s'], env=env)` with `RESEARCHER_API_KEY` backfilled from `OPENAI_API_KEY` for the existing live-test harness guard
  - Result: `4 passed`
- `timeout 120 uv run pixiu run --mode single --island momentum`
  - Result: command timed out later in Stage 2 by design, but Stage 1 completed successfully first:
    - `市场上下文生成成功`
    - `Stage 1 市场上下文完成 ... 耗时 37500.54 ms`
    - run advanced into `Stage 2`

## Open items

- The repo live-test harness still hard-gates on `RESEARCHER_API_KEY`; that helper is outside the allowed write set, so I did not change it here. For this verification pass I satisfied the existing guard by backfilling `RESEARCHER_API_KEY` from the current `OPENAI_API_KEY` in the command environment.
- Stage 1 live closure is complete for the current known Tushare blocking-core path, but the next mainline blocker remains controlled-run Stage 2 value density / novelty waste.
