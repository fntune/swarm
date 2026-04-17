"""Manager coordination tools for claude-swarm agents."""

import logging
import re

from swarm.runtime import task_registry
from swarm.storage.db import (
    get_agent,
    get_agents,
    get_db,
    get_pending_clarifications as db_get_pending_clarifications,
    insert_agent,
    insert_event,
    insert_response,
    update_agent_status,
)

logger = logging.getLogger("swarm.tools.manager")
VALID_WORKER_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def _get_owned_worker(db, run_id: str, manager_name: str, name: str):
    """Resolve a worker only if it belongs to the manager."""
    worker_name = name if "." in name else f"{manager_name}.{name}"
    agent = get_agent(db, run_id, worker_name)
    if agent and agent["parent"] == manager_name:
        return agent
    return None


async def spawn_worker(
    run_id: str,
    manager_name: str,
    name: str,
    prompt: str,
    check: str | None = None,
    model: str = "sonnet",
) -> dict:
    """Spawn a new worker agent."""
    with get_db(run_id) as db:
        if not VALID_WORKER_NAME.fullmatch(name):
            return {"content": [{"type": "text", "text": f"Invalid worker name: {name}"}]}

        worker_name = f"{manager_name}.{name}"

        existing = get_agent(db, run_id, worker_name)
        if existing:
            return {"content": [{"type": "text", "text": f"Worker {worker_name} already exists (status: {existing['status']})"}]}

        manager = get_agent(db, run_id, manager_name)
        default_check = manager["check_command"] if manager else "true"

        # Enforce manager's max_subagents cap before any worktree/DB side effects.
        max_subagents = None
        if manager is not None:
            try:
                max_subagents = manager["max_subagents"]
            except (IndexError, KeyError):
                max_subagents = None
        if max_subagents is not None:
            existing_children = db.execute(
                "SELECT COUNT(*) FROM agents WHERE run_id = ? AND parent = ?",
                (run_id, manager_name),
            ).fetchone()[0]
            if existing_children >= max_subagents:
                insert_event(db, run_id, manager_name, "error", {
                    "error": "max_subagents_exceeded",
                    "limit": max_subagents,
                    "spawned": existing_children,
                    "rejected": worker_name,
                })
                logger.warning(
                    f"Manager {manager_name} blocked from spawning {worker_name}: "
                    f"max_subagents={max_subagents}, already spawned={existing_children}"
                )
                return {"content": [{"type": "text", "text": (
                    f"Cannot spawn worker: max_subagents={max_subagents} already reached "
                    f"(spawned={existing_children})."
                )}]}

        insert_agent(
            db,
            run_id,
            worker_name,
            prompt,
            agent_type="worker",
            check_command=check or default_check,
            model=model,
            parent=manager_name,
        )

        insert_event(db, run_id, manager_name, "progress", {
            "status": f"Spawned worker {worker_name}",
            "worker": worker_name,
        })

        logger.info(f"Manager {manager_name} spawned worker {worker_name}")
        return {"content": [{"type": "text", "text": f"Spawned worker: {worker_name}"}]}


async def respond_to_clarification(run_id: str, manager_name: str, clarification_id: str, response: str) -> dict:
    """Respond to a worker's clarification request."""
    with get_db(run_id) as db:
        clarification = db.execute(
            """
            SELECT agent FROM events
            WHERE run_id = ? AND id = ? AND event_type IN ('clarification', 'blocker')
            """,
            (run_id, clarification_id),
        ).fetchone()
        if not clarification or not clarification["agent"].startswith(f"{manager_name}."):
            return {"content": [{"type": "text", "text": f"Clarification not found: {clarification_id[:8]}"}]}

        insert_response(db, run_id, clarification_id, response)
        logger.info(f"Manager {manager_name} responded to clarification {clarification_id[:8]}")
        return {"content": [{"type": "text", "text": f"Response sent to clarification {clarification_id[:8]}"}]}


