# Discovery Brief: controlled-run Stage 2 closure

## Problem Signal

After Stage 1 live closure, the mainline blocker has shifted downstream: controlled single still spends heavily in Stage 2 and passes too many low-value candidates into later stages. The next slice must close the controlled-run Stage 2 path rather than continue local fast-feedback tuning.

## Research Scope

Use current runtime evidence from docs/overview/05_spec-execution-audit.md, docs/overview/06_runtime-concessions.md, docs/plans/current_implementation_plan.md, recent controlled single artifacts, and Stage 2/Stage 5 diagnostics to define the bounded closure target.

## Open Questions

Which remaining wastes are dominant in controlled single: novelty, JSON robustness, alignment drift, or approved-to-low-sharpe value density? What is the smallest slice that changes mainline health rather than just fast-feedback cleanliness?

## Recommendation Target

Produce a bounded plan for controlled-run Stage 2 closure that can enter build under team-lead/ops flow.
