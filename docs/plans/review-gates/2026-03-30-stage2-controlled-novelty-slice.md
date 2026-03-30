# Review Gate: Stage 2 controlled novelty slice

## Inputs

- Implementation diff in [src/agents/researcher.py](/home/torpedo/Workspace/ML/Pixiu/src/agents/researcher.py) and [tests/test_stage2.py](/home/torpedo/Workspace/ML/Pixiu/tests/test_stage2.py)
- Sprint contract [2026-03-29-stage2-controlled-novelty-slice.md](/home/torpedo/Workspace/ML/Pixiu/docs/plans/sprint-contracts/2026-03-29-stage2-controlled-novelty-slice.md)
- Implementation report [2026-03-29-stage2-controlled-novelty-slice.md](/home/torpedo/Workspace/ML/Pixiu/docs/plans/implementation-reports/2026-03-29-stage2-controlled-novelty-slice.md)
- Targeted pytest proof and controlled-run artifact [round_000.json](/home/torpedo/Workspace/ML/Pixiu/data/experiment_runs/20260330_114204/round_000.json)

## Review Passes

- Lead review of the bounded symbolic-mutation novelty prefilter slice

## Findings

- No blocking correctness defect found in the bounded write set.
- The prefilter stays inside Stage 2 local generation, reuses the current novelty threshold semantics, and does not alter schema or downstream stage contracts.
- Test coverage is aligned with the change: existing-pool duplicate suppression and same-batch duplicate suppression are both exercised.

## Residual Risks

- The helper in [researcher.py](/home/torpedo/Workspace/ML/Pixiu/src/agents/researcher.py) reuses `NoveltyFilter` private token/Jaccard helpers. This is acceptable for the current bounded slice, but a later novelty refactor should expose a shared public helper if Stage 2 prefiltering expands.
- Repeated controlled-run proofs keep the main novelty reduction (`symbolic_mutation novelty 9 -> 3`), but `validator/local_retry` still fluctuate and `approved_notes_count` remains `0`.
- This slice reduces symbolic duplicate waste but does not close the remaining Stage 2 bottlenecks in `factor_algebra`, `narrative_mining`, and `cross_market`.

## Auto Decisions

- Accept this slice as a valid bounded reduction of controlled-run novelty waste.
- Keep the next mainline target on residual `factor_algebra`, `narrative_mining`, and validator waste instead of reopening Stage 1 or downstream threshold logic.

## Taste Decisions

- none

## Recommendation

pass

## Approval Target

Commit this bounded novelty slice on `feature/stage2-controlled-closure` without mixing unrelated team-runtime or status-file changes.
