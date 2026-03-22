## Why

- 这次变更解决什么问题？
- 为什么现在做？

## Architecture Impact

- 影响哪些 Stage / contract / control-plane / product boundary？
- 这是让代码追上 spec，还是 spec 追上代码，还是消除漂移？

## Source of Truth

- Current truth:
  - 
- Updated docs/spec:
  - 
- Drift intentionally left:
  - 

## Changes

- 

## Verification

Run:

```bash
uv run pytest -q tests -m "smoke or unit"
```

Additional:

```bash
# add targeted commands here
```

Results:

- 

## Risk

- 行为回归面：
- 兼容性风险：
- 运行时风险：

## Experiment State

- [ ] 不需要 reset 实验状态
- [ ] 需要 reset `data/control_plane_state.db`
- [ ] 需要清理 `data/experiment_runs/`
- [ ] 需要清理 `data/artifacts/`
- [ ] 不要清 `data/factor_pool_db/`

Reason:

- 

## Docs / Spec Checklist

- [ ] 需要更新 `docs/overview/05_spec-execution-audit.md`
- [ ] 需要更新相关 `docs/design/*.md`
- [ ] 需要更新 `docs/plans/*.md`
- [ ] 不需要更新文档（理由已写明）

## Worker Output

- What changed:
- Why:
- Verification:
- Open items:

