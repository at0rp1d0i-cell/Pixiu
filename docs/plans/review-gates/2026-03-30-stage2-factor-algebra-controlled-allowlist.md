# Review Gate: Stage 2 factor_algebra controlled allowlist

## Inputs

- Implementation diff in [researcher.py](/home/torpedo/Workspace/ML/Pixiu/src/agents/researcher.py), [test_stage2.py](/home/torpedo/Workspace/ML/Pixiu/tests/test_stage2.py), and [06_runtime-concessions.md](/home/torpedo/Workspace/ML/Pixiu/docs/overview/06_runtime-concessions.md)
- Sprint contract [2026-03-30-stage2-factor-algebra-controlled-allowlist.md](/home/torpedo/Workspace/ML/Pixiu/docs/plans/sprint-contracts/2026-03-30-stage2-factor-algebra-controlled-allowlist.md)
- Implementation report [2026-03-30-stage2-factor-algebra-controlled-allowlist.md](/home/torpedo/Workspace/ML/Pixiu/docs/plans/implementation-reports/2026-03-30-stage2-factor-algebra-controlled-allowlist.md)
- Controlled-run artifact [round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260330_140354/round_000.json)

## Review Passes

- Lead review of the bounded controlled-run factor-algebra allowlist slice

## Findings

- No blocking correctness defect found in the bounded write set.
- Moving the profile policy gate ahead of alignment is the correct order for this slice because disallowed families should fail as profile policy, not masquerade as alignment errors.
- Test coverage is adequate for the bounded semantics change: ratio-momentum rejection, volume-confirmation rejection, prompt injection, stop-loss regression, and fast-feedback compatibility are all exercised.

## Residual Risks

- This remains an `experiment_concession`, not the final Stage 2 generation architecture.
- The family-level blocker is isolated, but the next blocker is now `mean_spread` wording/alignment.
- `approved_notes_count` remains `0`, so self-evolve smoke is still not unlocked.

## Auto Decisions

- Accept this slice as a valid narrowing of the controlled single-note factor-algebra surface.
- Keep the next mainline target on factor-algebra wording/alignment recovery instead of adding more family blacklists.

## Taste Decisions

- none

## Recommendation

pass

## Approval Target

Commit this bounded allowlist slice without mixing unrelated local team/runtime files.
