"""Coordination tools for claude-swarm agents.

These tools are designed to be used with the Claude Agent SDK as in-process MCP tools.
Since the SDK may not be available, we provide stub implementations that can be
called directly from the executor.
"""

import asyncio
import logging
import os
import subprocess
from uuid import uuid4

from swarm.db import (
    consume_response,
    get_agent,
    get_agents,
    get_db,
    get_pending_clarifications as db_get_pending_clarifications,
    get_response,
    insert_agent,
    insert_event,
    insert_response,
    update_agent_status,
)

logger = logging.getLogger("swarm.tools")


def get_run_context() -> tuple[str, str]:
    """Get run_id and agent_name from environment."""
    run_id = os.environ.get("SWARM_RUN_ID", "")
    agent_name = os.environ.get("SWARM_AGENT_NAME", "")
    if not run_id or not agent_name:
        raise RuntimeError("SWARM_RUN_ID and SWARM_AGENT_NAME must be set")
    return run_id, agent_name


async def _poll_for_response(
    run_id: str,
    agent_name: str,
    clarification_id: str,
    timeout: int,
    response_type: str,
) -> dict | None:
    """Poll for manager response to clarification/blocker.

    Args:
        run_id: Run identifier
        agent_name: Agent name
        clarification_id: ID of the clarification request
        timeout: Max seconds to wait
        response_type: "clarification" or "blocker" (for logging)

    Returns:
        Response dict if received, None if timeout
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        with get_db(run_id) as db:
            response = get_response(db, run_id, clarification_id)
            if response:
                consume_response(db, response["id"])
                update_agent_status(db, run_id, agent_name, "running")
                logger.info(f"Agent {agent_name} received {response_type}: {response['response']}")
                return response

        await asyncio.sleep(2)

    return None


async def mark_complete(summary: str) -> dict:
    """Signal task completion. Runs check command automatically.

    Args:
        summary: Summary of work completed

    Returns:
        Tool result dict with success/failure message
    """
    run_id, agent_name = get_run_context()

    with get_db(run_id) as db:
        # Get check command from DB
        agent = get_agent(db, run_id, agent_name)
        if not agent:
            return {"content": [{"type": "text", "text": f"ERROR: Agent {agent_name} not found"}]}

        check_cmd = agent["check_command"] or "true"

        # Run check command in worktree
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
            # Success - mark completed
            update_agent_status(db, run_id, agent_name, "completed")
            insert_event(db, run_id, agent_name, "done", {"summary": summary})
            logger.info(f"Agent {agent_name} completed successfully")
            return {"content": [{"type": "text", "text": "Task completed successfully. Check passed."}]}
        else:
            # Failed - return error, agent continues
            output = f"{result.stdout}\n{result.stderr}".strip()
            logger.warning(f"Check failed for {agent_name}: {output}")
            return {"content": [{"type": "text", "text": f"Check failed. Fix and retry.\n\nOutput:\n{output}"}]}


async def request_clarification(
    question: str,
    escalate_to: str = "auto",
    timeout: int = 300,
) -> dict:
    """Ask manager for guidance. BLOCKS until response received.

    Args:
        question: Question to ask manager
        escalate_to: Who to escalate to ("parent", "human", "auto")
        timeout: Max seconds to wait for response

    Returns:
        Tool result dict with manager's response
    """
    run_id, agent_name = get_run_context()
    clarification_id = uuid4().hex

    with get_db(run_id) as db:
        # Emit clarification event
        insert_event(
            db,
            run_id,
            agent_name,
            "clarification",
            {
                "question": question,
                "escalate_to": escalate_to,
                "parent_agent": os.environ.get("SWARM_PARENT_AGENT", ""),
                "tree_path": os.environ.get("SWARM_TREE_PATH", ""),
                "clarification_id": clarification_id,
            },
        )
        update_agent_status(db, run_id, agent_name, "blocked")
        logger.info(f"Agent {agent_name} blocked on clarification: {question}")

    # Poll for response
    response = await _poll_for_response(run_id, agent_name, clarification_id, timeout, "response")
    if response:
        return {"content": [{"type": "text", "text": f"Manager response: {response['response']}"}]}

    # Timeout
    with get_db(run_id) as db:
        update_agent_status(db, run_id, agent_name, "timeout", "Clarification timeout")
        insert_event(db, run_id, agent_name, "error", {"error": "Clarification timeout", "question": question})
    logger.error(f"Agent {agent_name} timed out waiting for clarification")
    return {"content": [{"type": "text", "text": "ERROR: Clarification timeout. No response from manager."}]}


async def report_progress(status: str, milestone: str | None = None) -> dict:
    """Report progress update.

    Args:
        status: Current status description
        milestone: Optional milestone name (e.g., 'core_impl')

    Returns:
        Tool result dict
    """
    run_id, agent_name = get_run_context()

    with get_db(run_id) as db:
        data = {"status": status}
        if milestone:
            data["milestone"] = milestone

        insert_event(db, run_id, agent_name, "progress", data)
        logger.info(f"Agent {agent_name} progress: {status}" + (f" (milestone: {milestone})" if milestone else ""))
        return {"content": [{"type": "text", "text": "Progress recorded."}]}


async def report_blocker(issue: str, timeout: int = 300) -> dict:
    """Report blocking issue. BLOCKS until manager responds.

    Args:
        issue: Description of the blocking issue
        timeout: Max seconds to wait for response

    Returns:
        Tool result dict with manager's guidance
    """
    run_id, agent_name = get_run_context()
    clarification_id = uuid4().hex

    with get_db(run_id) as db:
        # Emit blocker event
        insert_event(
            db,
            run_id,
            agent_name,
            "blocker",
            {
                "question": issue,
                "escalate_to": "parent",
                "parent_agent": os.environ.get("SWARM_PARENT_AGENT", ""),
                "tree_path": os.environ.get("SWARM_TREE_PATH", ""),
                "clarification_id": clarification_id,
            },
        )
        update_agent_status(db, run_id, agent_name, "blocked")
        logger.info(f"Agent {agent_name} blocked on issue: {issue}")

    # Poll for response
    response = await _poll_for_response(run_id, agent_name, clarification_id, timeout, "guidance")
    if response:
        return {"content": [{"type": "text", "text": f"Manager guidance: {response['response']}"}]}

    # Timeout
    with get_db(run_id) as db:
        update_agent_status(db, run_id, agent_name, "timeout", "Blocker timeout")
        insert_event(db, run_id, agent_name, "error", {"error": "Blocker timeout", "issue": issue})
    logger.error(f"Agent {agent_name} timed out waiting for blocker resolution")
    return {"content": [{"type": "text", "text": "ERROR: Blocker timeout. No response from manager."}]}


# =============================================================================
# Manager Tools - For manager agents to coordinate workers
# =============================================================================


async def spawn_worker(
    name: str,
    prompt: str,
    check: str | None = None,
    model: str = "sonnet",
) -> dict:
    """Spawn a new worker agent.

    Args:
        name: Worker name (will be prefixed with manager name)
        prompt: Task prompt for the worker
        check: Optional check command (defaults to plan default)
        model: Model to use (sonnet, opus, haiku)

    Returns:
        Tool result dict
    """
    run_id, manager_name = get_run_context()

    with get_db(run_id) as db:
        # Create hierarchical name
        worker_name = f"{manager_name}.{name}"

        # Check if agent already exists
        existing = get_agent(db, run_id, worker_name)
        if existing:
            return {"content": [{"type": "text", "text": f"Worker {worker_name} already exists (status: {existing['status']})"}]}

        # Get manager's plan for defaults
        manager = get_agent(db, run_id, manager_name)
        default_check = manager["check_command"] if manager else "true"

        # Insert worker agent
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


async def respond_to_clarification(clarification_id: str, response: str) -> dict:
    """Respond to a worker's clarification request.

    Args:
        clarification_id: ID of the clarification (from get_pending_clarifications)
        response: Response to send to the worker

    Returns:
        Tool result dict
    """
    run_id, manager_name = get_run_context()

    with get_db(run_id) as db:
        insert_response(db, run_id, clarification_id, response)
        logger.info(f"Manager {manager_name} responded to clarification {clarification_id[:8]}")
        return {"content": [{"type": "text", "text": f"Response sent to clarification {clarification_id[:8]}"}]}


async def cancel_worker(name: str) -> dict:
    """Cancel a worker agent.

    Args:
        name: Worker name (can be short name or full hierarchical name)

    Returns:
        Tool result dict
    """
    run_id, manager_name = get_run_context()

    with get_db(run_id) as db:
        # Try hierarchical name first
        worker_name = name if "." in name else f"{manager_name}.{name}"
        agent = get_agent(db, run_id, worker_name)

        if not agent:
            # Try exact name
            agent = get_agent(db, run_id, name)
            worker_name = name

        if not agent:
            return {"content": [{"type": "text", "text": f"Worker not found: {name}"}]}

        if agent["status"] in ("completed", "failed", "cancelled"):
            return {"content": [{"type": "text", "text": f"Worker {worker_name} already in terminal state: {agent['status']}"}]}

        update_agent_status(db, run_id, worker_name, "cancelled", "Cancelled by manager")
        insert_event(db, run_id, manager_name, "progress", {
            "status": f"Cancelled worker {worker_name}",
            "worker": worker_name,
        })

        logger.info(f"Manager {manager_name} cancelled worker {worker_name}")
        return {"content": [{"type": "text", "text": f"Cancelled worker: {worker_name}"}]}


async def get_worker_status(name: str | None = None) -> dict:
    """Get status of workers.

    Args:
        name: Optional specific worker name. If None, returns all workers under this manager.

    Returns:
        Tool result dict with worker status
    """
    run_id, manager_name = get_run_context()

    with get_db(run_id) as db:
        if name:
            # Get specific worker
            worker_name = name if "." in name else f"{manager_name}.{name}"
            agent = get_agent(db, run_id, worker_name)
            if not agent:
                agent = get_agent(db, run_id, name)
            if not agent:
                return {"content": [{"type": "text", "text": f"Worker not found: {name}"}]}

            status_text = f"Worker: {agent['name']}\nStatus: {agent['status']}\nIteration: {agent['iteration']}/{agent['max_iterations']}"
            if agent["error"]:
                status_text += f"\nError: {agent['error'][:200]}"
            return {"content": [{"type": "text", "text": status_text}]}

        else:
            # Get all workers under this manager
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


async def get_pending_clarifications() -> dict:
    """Get all pending clarifications from workers.

    Returns:
        Tool result dict with list of pending clarifications
    """
    run_id, manager_name = get_run_context()

    with get_db(run_id) as db:
        clarifications = db_get_pending_clarifications(db, run_id)

        # Filter to workers under this manager
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


async def mark_plan_complete(summary: str) -> dict:
    """Signal that the manager's plan is complete.

    Args:
        summary: Summary of what was accomplished

    Returns:
        Tool result dict
    """
    run_id, manager_name = get_run_context()

    with get_db(run_id) as db:
        # Check if all workers are done
        all_agents = get_agents(db, run_id)
        workers = [a for a in all_agents if a["parent"] == manager_name]

        pending = [w for w in workers if w["status"] not in ("completed", "failed", "cancelled", "timeout")]
        if pending:
            names = [w["name"].split(".")[-1] for w in pending]
            return {"content": [{"type": "text", "text": f"Cannot complete: workers still running: {names}"}]}

        # Mark manager as completed
        update_agent_status(db, run_id, manager_name, "completed")
        insert_event(db, run_id, manager_name, "done", {"summary": summary})

        failed_workers = [w["name"].split(".")[-1] for w in workers if w["status"] == "failed"]
        completed_workers = [w["name"].split(".")[-1] for w in workers if w["status"] == "completed"]

        result = f"Plan complete. Completed workers: {completed_workers}"
        if failed_workers:
            result += f". Failed workers: {failed_workers}"

        logger.info(f"Manager {manager_name} completed: {summary}")
        return {"content": [{"type": "text", "text": result}]}


# Tool definitions for SDK integration
WORKER_TOOL_DEFINITIONS = [
    {
        "name": "mark_complete",
        "description": "Signal task completion. Runs check command automatically.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Summary of work completed"},
            },
            "required": ["summary"],
        },
    },
    {
        "name": "request_clarification",
        "description": "Ask manager for guidance. BLOCKS until response received.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Question to ask manager"},
                "escalate_to": {
                    "type": "string",
                    "enum": ["parent", "human", "auto"],
                    "description": "Who to escalate to (default: auto)",
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "report_progress",
        "description": "Report progress update. Use milestone param for named checkpoints.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Current status"},
                "milestone": {"type": "string", "description": "Optional milestone name"},
            },
            "required": ["status"],
        },
    },
    {
        "name": "report_blocker",
        "description": "Report blocking issue. BLOCKS until manager responds with guidance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "issue": {"type": "string", "description": "Description of the blocking issue"},
            },
            "required": ["issue"],
        },
    },
]

MANAGER_TOOL_DEFINITIONS = [
    {
        "name": "spawn_worker",
        "description": "Spawn a new worker agent to execute a subtask.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Worker name (will be prefixed with manager name)"},
                "prompt": {"type": "string", "description": "Task prompt for the worker"},
                "check": {"type": "string", "description": "Optional check command"},
                "model": {"type": "string", "enum": ["sonnet", "opus", "haiku"], "description": "Model to use"},
            },
            "required": ["name", "prompt"],
        },
    },
    {
        "name": "respond_to_clarification",
        "description": "Respond to a worker's clarification request.",
        "input_schema": {
            "type": "object",
            "properties": {
                "clarification_id": {"type": "string", "description": "ID from get_pending_clarifications"},
                "response": {"type": "string", "description": "Response to send to the worker"},
            },
            "required": ["clarification_id", "response"],
        },
    },
    {
        "name": "cancel_worker",
        "description": "Cancel a running worker agent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Worker name to cancel"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_worker_status",
        "description": "Get status of workers. If no name given, returns all workers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Optional specific worker name"},
            },
        },
    },
    {
        "name": "get_pending_clarifications",
        "description": "Get all pending clarification requests from workers.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "mark_plan_complete",
        "description": "Signal that the manager's plan is complete. All workers must be done first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Summary of what was accomplished"},
            },
            "required": ["summary"],
        },
    },
]

# Combined for backwards compatibility
TOOL_DEFINITIONS = WORKER_TOOL_DEFINITIONS


async def handle_tool_call(tool_name: str, args: dict) -> dict:
    """Handle a coordination tool call.

    Args:
        tool_name: Name of the tool
        args: Tool arguments

    Returns:
        Tool result dict
    """
    # Worker tools
    if tool_name == "mark_complete":
        return await mark_complete(args["summary"])
    elif tool_name == "request_clarification":
        return await request_clarification(
            args["question"],
            args.get("escalate_to", "auto"),
        )
    elif tool_name == "report_progress":
        return await report_progress(
            args["status"],
            args.get("milestone"),
        )
    elif tool_name == "report_blocker":
        return await report_blocker(args["issue"])

    # Manager tools
    elif tool_name == "spawn_worker":
        return await spawn_worker(
            args["name"],
            args["prompt"],
            args.get("check"),
            args.get("model", "sonnet"),
        )
    elif tool_name == "respond_to_clarification":
        return await respond_to_clarification(
            args["clarification_id"],
            args["response"],
        )
    elif tool_name == "cancel_worker":
        return await cancel_worker(args["name"])
    elif tool_name == "get_worker_status":
        return await get_worker_status(args.get("name"))
    elif tool_name == "get_pending_clarifications":
        return await get_pending_clarifications()
    elif tool_name == "mark_plan_complete":
        return await mark_plan_complete(args["summary"])

    else:
        return {"content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}]}
