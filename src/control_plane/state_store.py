import os
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from src.schemas.control_plane import (
    ArtifactRecord,
    HumanDecisionRecord,
    RunRecord,
    RunSnapshot,
)


_DEFAULT_DB_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "control_plane_state.db"
)


def _iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    return ts.isoformat()


def _dt(ts: str | None) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromisoformat(ts)


class StateStore:
    """Minimal SQLite-backed control-plane repository."""

    def __init__(self, db_path: str | Path = _DEFAULT_DB_PATH):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_tables(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_records (
                    run_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_round INTEGER NOT NULL,
                    current_stage TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    version TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_snapshots (
                    run_id TEXT PRIMARY KEY,
                    approved_notes_count INTEGER NOT NULL,
                    backtest_reports_count INTEGER NOT NULL,
                    verdicts_count INTEGER NOT NULL,
                    awaiting_human_approval INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    version TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS artifact_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    ref_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    version TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS human_decision_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    version TEXT NOT NULL
                )
                """
            )

    def create_run(self, mode: str) -> RunRecord:
        record = RunRecord(
            run_id=uuid.uuid4().hex,
            mode=mode,
            status="running",
            current_round=0,
            current_stage="pending",
            started_at=datetime.now(UTC),
        )
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO run_records (
                    run_id, mode, status, current_round, current_stage,
                    started_at, finished_at, last_error, created_at, version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.mode,
                    record.status,
                    record.current_round,
                    record.current_stage,
                    _iso(record.started_at),
                    _iso(record.finished_at),
                    record.last_error,
                    _iso(record.created_at),
                    record.version,
                ),
            )
        return record

    def update_run(self, run_id: str, **fields) -> RunRecord:
        if not fields:
            existing = self._get_run(run_id)
            if existing is None:
                raise KeyError(f"run not found: {run_id}")
            return existing

        allowed = {
            "mode",
            "status",
            "current_round",
            "current_stage",
            "started_at",
            "finished_at",
            "last_error",
        }
        invalid = set(fields) - allowed
        if invalid:
            raise ValueError(f"unsupported update fields: {sorted(invalid)}")

        normalized = dict(fields)
        for key in ("started_at", "finished_at"):
            if key in normalized and isinstance(normalized[key], datetime):
                normalized[key] = _iso(normalized[key])

        set_clause = ", ".join(f"{key} = ?" for key in normalized)
        values = [normalized[key] for key in normalized]
        values.append(run_id)

        with self._conn() as conn:
            cur = conn.execute(
                f"UPDATE run_records SET {set_clause} WHERE run_id = ?",
                values,
            )
            if cur.rowcount == 0:
                raise KeyError(f"run not found: {run_id}")
        updated = self._get_run(run_id)
        if updated is None:
            raise KeyError(f"run not found after update: {run_id}")
        return updated

    def write_snapshot(self, snapshot: RunSnapshot) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO run_snapshots (
                    run_id, approved_notes_count, backtest_reports_count,
                    verdicts_count, awaiting_human_approval, updated_at,
                    created_at, version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    approved_notes_count = excluded.approved_notes_count,
                    backtest_reports_count = excluded.backtest_reports_count,
                    verdicts_count = excluded.verdicts_count,
                    awaiting_human_approval = excluded.awaiting_human_approval,
                    updated_at = excluded.updated_at,
                    version = excluded.version
                """,
                (
                    snapshot.run_id,
                    snapshot.approved_notes_count,
                    snapshot.backtest_reports_count,
                    snapshot.verdicts_count,
                    int(snapshot.awaiting_human_approval),
                    _iso(snapshot.updated_at),
                    _iso(snapshot.created_at),
                    snapshot.version,
                ),
            )

    def append_artifact(self, record: ArtifactRecord) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO artifact_records (
                    run_id, kind, ref_id, path, created_at, version
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.kind,
                    record.ref_id,
                    record.path,
                    _iso(record.created_at),
                    record.version,
                ),
            )

    def append_human_decision(self, record: HumanDecisionRecord) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO human_decision_records (
                    run_id, action, created_at, version
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.action,
                    _iso(record.created_at),
                    record.version,
                ),
            )

    def get_latest_run(self) -> Optional[RunRecord]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM run_records
                ORDER BY started_at DESC, created_at DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return self._row_to_run(row)

    def get_snapshot(self, run_id: str) -> Optional[RunSnapshot]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM run_snapshots WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_snapshot(row)

    def list_artifacts(self, run_id: str, kind: Optional[str] = None) -> list[ArtifactRecord]:
        query = """
            SELECT run_id, kind, ref_id, path, created_at, version
            FROM artifact_records
            WHERE run_id = ?
        """
        params: list[object] = [run_id]
        if kind is not None:
            query += " AND kind = ?"
            params.append(kind)
        query += " ORDER BY created_at DESC, id DESC"

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_artifact(row) for row in rows]

    def list_reports(self, limit: int = 20) -> list[ArtifactRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT run_id, kind, ref_id, path, created_at, version
                FROM artifact_records
                WHERE kind = 'cio_report'
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_artifact(row) for row in rows]

    def _get_run(self, run_id: str) -> Optional[RunRecord]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM run_records WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_run(row)

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            run_id=row["run_id"],
            mode=row["mode"],
            status=row["status"],
            current_round=row["current_round"],
            current_stage=row["current_stage"],
            started_at=_dt(row["started_at"]),
            finished_at=_dt(row["finished_at"]),
            last_error=row["last_error"],
            created_at=_dt(row["created_at"]),
            version=row["version"],
        )

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row) -> RunSnapshot:
        return RunSnapshot(
            run_id=row["run_id"],
            approved_notes_count=row["approved_notes_count"],
            backtest_reports_count=row["backtest_reports_count"],
            verdicts_count=row["verdicts_count"],
            awaiting_human_approval=bool(row["awaiting_human_approval"]),
            updated_at=_dt(row["updated_at"]),
            created_at=_dt(row["created_at"]),
            version=row["version"],
        )

    @staticmethod
    def _row_to_artifact(row: sqlite3.Row) -> ArtifactRecord:
        return ArtifactRecord(
            run_id=row["run_id"],
            kind=row["kind"],
            ref_id=row["ref_id"],
            path=row["path"],
            created_at=_dt(row["created_at"]),
            version=row["version"],
        )


_state_store: StateStore | None = None


def get_state_store(db_path: str | Path | None = None) -> StateStore:
    """Return the process-wide control-plane store singleton."""
    global _state_store

    if db_path is not None:
        _state_store = StateStore(db_path)
        return _state_store

    if _state_store is None:
        configured_path = os.getenv("PIXIU_STATE_STORE_PATH")
        _state_store = StateStore(configured_path or _DEFAULT_DB_PATH)

    return _state_store
