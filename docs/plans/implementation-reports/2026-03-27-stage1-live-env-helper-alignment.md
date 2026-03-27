# 2026-03-27 Stage1 Live Env Helper Alignment

## What changed

- Updated [tests/helpers/live_env.py](/home/torpedo/Workspace/ML/Pixiu/tests/helpers/live_env.py) so live/e2e gating uses `get_researcher_llm_kwargs(profile="researcher")` to determine whether researcher-facing LLM credentials are resolvable under current LiteLLM/runtime-settings truth.
- Kept the helper surface stable, but changed the skip reason from a hard-coded `RESEARCHER_API_KEY` requirement to a runtime-truth message: `researcher LLM 凭据未就绪`.
- Added targeted unit coverage in [tests/test_stage1.py](/home/torpedo/Workspace/ML/Pixiu/tests/test_stage1.py):
  - `test_researcher_live_env_ready_accepts_openai_api_key_fallback`
  - `test_ensure_researcher_live_env_or_skip_uses_runtime_truth_message`

## Why

- Stage 1 runtime no longer depends on `RESEARCHER_API_KEY` alone. It can resolve credentials through current LiteLLM/runtime-settings behavior, including `OPENAI_API_KEY`.
- The previous live/e2e guard was stricter than the actual runtime and caused `tests/integration/test_stage1_live.py` to skip even when Stage 1 could really run.
- This follow-up aligns test gating with current runtime truth instead of broadening business logic.

## Verification

- `uv run pytest -q tests/test_stage1.py -k "researcher_live_env or resolve_run_env_truth_uses_repo_env_by_default"`
  - `3 passed, 58 deselected`
- `uv run pytest -q tests/integration/test_stage1_live.py -m live -v -s`
  - `4 passed`
  - live tool payloads were returned for `get_moneyflow_hsgt` and `get_margin_data`
  - `test_stage1_live_blocking_path_returns_non_degraded_context` executed instead of skipping

## Open items

- The live suite still logs a non-blocking Tushare `get_news` quota error after the Stage 1 run. This is enrichment-only and did not fail the blocking-core live checks.
