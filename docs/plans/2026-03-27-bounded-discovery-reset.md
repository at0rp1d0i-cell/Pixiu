# Discovery Brief: bounded discovery reset

## Problem Signal

Canonical state and runtime truth have drifted from the current mainline. Team runtime is only partially repo-managed, and branch-based work cannot start safely without a bounded discovery reset.

## Research Scope

1) state drift across docs/project, docs/status, and current implementation plan; 2) runtime truth for controlled/default/fast_feedback; 3) installability and reproducibility of team runtime assets under .agents/skills and .codex; 4) branch graph for the next work phase.

## Open Questions

Which blockers are still active on the mainline? Which assets are repo-managed vs local-only? What branch tasks can run in parallel without overlapping write sets?

## Recommendation Target

Produce a bounded discovery summary and a branch-ready task graph for planning.
