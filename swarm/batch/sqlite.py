"""SQLite persistence, event sink, and coordination backend for batch mode.

One file on purpose: path helpers, schema, low-level row helpers, SqliteSink
(the EventSink used by batch), and SqliteCoordinationBackend (the
CoordinationBackend used by batch) all belong together because they touch
the same five tables.

Schema (PRAGMA user_version = 1):
- nodes           one row per plan-declared agent, immutable config
- attempts        one row per execution attempt, mutable runtime state
- workspaces      one row per allocated workspace (worktree/cwd/tempdir)
- events          append-only event log for the EventSink
- coord_responses manager replies to clarification/blocker events

Legacy databases (old `agents` table, user_version = 0) are rejected with a
clear SwarmError — pre-production, fresh schemas only.
"""

import asyncio
import json
import logging
import sqlite3
import subprocess
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Generator, Iterable
from uuid import uuid4

from swarm.core.agent import AgentRequest
from swarm.core.coordination import (
    CoordinationBackend,
    CoordOp,
    CoordResult,
)
from swarm.core.errors import SwarmError
from swarm.core.events import (
    AgentCompleted,
    AgentStarted,
    CoordCall,
    CostUpdate,
    EventSink,
    IterationTick,
    LogText,
    SwarmEvent,
)

logger = logging.getLogger("swarm.batch.sqlite")

SCHEMA_VERSION = 1

TERMINAL_STATUSES = {
    "completed",
    "failed",
    "timeout",
    "cancelled",
    "cost_exceeded",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    run_id TEXT NOT NULL,
    name TEXT NOT NULL,
    plan_name TEXT NOT NULL,
    runtime TEXT NOT NULL,
    profile TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt TEXT NOT NULL,
    check_command TEXT NOT NULL,
    depends_on TEXT NOT NULL,
    max_iterations INTEGER NOT NULL,
    max_cost_usd REAL NOT NULL,
    parent TEXT,
    tree_path TEXT NOT NULL,
    output_schema TEXT,
    env TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, name)
);

CREATE TABLE IF NOT EXISTS attempts (
    attempt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    node_name TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    iteration INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    cost_source TEXT NOT NULL DEFAULT 'sdk',
    vendor_session_id TEXT,
    workspace_id TEXT,
    error TEXT,
    started_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id, node_name) REFERENCES nodes(run_id, name)
);

CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    branch TEXT,
    base_branch TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    agent TEXT,
    event_type TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS coord_responses (
    response_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    request_event_id TEXT NOT NULL,
    response_text TEXT NOT NULL,
    consumed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (request_event_id) REFERENCES events(event_id)
);

