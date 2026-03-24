# Worktree-Safe Environment Truth Design

Status: active
Owner: coordinator
Purpose: Define a single machine-scoped environment source that every Pixiu worktree can share, while preserving explicit shell overrides.

## Problem

Pixiu currently mixes three incompatible assumptions:

- some code reads repo-local `.env`
- some code relies on shell-exported environment variables
- some code falls back to repo-relative paths

This breaks down in `git worktree` workflows because untracked repo-local `.env` files are not shared, while repo-relative defaults often point at the wrong worktree path.

## Decision

Pixiu will introduce a machine-scoped runtime env file:

- default path: `~/.config/pixiu/runtime.env`
- purpose: shared truth for machine-level runtime values across all worktrees

Repository `.env` remains supported, but only as a repo-local override / developer convenience layer. It is no longer the primary source of truth for machine-scoped values.

## Precedence

The resolved load order is:

1. explicit process environment
2. user runtime env (`~/.config/pixiu/runtime.env`)
3. repo-local `.env`
4. code fallback/default

This order must be identical in:

- `scripts/doctor.py`
- `scripts/experiment_preflight.py`
- `scripts/run_experiment_harness.py`
- shared runtime helpers used by live code paths

## Scope

This first slice only covers environment truth and source tracing for high-value runtime keys:

- `TUSHARE_TOKEN`
- `QLIB_DATA_DIR`
- selected researcher/runtime keys that already depend on dotenv loading

It does not introduce:

- a product settings system
- an app-facing config UI
- secret encryption
- profile editing UX

## Required Behavior

### Shared loader

Add a shared env loader in `src/core/env.py` that can:

- read the user runtime env file if present
- read the repo-local `.env` if present
- merge them with explicit environment variables winning
- optionally apply the merged values back into a target env / process env
- expose source metadata for selected keys

### Source tracing

`doctor` and `preflight` must be able to report where important values came from, such as:

- `process_env`
- `user_runtime_env`
- `repo_env`
- `default`
- `profile`

The first version only needs to surface source tracing where it materially improves debugging:

- blocking `doctor` setup
- `preflight` summary / JSON output

### Worktree safety

Repo-relative fallback paths remain allowed, but only after the shared env layers are resolved. A worktree must not silently ignore an already valid shared machine-level `QLIB_DATA_DIR`.

## Recommended Approach

Use one shared helper module in `src/core/env.py` and migrate the current script entrypoints to it.

Why this approach:

- one precedence rule instead of script-specific variants
- minimal runtime surface area
- no new config format
- preserves backwards compatibility with existing `.env` usage

## Acceptance

- two worktrees on the same machine resolve the same `TUSHARE_TOKEN` and `QLIB_DATA_DIR` without duplicating `.env`
- explicit shell exports still override shared/runtime files
- `doctor` and `preflight` show the source of critical values
- the implementation does not widen into a general settings system
