{
  "agent_type": "worker",
  "consumed_artifacts": [
    "docs/plans/dispatch-packets/2026-03-27-stage2-controlled-closure-builder.md",
    "docs/plans/sprint-contracts/2026-03-27-stage2-controlled-closure.md"
  ],
  "expected_writeback_command": "Return the implementation handoff by writing the implementation report to docs/plans/implementation-reports/2026-03-27-stage2-controlled-closure.md",
  "expected_writeback_target": "docs/plans/implementation-reports/2026-03-27-stage2-controlled-closure.md",
  "invocation_spec_path": "docs/plans/invocation-specs/2026-03-27-stage2-controlled-closure-builder.md",
  "launch_message": "You are the repo-defined role \"Implementation Worker\" (implementation-worker).\n\nUse runtime skill: .agents/skills/implementation-worker/SKILL.md\nUse role metadata: .agents/skills/implementation-worker/agents/openai.yaml\nConsume source packet: docs/plans/dispatch-packets/2026-03-27-stage2-controlled-closure-builder.md\nConsume invocation spec: docs/plans/invocation-specs/2026-03-27-stage2-controlled-closure-builder.md\nTreat Ops as the dispatch owner; do not redefine the task from chat history.\nWrite back exactly to: docs/plans/implementation-reports/2026-03-27-stage2-controlled-closure.md\nExpected writeback command: Return the implementation handoff by writing the implementation report to docs/plans/implementation-reports/2026-03-27-stage2-controlled-closure.md\nAfter writeback, return a concise completion note to Ops.",
  "logical_role": "implementation-worker",
  "metadata": ".agents/skills/implementation-worker/agents/openai.yaml",
  "model": "gpt-5.4",
  "packet_path": "docs/plans/dispatch-packets/2026-03-27-stage2-controlled-closure-builder.md",
  "reasoning_effort": "high",
  "role": "Implementation Worker",
  "runtime_skill": ".agents/skills/implementation-worker/SKILL.md"
}
