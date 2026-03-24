# LLM Runtime Settings Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an explicit runtime LLM settings layer that separates provider credentials from provider/model selection, without breaking the current legacy env-based runtime.

**Architecture:** Introduce `config/llm_runtime.json` plus a thin `src/llm/runtime_settings.py` resolver. Provider credentials/endpoints come from env (`DEEPSEEK_*`, `OPENAI_*`), while runtime selection uses `default_provider`, provider default models, and role overrides. `openai_compat.py` should consult this resolver when a role/profile is provided, then fall back to the current `RESEARCHER_* -> OPENAI_*` legacy environment logic if settings are absent or invalid.

**Tech Stack:** Python, `uv`, JSON config, pytest, LangChain `ChatOpenAI`

---

### Task 1: Add runtime settings config and loader tests

**Files:**
- Create: `config/llm_runtime.json`
- Create: `src/llm/runtime_settings.py`
- Test: `tests/test_llm_runtime_settings.py`

**Step 1: Write the failing tests**

- Test loading `config/llm_runtime.json`
- Test resolving `default_provider`
- Test resolving `researcher -> openai` style role override
- Test invalid/missing role returns fallback-safe result
- Test provider credentials read from `DEEPSEEK_*` / `OPENAI_*`

**Step 2: Run tests to verify failure**

Run: `uv run pytest -q tests/test_llm_runtime_settings.py`

**Step 3: Write minimal implementation**

- Add JSON loader
- Add a small resolver that returns selected `provider`, `model`, and env-derived connection values
- Keep parsing small and defensive

**Step 4: Run tests to verify pass**

Run: `uv run pytest -q tests/test_llm_runtime_settings.py`

**Step 5: Commit**

```bash
git add config/llm_runtime.json src/llm/runtime_settings.py tests/test_llm_runtime_settings.py
git commit -m "feat(llm): add runtime provider settings"
```

### Task 2: Wire runtime selection into openai_compat

**Files:**
- Modify: `src/llm/openai_compat.py`
- Modify: `src/llm/__init__.py`
- Test: `tests/test_llm_config.py`

**Step 1: Write the failing tests**

- `profile='researcher'` uses configured role mapping when config exists
- `PIXIU_LLM_DEFAULT_PROVIDER` can override global default provider
- explicit overrides still win
- missing config still falls back to legacy env behavior

**Step 2: Run targeted tests to verify failure**

Run: `uv run pytest -q tests/test_llm_config.py`

**Step 3: Write minimal implementation**

- Resolve provider/model/endpoint info from runtime settings when `profile` is set
- Preserve current fallback logic for compatibility
- Do not change usage ledger metadata behavior

**Step 4: Run tests to verify pass**

Run: `uv run pytest -q tests/test_llm_config.py tests/test_llm_runtime_settings.py`

**Step 5: Commit**

```bash
git add src/llm/openai_compat.py src/llm/__init__.py tests/test_llm_config.py
git commit -m "feat(llm): resolve providers by role"
```

### Task 3: Document operator-facing env usage

**Files:**
- Modify: `.env.example`

**Step 1: Update the example env**

- Add `DEEPSEEK_*` and `OPENAI_*` provider credential blocks
- Add note that runtime selection now lives in `config/llm_runtime.json`
- Add optional `PIXIU_LLM_DEFAULT_PROVIDER`
- Keep current `RESEARCHER_*` block documented as legacy compatibility only

**Step 2: Verify formatting**

Run: `git diff --check`

**Step 3: Commit**

```bash
git add .env.example
git commit -m "docs(env): document llm runtime settings"
```

### Task 4: Run verification and live smoke

**Files:**
- No new files required

**Step 1: Run targeted unit tests**

Run: `uv run pytest -q tests/test_llm_runtime_settings.py tests/test_llm_config.py`

**Step 2: Run runtime config smoke**

Run:

```bash
uv run python -c "from src.llm.openai_compat import get_researcher_llm_kwargs; print(get_researcher_llm_kwargs(profile='researcher'))"
```

Expected:
- explicit `provider/model/base_url/api_key` resolution
- no regression in metadata or callback injection

**Step 3: Run one minimal live smoke if credentials exist**

Run a single `build_researcher_llm(profile='researcher')` call with the selected provider and record whether it succeeds or fails.

**Step 4: Commit final integration if needed**

```bash
git add .
git commit -m "test(llm): verify runtime settings integration"
```
