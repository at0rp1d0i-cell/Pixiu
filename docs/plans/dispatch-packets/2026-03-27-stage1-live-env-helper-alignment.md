# Task Brief: Stage1 live env helper alignment

## Objective

Align live/e2e env guard with current LiteLLM/runtime-settings truth so Stage 1 live tests do not skip solely because RESEARCHER_API_KEY is absent while runtime credentials are otherwise available.

## Scope

Review and patch only tests/helpers/live_env.py and directly affected live-test support/tests if required; keep Stage 1 business runtime unchanged; verify targeted live-env helper behavior and Stage 1 unit/integration coverage.

## Constraints

Allowed write set: tests/helpers/live_env.py, tests/conftest.py, tests/integration/test_stage1_live.py, tests/test_stage1.py, docs/plans/implementation-reports/2026-03-27-stage1-live-env-helper-alignment.md. Do not modify src runtime code unless absolutely required. Preserve current Stage 1 blocking prefetch design. Verification must include targeted pytest commands and a note explaining how the helper now matches runtime env truth.

## Relevant Decisions

Stage 1 runtime already supports provider/env resolution beyond RESEARCHER_API_KEY. The follow-up must fix the test/env guard rather than broadening business logic. Treat this as a review-blocking alignment fix inside stage1-live-closure.

## Expected Output

Worker returns What changed, Why, Verification, Open items, and writes a bounded implementation report at docs/plans/implementation-reports/2026-03-27-stage1-live-env-helper-alignment.md.

## Writeback Target

docs/plans/dispatch-packets/2026-03-27-stage1-live-env-helper-alignment.md
