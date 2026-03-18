import pytest
from datetime import UTC, datetime, timedelta

pytestmark = pytest.mark.unit

from src.control_plane.state_store import StateStore
from src.schemas.control_plane import ArtifactRecord, HumanDecisionRecord, RunSnapshot


def test_create_update_and_get_latest_run(tmp_path):
    db_path = tmp_path / "state_store.sqlite"
    store = StateStore(db_path)

    run = store.create_run(mode="evolve")
    assert run.mode == "evolve"
    assert run.status == "running"
    assert run.current_stage == "pending"

    updated = store.update_run(
        run.run_id,
        status="completed",
        current_round=3,
        current_stage="report",
        finished_at=datetime.now(UTC),
        last_error=None,
    )
    assert updated.status == "completed"
    assert updated.current_round == 3
    assert updated.current_stage == "report"
    assert updated.finished_at is not None

    latest = store.get_latest_run()
    assert latest is not None
    assert latest.run_id == run.run_id
    assert latest.status == "completed"


def test_write_snapshot_and_get_snapshot(tmp_path):
    db_path = tmp_path / "state_store.sqlite"
    store = StateStore(db_path)
    run = store.create_run(mode="single")

    snapshot = RunSnapshot(
        run_id=run.run_id,
        approved_notes_count=2,
        backtest_reports_count=1,
        verdicts_count=1,
        awaiting_human_approval=True,
        updated_at=datetime.now(UTC),
    )
    store.write_snapshot(snapshot)

    got = store.get_snapshot(run.run_id)
    assert got is not None
    assert got.run_id == run.run_id
    assert got.approved_notes_count == 2
    assert got.awaiting_human_approval is True

    updated_snapshot = RunSnapshot(
        run_id=run.run_id,
        approved_notes_count=3,
        backtest_reports_count=2,
        verdicts_count=2,
        awaiting_human_approval=False,
        updated_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    store.write_snapshot(updated_snapshot)

    got2 = store.get_snapshot(run.run_id)
    assert got2 is not None
    assert got2.approved_notes_count == 3
    assert got2.backtest_reports_count == 2
    assert got2.awaiting_human_approval is False


def test_append_and_list_artifacts_and_reports_order(tmp_path):
    db_path = tmp_path / "state_store.sqlite"
    store = StateStore(db_path)
    run = store.create_run(mode="evolve")
    now = datetime.now(UTC)

    store.append_artifact(
        ArtifactRecord(
            run_id=run.run_id,
            kind="backtest_report",
            ref_id="bt-old",
            path="/tmp/bt-old.json",
            created_at=now - timedelta(minutes=3),
        )
    )
    store.append_artifact(
        ArtifactRecord(
            run_id=run.run_id,
            kind="cio_report",
            ref_id="cio-old",
            path="/tmp/cio-old.md",
            created_at=now - timedelta(minutes=2),
        )
    )
    store.append_artifact(
        ArtifactRecord(
            run_id=run.run_id,
            kind="cio_report",
            ref_id="cio-new",
            path="/tmp/cio-new.md",
            created_at=now - timedelta(minutes=1),
        )
    )

    all_artifacts = store.list_artifacts(run.run_id)
    assert [a.ref_id for a in all_artifacts] == ["cio-new", "cio-old", "bt-old"]

    cio_artifacts = store.list_artifacts(run.run_id, kind="cio_report")
    assert [a.ref_id for a in cio_artifacts] == ["cio-new", "cio-old"]
    assert all(a.kind == "cio_report" for a in cio_artifacts)

    reports = store.list_reports()
    assert [r.ref_id for r in reports] == ["cio-new", "cio-old"]
    assert all(r.kind == "cio_report" for r in reports)

    reports_limited = store.list_reports(limit=1)
    assert len(reports_limited) == 1
    assert reports_limited[0].ref_id == "cio-new"


def test_append_human_decision_no_crash(tmp_path):
    db_path = tmp_path / "state_store.sqlite"
    store = StateStore(db_path)
    run = store.create_run(mode="single")

    store.append_human_decision(
        HumanDecisionRecord(run_id=run.run_id, action="approve")
    )
    store.append_human_decision(
        HumanDecisionRecord(run_id=run.run_id, action="redirect:momentum")
    )
    store.append_human_decision(
        HumanDecisionRecord(run_id=run.run_id, action="stop")
    )

    # This test validates write-path coverage for the decisions table.
    assert store.get_latest_run() is not None
