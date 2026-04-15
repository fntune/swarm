"""Schema setup, legacy detection, and SqliteCoordinationBackend round-trips."""

import asyncio
import sqlite3
from pathlib import Path

import pytest

from swarm.batch.sqlite import (
    SqliteCoordinationBackend,
    get_db_path,
    init_db,
    insert_attempt,
    insert_node,
    insert_workspace,
    latest_attempt,
    pending_nodes,
    update_attempt_status,
)
from swarm.core.errors import SwarmError


def _seed(db, run_id):
    insert_workspace(
        db,
        workspace_id="ws-1",
        run_id=run_id,
        kind="cwd",
        path=".",
        branch=None,
        base_branch=None,
    )
    insert_node(
        db,
        run_id=run_id,
        name="alpha",
        plan_name="t",
        runtime="mock",
        profile="implementer",
        model="sonnet",
        prompt="hello",
        check_command="true",
        depends_on=[],
        max_iterations=5,
        max_cost_usd=1.0,
        on_failure="continue",
        retry_count=3,
        parent=None,
        tree_path="root.alpha",
    )
    return insert_attempt(
        db,
        run_id=run_id,
        node_name="alpha",
        attempt_number=1,
        workspace_id="ws-1",
    )


def test_schema_user_version(cwd_tmp):
    db = init_db("r1", cwd_tmp)
    try:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        # All five tables exist
        names = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {"nodes", "attempts", "workspaces", "events", "coord_responses"} <= names
    finally:
        db.close()


def test_legacy_db_detection(cwd_tmp):
    legacy_path = get_db_path("legacy", cwd_tmp)
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(legacy_path))
    conn.execute("CREATE TABLE agents (x INT)")
    conn.commit()
    conn.close()
    with pytest.raises(SwarmError, match="Legacy run database"):
        init_db("legacy", cwd_tmp)


def test_node_attempt_round_trip(cwd_tmp):
    db = init_db("r2", cwd_tmp)
    try:
        attempt_id = _seed(db, "r2")
        ready = pending_nodes(db, "r2")
        assert len(ready) == 1
        update_attempt_status(db, attempt_id, "completed")
        attempt = latest_attempt(db, "r2", "alpha")
        assert attempt["status"] == "completed"
    finally:
        db.close()


def test_coord_backend_report_progress(cwd_tmp):
    db = init_db("r3", cwd_tmp)
    try:
        _seed(db, "r3")
    finally:
        db.close()
    backend = SqliteCoordinationBackend(base_path=cwd_tmp)
    result = asyncio.run(
        backend.report_progress("r3", "alpha", "halfway", "milestone-1")
    )
    assert result.success
    # Verify the event was inserted
    with sqlite3.connect(str(get_db_path("r3", cwd_tmp))) as conn:
        rows = conn.execute(
            "SELECT event_type FROM events WHERE run_id = ?", ("r3",)
        ).fetchall()
    assert any(r[0] == "progress" for r in rows)
