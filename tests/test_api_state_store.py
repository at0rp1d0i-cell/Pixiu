from datetime import UTC, datetime

from src.api import server
from src.control_plane.state_store import StateStore
from src.schemas.control_plane import ArtifactRecord, RunSnapshot


def test_api_status_reads_latest_run_and_snapshot(tmp_path, monkeypatch):
    store = StateStore(tmp_path / "state_store.sqlite")
    run = store.create_run(mode="single")
    store.update_run(
        run.run_id,
        status="awaiting_human_approval",
        current_round=2,
        current_stage="report",
    )
    store.write_snapshot(
        RunSnapshot(
            run_id=run.run_id,
            approved_notes_count=2,
            backtest_reports_count=1,
            verdicts_count=1,
            awaiting_human_approval=True,
            updated_at=datetime.now(UTC),
        )
    )

    monkeypatch.setattr(server, "_get_state_store", lambda: store)

    payload = server.get_status()

    assert payload["status"] == "awaiting_human_approval"
    assert payload["run_id"] == run.run_id
    assert payload["current_stage"] == "report"
    assert payload["backtest_reports_count"] == 1
    assert payload["awaiting_human_approval"] is True


def test_api_reports_reads_control_plane_artifacts(tmp_path, monkeypatch):
    store = StateStore(tmp_path / "state_store.sqlite")
    run = store.create_run(mode="evolve")
    report_path = tmp_path / "reports" / "latest.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("# CIO Report", encoding="utf-8")

    store.append_artifact(
        ArtifactRecord(
            run_id=run.run_id,
            kind="cio_report",
            ref_id="report-001",
            path=str(report_path),
        )
    )

    monkeypatch.setattr(server, "_get_state_store", lambda: store)

    payload = server.get_reports()

    assert len(payload) == 1
    assert payload[0]["id"] == "report-001"
    assert payload[0]["run_id"] == run.run_id
    assert payload[0]["path"] == str(report_path)