CREATE INDEX IF NOT EXISTS idx_attempts_run_node ON attempts(run_id, node_name, attempt_number);
CREATE INDEX IF NOT EXISTS idx_attempts_status ON attempts(run_id, status);
CREATE INDEX IF NOT EXISTS idx_events_run_agent ON events(run_id, agent);
CREATE INDEX IF NOT EXISTS idx_events_run_type ON events(run_id, event_type);
CREATE INDEX IF NOT EXISTS idx_coord_responses_pending ON coord_responses(run_id, request_event_id, consumed);
"""


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def get_run_dir(run_id: str, base_path: Path | None = None) -> Path:
    base = base_path or Path.cwd()
    return base / ".swarm" / "runs" / run_id


def get_db_path(run_id: str, base_path: Path | None = None) -> Path:
    return get_run_dir(run_id, base_path) / "swarm.db"


def get_logs_dir(run_id: str, base_path: Path | None = None) -> Path:
    return get_run_dir(run_id, base_path) / "logs"


def get_log_path(
    run_id: str, agent_name: str, base_path: Path | None = None
) -> Path:
    return get_logs_dir(run_id, base_path) / f"{agent_name}.log"


def ensure_log_file(
    run_id: str, agent_name: str, base_path: Path | None = None
) -> Path:
    log_path = get_log_path(run_id, agent_name, base_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return log_path


def run_exists(run_id: str, base_path: Path | None = None) -> bool:
    return get_db_path(run_id, base_path).exists()


def list_runs(base_path: Path | None = None) -> list[str]:
    base = base_path or Path.cwd()
    runs_dir = base / ".swarm" / "runs"
    if not runs_dir.exists():
        return []
    return sorted([d.name for d in runs_dir.iterdir() if d.is_dir()], reverse=True)


# ---------------------------------------------------------------------------
# Low-level connection management
# ---------------------------------------------------------------------------


def _configure(db: sqlite3.Connection) -> None:
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA busy_timeout = 5000")
    db.execute("PRAGMA synchronous = NORMAL")
    db.execute("PRAGMA foreign_keys = ON")


def open_db(
    run_id: str, base_path: Path | None = None
) -> sqlite3.Connection:
    db_path = get_db_path(run_id, base_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(db_path), timeout=30.0)
    _configure(db)
    return db


@contextmanager
def get_db(
    run_id: str, base_path: Path | None = None
) -> Generator[sqlite3.Connection, None, None]:
    db = open_db(run_id, base_path)
    try:
        yield db
    finally:
        db.close()


def _check_legacy(db: sqlite3.Connection) -> None:
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='agents'"
    ).fetchone()
    if row is not None:
        raise SwarmError(
            "Legacy run database detected (old 'agents' table). "
            "This codebase no longer reads the old schema. "
            "Run `swarm clean --all` to remove legacy runs and rerun."
        )


def init_db(run_id: str, base_path: Path | None = None) -> sqlite3.Connection:
    db = open_db(run_id, base_path)
    _check_legacy(db)
    db.executescript(SCHEMA)
    db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    db.commit()
    logger.info("Initialized database at %s", get_db_path(run_id, base_path))
    return db


# ---------------------------------------------------------------------------
# Node + attempt + workspace helpers
# ---------------------------------------------------------------------------


def insert_node(
    db: sqlite3.Connection,
    *,
    run_id: str,
    name: str,
    plan_name: str,
    runtime: str,
    profile: str,
    model: str,
    prompt: str,
    check_command: str,
    depends_on: Iterable[str],
    max_iterations: int,
    max_cost_usd: float,
    parent: str | None,
    tree_path: str,
    env: dict[str, str] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> None:
    db.execute(
        """INSERT INTO nodes (
            run_id, name, plan_name, runtime, profile, model, prompt,
            check_command, depends_on, max_iterations, max_cost_usd,
            parent, tree_path, output_schema, env
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_id,
            name,
            plan_name,
            runtime,
            profile,
            model,
            prompt,
            check_command,
            json.dumps(list(depends_on)),
            max_iterations,
            max_cost_usd,
            parent,
            tree_path,
            json.dumps(output_schema) if output_schema is not None else None,
            json.dumps(env or {}),
        ),
    )
    db.commit()


def get_node(
    db: sqlite3.Connection, run_id: str, name: str
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM nodes WHERE run_id = ? AND name = ?",
        (run_id, name),
    ).fetchone()


def get_nodes(db: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT * FROM nodes WHERE run_id = ? ORDER BY created_at",
        (run_id,),
    ).fetchall()


