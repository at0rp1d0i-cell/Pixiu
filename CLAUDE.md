# CLAUDE.md

兼容入口，保留给仍会自动查找 `CLAUDE.md` 的工具。

当前仓库不再把这份文件当作架构真相来源。请改读：

1. `AGENTS.md`
2. `docs/README.md`
3. `docs/overview/README.md`
4. `docs/overview/architecture-overview.md`
5. `docs/overview/spec-execution-audit.md`

当前几个关键事实：

- 当前文档主体系是 `docs/overview/` + `docs/design/` + `docs/plans/`。
- `docs/archive/` 只保留历史材料，不再指导当前实现。
- Stage 5 的 canonical runtime 是 `src/agents/judgment.py`。
- `src/agents/critic.py`、`src/agents/factor_pool_writer.py`、`src/agents/cio_report_renderer.py` 是兼容层，不是当前主实现。
- 默认测试入口是 `pytest -q tests -m "smoke or unit"`。

如果你需要历史版 Stage 4→5 实施说明，请去 `docs/archive/reports/` 查阅归档报告，而不是使用这份文件。
