"""Worker coordination tools for claude-swarm agents."""

import asyncio
import logging
import os
import subprocess

from swarm.storage.db import (
    consume_response,
    get_agent,
    get_db,
    get_response,
    insert_event,
    update_agent_status,
)

logger = logging.getLogger("swarm.tools.worker")


async def _poll_for_response(
    run_id: str,
    agent_name: str,
    clarification_id: str,
    timeout: int,
    response_type: str,
) -> dict | None:
    """Poll for manager response to clarification/blocker."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        with get_db(run_id) as db:
            response = get_response(db, run_id, clarification_id)
            if response:
                consume_response(db, response["id"])
                update_agent_status(db, run_id, agent_name, "running")
                logger.info(f"Agent {agent_name} received {response_type}: {response['response']}")
                return dict(response)

        await asyncio.sleep(2)

    return None


async def mark_complete(run_id: str, agent_name: str, summary: str) -> dict:
    """Signal task completion. Runs check command automatically."""
    with get_db(run_id) as db:
        agent = get_agent(db, run_id, agent_name)
        if not agent:
            return {"content": [{"type": "text", "text": f"ERROR: Agent {agent_name} not found"}]}

        check_cmd = agent["check_command"] or "true"
        worktree = agent["worktree"]
        logger.info(f"Running check command: {check_cmd}")
        result = subprocess.run(
            check_cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=worktree,
        )

        if result.returncode == 0:
            update_agent_status(db, run_id, agent_name, "completed")
            insert_event(db, run_id, agent_name, "done", {"summary": summary})
            logger.info(f"Agent {agent_name} completed successfully")
            return {"content": [{"type": "text", "text": "Task completed successfully. Check passed."}]}
        else:
            output = f"{result.stdout}\n{result.stderr}".strip()
            logger.warning(f"Check failed for {agent_name}: {output}")
            return {"content": [{"type": "text", "text": f"Check failed. Fix and retry.\n\nOutput:\n{output}"}]}


async def request_clarification(
    run_id: str,
    agent_name: str,
    question: str,
    escalate_to: str = "auto",
    timeout: int = 300,
) -> dict:
    """Ask manager for guidance. BLOCKS until response received."""
    with get_db(run_id) as db:
        event_id = insert_event(
            db,
            run_id,
            agent_name,
            "clarification",
            {
                "question": question,
                "escalate_to": escalate_to,
                "parent_agent": os.environ.get("SWARM_PARENT_AGENT", ""),
                "tree_path": os.environ.get("SWARM_TREE_PATH", ""),
            },
        )
        update_agent_status(db, run_id, agent_name, "blocked")
        logger.info(f"Agent {agent_name} blocked on clarification: {question}")

    response = await _poll_for_response(run_id, agent_name, event_id, timeout, "response")
    if response:
        return {"content": [{"type": "text", "text": f"Manager response: {response['response']}"}]}

    with get_db(run_id) as db:
        update_agent_status(db, run_id, agent_name, "timeout", "Clarification timeout")
        insert_event(db, run_id, agent_name, "error", {"error": "Clarification timeout", "question": question})
    logger.error(f"Agent {agent_name} timed out waiting for clarification")
    return {"content": [{"type": "text", "text": "ERROR: Clarification timeout. No response from manager."}]}


async def report_progress(run_id: str, agent_name: str, status: str, milestone: str | None = None) -> dict:
    """Report progress update."""
    with get_db(run_id) as db:
        data = {"status": status}
        if milestone:
            data["milestone"] = milestone

        insert_event(db, run_id, agent_name, "progress", data)
        logger.info(f"Agent {agent_name} progress: {status}" + (f" (milestone: {milestone})" if milestone else ""))
        return {"content": [{"type": "text", "text": "Progress recorded."}]}


async def report_blocker(run_id: str, agent_name: str, issue: str, timeout: int = 300) -> dict:
    """Report blocking issue. BLOCKS until manager responds."""
    with get_db(run_id) as db:
        event_id = insert_event(
            db,
            run_id,
            agent_name,
            "blocker",
            {
                "question": issue,
                "escalate_to": "parent",
                "parent_agent": os.environ.get("SWARM_PARENT_AGENT", ""),
                "tree_path": os.environ.get("SWARM_TREE_PATH", ""),
            },
        )
        update_agent_status(db, run_id, agent_name, "blocked")
        logger.info(f"Agent {agent_name} blocked on issue: {issue}")

    response = await _poll_for_response(run_id, agent_name, event_id, timeout, "guidance")
    if response:
        return {"content": [{"type": "text", "text": f"Manager guidance: {response['response']}"}]}

    with get_db(run_id) as db:
        update_agent_status(db, run_id, agent_name, "timeout", "Blocker timeout")
        insert_event(db, run_id, agent_name, "error", {"error": "Blocker timeout", "issue": issue})
    logger.error(f"Agent {agent_name} timed out waiting for blocker resolution")
    return {"content": [{"type": "text", "text": "ERROR: Blocker timeout. No response from manager."}]}