def insert_workspace(
    db: sqlite3.Connection,
    *,
    workspace_id: str,
    run_id: str,
    kind: str,
    path: str,
    branch: str | None,
    base_branch: str | None,
) -> None:
    db.execute(
        """INSERT OR IGNORE INTO workspaces
            (workspace_id, run_id, kind, path, branch, base_branch)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (workspace_id, run_id, kind, path, branch, base_branch),
    )
    db.commit()


def get_workspace(
    db: sqlite3.Connection, workspace_id: str
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM workspaces WHERE workspace_id = ?",
        (workspace_id,),
    ).fetchone()


def insert_attempt(
    db: sqlite3.Connection,
    *,
    run_id: str,
    node_name: str,
    attempt_number: int,
    workspace_id: str | None = None,
    status: str = "pending",
) -> str:
    attempt_id = uuid4().hex
    db.execute(
        """INSERT INTO attempts (
            attempt_id, run_id, node_name, attempt_number, status,
            workspace_id
        ) VALUES (?, ?, ?, ?, ?, ?)""",
        (attempt_id, run_id, node_name, attempt_number, status, workspace_id),
    )
    db.commit()
    return attempt_id


def latest_attempt(
    db: sqlite3.Connection, run_id: str, node_name: str
) -> sqlite3.Row | None:
    return db.execute(
        """SELECT * FROM attempts
           WHERE run_id = ? AND node_name = ?
           ORDER BY attempt_number DESC LIMIT 1""",
        (run_id, node_name),
    ).fetchone()


def update_attempt_status(
    db: sqlite3.Connection,
    attempt_id: str,
    status: str,
    error: str | None = None,
) -> None:
    db.execute(
        """UPDATE attempts
             SET status = ?,
                 error = COALESCE(?, error),
                 updated_at = CURRENT_TIMESTAMP
             WHERE attempt_id = ?""",
        (status, error, attempt_id),
    )
    db.commit()


def update_attempt_iteration(
    db: sqlite3.Connection, attempt_id: str, iteration: int
) -> None:
    db.execute(
        """UPDATE attempts
             SET iteration = ?, updated_at = CURRENT_TIMESTAMP
             WHERE attempt_id = ?""",
        (iteration, attempt_id),
    )
    db.commit()


def update_attempt_cost(
    db: sqlite3.Connection,
    attempt_id: str,
    cost_usd: float,
    cost_source: str,
) -> None:
    db.execute(
        """UPDATE attempts
             SET cost_usd = ?, cost_source = ?, updated_at = CURRENT_TIMESTAMP
             WHERE attempt_id = ?""",
        (cost_usd, cost_source, attempt_id),
    )
    db.commit()


def update_attempt_session(
    db: sqlite3.Connection, attempt_id: str, vendor_session_id: str
) -> None:
    db.execute(
        """UPDATE attempts
             SET vendor_session_id = ?, updated_at = CURRENT_TIMESTAMP
             WHERE attempt_id = ?""",
        (vendor_session_id, attempt_id),
    )
    db.commit()


def mark_attempt_started(db: sqlite3.Connection, attempt_id: str) -> None:
    db.execute(
        """UPDATE attempts
             SET status = 'running',
                 started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                 updated_at = CURRENT_TIMESTAMP
             WHERE attempt_id = ?""",
        (attempt_id,),
    )
    db.commit()


def get_attempt(
    db: sqlite3.Connection, attempt_id: str
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM attempts WHERE attempt_id = ?",
        (attempt_id,),
    ).fetchone()


def get_total_cost(db: sqlite3.Connection, run_id: str) -> float:
    row = db.execute(
        """SELECT SUM(cost_usd) FROM attempts a
           WHERE a.run_id = ?
             AND a.attempt_number = (
                 SELECT MAX(attempt_number) FROM attempts b
                 WHERE b.run_id = a.run_id AND b.node_name = a.node_name
             )""",
        (run_id,),
    ).fetchone()[0]
    return row or 0.0


def pending_nodes(db: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    """Nodes whose latest attempt is pending and whose deps are satisfied."""
    rows = db.execute(
        """SELECT n.*, a.attempt_id, a.attempt_number, a.status AS attempt_status
             FROM nodes n
             JOIN attempts a
               ON a.run_id = n.run_id AND a.node_name = n.name
             WHERE n.run_id = ?
               AND a.attempt_number = (
                   SELECT MAX(attempt_number) FROM attempts b
                   WHERE b.run_id = n.run_id AND b.node_name = n.name
               )
               AND a.status = 'pending'""",
        (run_id,),
    ).fetchall()
    ready: list[sqlite3.Row] = []
    for r in rows:
        deps = json.loads(r["depends_on"])
        if all(_dep_terminal(db, run_id, dep) for dep in deps):
            ready.append(r)
    return ready


def _dep_terminal(
    db: sqlite3.Connection, run_id: str, dep_name: str
) -> bool:
    row = db.execute(
        """SELECT status FROM attempts
             WHERE run_id = ? AND node_name = ?
             ORDER BY attempt_number DESC LIMIT 1""",
        (run_id, dep_name),
    ).fetchone()
    if row is None:
        return False
    return row["status"] in TERMINAL_STATUSES


def all_nodes_done(db: sqlite3.Connection, run_id: str) -> bool:
    row = db.execute(
        """SELECT COUNT(*) FROM attempts a
             WHERE a.run_id = ?
               AND a.attempt_number = (
                   SELECT MAX(attempt_number) FROM attempts b
                   WHERE b.run_id = a.run_id AND b.node_name = a.node_name
               )
               AND a.status NOT IN ('completed','failed','timeout','cancelled','cost_exceeded')""",
        (run_id,),
    ).fetchone()[0]
    return row == 0


# ---------------------------------------------------------------------------
# Events and coordination responses
# ---------------------------------------------------------------------------


def _event_kind(event: SwarmEvent) -> str:
    return type(event).__name__


def _event_data(event: SwarmEvent) -> str:
    if is_dataclass(event):
        payload = {k: v for k, v in asdict(event).items() if k not in ("run_id", "agent")}
        return json.dumps(payload, default=str)
    return json.dumps({"repr": repr(event)})


def insert_event(
    db: sqlite3.Connection,
    *,
    run_id: str,
    agent: str | None,
    event_type: str,
    data: dict[str, Any] | None = None,
) -> str:
    event_id = uuid4().hex
    db.execute(
        "INSERT INTO events (event_id, run_id, agent, event_type, data) VALUES (?, ?, ?, ?, ?)",
        (event_id, run_id, agent, event_type, json.dumps(data or {})),
    )
    db.commit()
    return event_id


def get_recent_events(
    db: sqlite3.Connection,
    run_id: str,
    limit: int = 50,
) -> list[sqlite3.Row]:
    return db.execute(
        """SELECT agent, event_type, data, created_at FROM events
             WHERE run_id = ?
             ORDER BY created_at DESC LIMIT ?""",
        (run_id, limit),
    ).fetchall()


def insert_response(
    db: sqlite3.Connection,
    run_id: str,
    request_event_id: str,
    response_text: str,
) -> str:
    response_id = uuid4().hex
    db.execute(
        """INSERT INTO coord_responses
             (response_id, run_id, request_event_id, response_text)
           VALUES (?, ?, ?, ?)""",
        (response_id, run_id, request_event_id, response_text),
    )
    db.commit()
    return response_id


def get_pending_response(
    db: sqlite3.Connection, run_id: str, request_event_id: str
) -> sqlite3.Row | None:
    return db.execute(
        """SELECT response_id, response_text FROM coord_responses
             WHERE run_id = ? AND request_event_id = ? AND consumed = 0
             LIMIT 1""",
        (run_id, request_event_id),
    ).fetchone()


def consume_response(db: sqlite3.Connection, response_id: str) -> None:
    db.execute(
        "UPDATE coord_responses SET consumed = 1 WHERE response_id = ?",
        (response_id,),
    )
    db.commit()


def get_pending_clarifications_for_parent(
    db: sqlite3.Connection, run_id: str, parent: str
) -> list[dict]:
    rows = db.execute(
        """SELECT e.event_id, e.agent, json_extract(e.data, '$.question') AS question
             FROM events e
             WHERE e.run_id = ?
               AND e.event_type IN ('clarification','blocker')
               AND NOT EXISTS (
                   SELECT 1 FROM coord_responses r
                   WHERE r.request_event_id = e.event_id
               )""",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows if r["agent"].startswith(f"{parent}.")]


# ---------------------------------------------------------------------------
# SqliteSink — EventSink for batch mode
# ---------------------------------------------------------------------------


class SqliteSink:
    """Writes events to the events table and forwards LogText to log files.

    One sink per run. Construct it once in the scheduler and pass it into
    RunContext; executors call ctx.events.emit(...) without caring about
    persistence.
    """

    def __init__(self, run_id: str, base_path: Path | None = None):
        self.run_id = run_id
        self.base_path = base_path

    def emit(self, event: SwarmEvent) -> None:
        from swarm.batch.logs import append_agent_log

        agent = getattr(event, "agent", None)
        event_type = _event_kind(event)
        data = _event_data(event)

        with get_db(self.run_id, self.base_path) as db:
            db.execute(
                "INSERT INTO events (event_id, run_id, agent, event_type, data) VALUES (?, ?, ?, ?, ?)",
                (uuid4().hex, self.run_id, agent, event_type, data),
            )
            db.commit()

            if isinstance(event, LogText):
                append_agent_log(self.run_id, event.agent, event.text, self.base_path)
            elif isinstance(event, IterationTick):
                row = latest_attempt(db, self.run_id, event.agent)
                if row is not None:
                    update_attempt_iteration(db, row["attempt_id"], event.iteration)
            elif isinstance(event, CostUpdate):
                row = latest_attempt(db, self.run_id, event.agent)
                if row is not None:
                    update_attempt_cost(
                        db, row["attempt_id"], event.cost_usd, event.source
                    )
            elif isinstance(event, AgentStarted):
                row = latest_attempt(db, self.run_id, event.agent)
                if row is not None:
                    mark_attempt_started(db, row["attempt_id"])
            elif isinstance(event, AgentCompleted):
                row = latest_attempt(db, self.run_id, event.agent)
                if row is not None:
                    update_attempt_status(
                        db,
                        row["attempt_id"],
                        event.status,
                        event.error,
                    )


# ---------------------------------------------------------------------------
# SqliteCoordinationBackend — CoordinationBackend for batch mode
# ---------------------------------------------------------------------------


_WORKER_OPS = {
    CoordOp.MARK_COMPLETE,
    CoordOp.REPORT_PROGRESS,
    CoordOp.REPORT_BLOCKER,
    CoordOp.REQUEST_CLARIFICATION,
}
_ORCHESTRATOR_OPS = {
    CoordOp.SPAWN,
    CoordOp.STATUS,
    CoordOp.RESPOND,
    CoordOp.CANCEL,
    CoordOp.PENDING_CLARIFICATIONS,
    CoordOp.MARK_PLAN_COMPLETE,
}
_ALL_OPS = _WORKER_OPS | _ORCHESTRATOR_OPS


class SqliteCoordinationBackend:
    """CoordinationBackend that persists everything in the 5-table schema.

    Construct once per run in the scheduler. Polling loops for
    request_clarification / report_blocker share the same db path.
    """

    name = "sqlite"

    def __init__(self, base_path: Path | None = None, poll_interval: float = 2.0):
        self.base_path = base_path
        self.poll_interval = poll_interval

    def supports(self, op: CoordOp) -> bool:
        return op in _ALL_OPS

    # -- worker ops ---------------------------------------------------------

    async def mark_complete(
        self, run_id: str, agent: str, summary: str
    ) -> CoordResult:
        with get_db(run_id, self.base_path) as db:
            node = get_node(db, run_id, agent)
            if node is None:
                return CoordResult(text=f"ERROR: Agent {agent} not found", success=False)

            attempt = latest_attempt(db, run_id, agent)
            if attempt is None:
                return CoordResult(
                    text=f"ERROR: No active attempt for {agent}",
                    success=False,
                )

            check_cmd = node["check_command"] or "true"
            workspace_row = (
                get_workspace(db, attempt["workspace_id"])
                if attempt["workspace_id"]
                else None
            )
            cwd = workspace_row["path"] if workspace_row else None

            result = subprocess.run(
                check_cmd, shell=True, capture_output=True, text=True, cwd=cwd
            )
            if result.returncode == 0:
                update_attempt_status(db, attempt["attempt_id"], "completed")
                insert_event(
                    db,
                    run_id=run_id,
                    agent=agent,
                    event_type="done",
                    data={"summary": summary},
                )
                return CoordResult(text="Task completed successfully. Check passed.")

            output = f"{result.stdout}\n{result.stderr}".strip()
            return CoordResult(
                text=f"Check failed. Fix and retry.\n\nOutput:\n{output}",
                success=False,
            )

    async def report_progress(
        self, run_id: str, agent: str, status: str, milestone: str | None
    ) -> CoordResult:
        data: dict[str, Any] = {"status": status}
        if milestone:
            data["milestone"] = milestone
        with get_db(run_id, self.base_path) as db:
            insert_event(db, run_id=run_id, agent=agent, event_type="progress", data=data)
        return CoordResult(text="Progress recorded.")

    async def report_blocker(
        self, run_id: str, agent: str, issue: str, timeout: int
    ) -> CoordResult:
        return await self._ask_parent(
            run_id, agent, issue, escalate_to="parent", timeout=timeout, kind="blocker"
        )

    async def request_clarification(
        self,
        run_id: str,
        agent: str,
        question: str,
        escalate_to: str,
        timeout: int,
    ) -> CoordResult:
        return await self._ask_parent(
            run_id,
            agent,
            question,
            escalate_to=escalate_to,
            timeout=timeout,
            kind="clarification",
        )

    async def _ask_parent(
        self,
        run_id: str,
        agent: str,
        question: str,
        *,
        escalate_to: str,
        timeout: int,
        kind: str,
    ) -> CoordResult:
        with get_db(run_id, self.base_path) as db:
            event_id = insert_event(
                db,
                run_id=run_id,
                agent=agent,
                event_type=kind,
                data={"question": question, "escalate_to": escalate_to},
            )
            attempt = latest_attempt(db, run_id, agent)
            if attempt is not None:
                update_attempt_status(db, attempt["attempt_id"], "blocked")

        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            with get_db(run_id, self.base_path) as db:
                pending = get_pending_response(db, run_id, event_id)
                if pending is not None:
                    consume_response(db, pending["response_id"])
                    attempt = latest_attempt(db, run_id, agent)
                    if attempt is not None:
                        update_attempt_status(db, attempt["attempt_id"], "running")
                    return CoordResult(
                        text=f"Manager response: {pending['response_text']}",
                        data={"response_text": pending["response_text"]},
                    )
            await asyncio.sleep(self.poll_interval)

        with get_db(run_id, self.base_path) as db:
            attempt = latest_attempt(db, run_id, agent)
            if attempt is not None:
                update_attempt_status(
                    db,
                    attempt["attempt_id"],
                    "timeout",
                    f"{kind} timeout",
                )
            insert_event(
                db,
                run_id=run_id,
                agent=agent,
                event_type="error",
                data={"error": f"{kind} timeout", "question": question},
            )
        return CoordResult(
            text=f"ERROR: {kind} timeout. No response from parent.",
            success=False,
        )

    # -- orchestrator ops ---------------------------------------------------

    async def spawn(
        self, run_id: str, parent: str, request: AgentRequest
    ) -> CoordResult:
        from swarm.batch.plan import resolve_child  # local import to avoid cycle

        child_name = f"{parent}.{request.name}"
        with get_db(run_id, self.base_path) as db:
            if get_node(db, run_id, child_name) is not None:
                return CoordResult(
                    text=f"Child {child_name} already exists",
                    success=False,
                )
            parent_node = get_node(db, run_id, parent)
            resolved = resolve_child(
                request, parent_row=parent_node, parent_name=parent
            )
            insert_node(
                db,
                run_id=run_id,
                name=child_name,
                plan_name=parent_node["plan_name"] if parent_node else "inline",
                runtime=resolved.runtime,
                profile=resolved.profile.name,
                model=resolved.model,
                prompt=resolved.prompt,
                check_command=resolved.check,
                depends_on=[],
                max_iterations=resolved.limits.max_iterations,
                max_cost_usd=resolved.limits.max_cost_usd,
                parent=parent,
                tree_path=resolved.tree_path,
                env=dict(resolved.env),
                output_schema=resolved.output_schema,
            )
            insert_attempt(
                db,
                run_id=run_id,
                node_name=child_name,
                attempt_number=1,
                status="pending",
            )
            insert_event(
                db,
                run_id=run_id,
                agent=parent,
                event_type="progress",
                data={"status": f"Spawned worker {child_name}", "worker": child_name},
            )
        return CoordResult(text=f"Spawned worker: {child_name}")

    async def status(
        self, run_id: str, parent: str, name: str | None
    ) -> CoordResult:
        with get_db(run_id, self.base_path) as db:
            if name:
                worker = name if "." in name else f"{parent}.{name}"
                node = get_node(db, run_id, worker)
                if node is None:
                    return CoordResult(text=f"Worker not found: {name}", success=False)
                attempt = latest_attempt(db, run_id, worker)
                if attempt is None:
                    return CoordResult(text=f"No attempts yet for {worker}")
                text = (
                    f"Worker: {worker}\n"
                    f"Status: {attempt['status']}\n"
                    f"Iteration: {attempt['iteration']}/{node['max_iterations']}"
                )
                if attempt["error"]:
                    text += f"\nError: {str(attempt['error'])[:200]}"
                return CoordResult(text=text)

            nodes = get_nodes(db, run_id)
            workers = [n for n in nodes if n["parent"] == parent]
            if not workers:
                return CoordResult(text="No workers spawned yet.")
            lines = ["Workers:"]
            for w in workers:
                a = latest_attempt(db, run_id, w["name"])
                status = a["status"] if a else "pending"
                short = w["name"].split(".")[-1]
                iter_count = a["iteration"] if a else 0
                lines.append(
                    f"  {short}: {status} (iter {iter_count}/{w['max_iterations']})"
                )
                if a and a["error"]:
                    lines.append(f"    Error: {str(a['error'])[:100]}")
            return CoordResult(text="\n".join(lines))

    async def respond(
        self,
        run_id: str,
        parent: str,
        clarification_id: str,
        response: str,
    ) -> CoordResult:
        with get_db(run_id, self.base_path) as db:
            insert_response(db, run_id, clarification_id, response)
        return CoordResult(
            text=f"Response sent to clarification {clarification_id[:8]}"
        )

    async def cancel(
        self, run_id: str, parent: str, name: str
    ) -> CoordResult:
        with get_db(run_id, self.base_path) as db:
            worker = name if "." in name else f"{parent}.{name}"
            node = get_node(db, run_id, worker)
            if node is None:
                node = get_node(db, run_id, name)
                worker = name if node else worker
            if node is None:
                return CoordResult(text=f"Worker not found: {name}", success=False)
            attempt = latest_attempt(db, run_id, worker)
            if attempt and attempt["status"] in TERMINAL_STATUSES:
                return CoordResult(
                    text=f"Worker {worker} already in terminal state: {attempt['status']}",
                    success=False,
                )
            if attempt:
                update_attempt_status(
                    db, attempt["attempt_id"], "cancelled", "Cancelled by parent"
                )
            insert_event(
                db,
                run_id=run_id,
                agent=parent,
                event_type="progress",
                data={"status": f"Cancelled worker {worker}", "worker": worker},
            )
        return CoordResult(text=f"Cancelled worker: {worker}")

    async def pending_clarifications(
        self, run_id: str, parent: str
    ) -> CoordResult:
        with get_db(run_id, self.base_path) as db:
            mine = get_pending_clarifications_for_parent(db, run_id, parent)
        if not mine:
            return CoordResult(text="No pending clarifications.")
        lines = ["Pending clarifications:"]
        for c in mine:
            short = c["agent"].split(".")[-1]
            lines.append(f"  [{c['event_id'][:8]}] {short}: {c['question']}")
        return CoordResult(text="\n".join(lines))

    async def mark_plan_complete(
        self, run_id: str, agent: str, summary: str
    ) -> CoordResult:
        with get_db(run_id, self.base_path) as db:
            nodes = get_nodes(db, run_id)
            workers = [n for n in nodes if n["parent"] == agent]
            pending = []
            for w in workers:
                a = latest_attempt(db, run_id, w["name"])
                if a is None or a["status"] not in TERMINAL_STATUSES:
                    pending.append(w["name"].split(".")[-1])
            if pending:
                return CoordResult(
                    text=f"Cannot complete: workers still running: {pending}",
                    success=False,
                )
            attempt = latest_attempt(db, run_id, agent)
            if attempt is not None:
                update_attempt_status(db, attempt["attempt_id"], "completed")
            insert_event(
                db,
                run_id=run_id,
                agent=agent,
                event_type="done",
                data={"summary": summary},
            )
            completed = [
                w["name"].split(".")[-1]
                for w in workers
                if (latest_attempt(db, run_id, w["name"]) or {"status": ""})["status"]
                == "completed"
            ]
            failed = [
                w["name"].split(".")[-1]
                for w in workers
                if (latest_attempt(db, run_id, w["name"]) or {"status": ""})["status"]
                == "failed"
            ]
        text = f"Plan complete. Completed workers: {completed}"
        if failed:
            text += f". Failed workers: {failed}"
        return CoordResult(text=text)
