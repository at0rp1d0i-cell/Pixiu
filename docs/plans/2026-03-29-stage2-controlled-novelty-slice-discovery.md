# Discovery Brief: controlled-run Stage 2 novelty slice

## Problem Signal

Fresh controlled/default artifact data/experiment_runs/20260329_224455/round_000.json shows Stage 2 stop-loss is working (local_retry_count=0), but novelty remains the dominant waste: novelty=16 vs alignment=2, with symbolic_mutation and narrative/cross_market still burning most of the budget.

## Research Scope

Use round_000 artifact 20260329_224455, current researcher/prefilter novelty logic, and Stage 2 tests to define the smallest slice that reduces controlled-run novelty waste without touching Stage 1 or Stage 4/5 thresholds.

## Open Questions

Which subspace should be hit first for the biggest payoff: symbolic_mutation duplicate churn, factor_algebra ratio_momentum recurrence, or narrative/cross_market near-duplicates? What is the smallest bounded fix that changes controlled-run artifact mix rather than only unit tests?

## Recommendation Target

Produce a bounded plan for a novelty-focused Stage 2 controlled-run slice suitable for build kickoff.