async def cancel_worker(run_id: str, manager_name: str, name: str) -> dict:
    """Cancel a worker agent."""
    with get_db(run_id) as db:
        agent = _get_owned_worker(db, run_id, manager_name, name)
        if not agent:
            return {"content": [{"type": "text", "text": f"Worker not found: {name}"}]}

        worker_name = agent["name"]
        if agent["status"] in ("completed", "failed", "cancelled"):
            return {"content": [{"type": "text", "text": f"Worker {worker_name} already in terminal state: {agent['status']}"}]}

        # Flip status first so a racing mark_complete on the worker refuses
        # to transition the cancelled agent back to completed.
        update_agent_status(db, run_id, worker_name, "cancelled", "Cancelled by manager")
        cancelled_task = task_registry.cancel(run_id, worker_name)
        insert_event(db, run_id, manager_name, "progress", {
            "status": f"Cancelled worker {worker_name}",
            "worker": worker_name,
            "task_cancelled": cancelled_task,
        })

        logger.info(
            f"Manager {manager_name} cancelled worker {worker_name} "
            f"(live task cancelled: {cancelled_task})"
        )
        return {"content": [{"type": "text", "text": f"Cancelled worker: {worker_name}"}]}


async def get_worker_status(run_id: str, manager_name: str, name: str | None = None) -> dict:
    """Get status of workers."""
    with get_db(run_id) as db:
        if name:
            agent = _get_owned_worker(db, run_id, manager_name, name)
            if not agent:
                return {"content": [{"type": "text", "text": f"Worker not found: {name}"}]}

            status_text = f"Worker: {agent['name']}\nStatus: {agent['status']}\nIteration: {agent['iteration']}/{agent['max_iterations']}"
            if agent["error"]:
                status_text += f"\nError: {agent['error'][:200]}"
            return {"content": [{"type": "text", "text": status_text}]}

        else:
            all_agents = get_agents(db, run_id)
            workers = [a for a in all_agents if a["parent"] == manager_name]

            if not workers:
                return {"content": [{"type": "text", "text": "No workers spawned yet."}]}

            lines = ["Workers:"]
            for w in workers:
                status = w["status"]
                short_name = w["name"].split(".")[-1]
                lines.append(f"  {short_name}: {status} (iter {w['iteration']}/{w['max_iterations']})")
                if w["error"]:
                    lines.append(f"    Error: {w['error'][:100]}")

            return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def get_pending_clarifications(run_id: str, manager_name: str) -> dict:
    """Get all pending clarifications from workers."""
    with get_db(run_id) as db:
        clarifications = db_get_pending_clarifications(db, run_id)

        my_clarifications = [
            c for c in clarifications
            if c["agent"].startswith(f"{manager_name}.")
        ]

        if not my_clarifications:
            return {"content": [{"type": "text", "text": "No pending clarifications."}]}

        lines = ["Pending clarifications:"]
        for c in my_clarifications:
            short_name = c["agent"].split(".")[-1]
            lines.append(f"  [{c['id'][:8]}] {short_name}: {c['question']}")

        return {"content": [{"type": "text", "text": "\n".join(lines)}]}


async def mark_plan_complete(run_id: str, manager_name: str, summary: str) -> dict:
    """Signal that the manager's plan is complete."""
    with get_db(run_id) as db:
        all_agents = get_agents(db, run_id)
        workers = [a for a in all_agents if a["parent"] == manager_name]

        pending = [w for w in workers if w["status"] not in ("completed", "failed", "cancelled", "timeout")]
        if pending:
            names = [w["name"].split(".")[-1] for w in pending]
            return {"content": [{"type": "text", "text": f"Cannot complete: workers still running: {names}"}]}

        update_agent_status(db, run_id, manager_name, "completed")
        insert_event(db, run_id, manager_name, "done", {"summary": summary})

        failed_workers = [w["name"].split(".")[-1] for w in workers if w["status"] == "failed"]
        completed_workers = [w["name"].split(".")[-1] for w in workers if w["status"] == "completed"]

        result = f"Plan complete. Completed workers: {completed_workers}"
        if failed_workers:
            result += f". Failed workers: {failed_workers}"

        logger.info(f"Manager {manager_name} completed: {summary}")
        return {"content": [{"type": "text", "text": result}]}
