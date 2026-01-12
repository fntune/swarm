"""Coordination tools for claude-swarm agents.

These tools are designed to be used with the Claude Agent SDK as in-process MCP tools.
Since the SDK may not be available, we provide stub implementations that can be
called directly from the executor.
"""

import asyncio
import json
import logging
import os
import subprocess
from uuid import uuid4

from swarm.db import (
    consume_response,
    get_agent,
    get_response,
    insert_event,
    open_db,
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


async def mark_complete(summary: str) -> dict:
    """Signal task completion. Runs check command automatically.

    Args:
        summary: Summary of work completed

    Returns:
        Tool result dict with success/failure message
    """
    run_id, agent_name = get_run_context()
    db = open_db(run_id)

    try:
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

    finally:
        db.close()


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
    db = open_db(run_id)

    try:
        clarification_id = uuid4().hex

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
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            response = get_response(db, run_id, clarification_id)
            if response:
                consume_response(db, response["id"])
                update_agent_status(db, run_id, agent_name, "running")
                logger.info(f"Agent {agent_name} received response: {response['response']}")
                return {"content": [{"type": "text", "text": f"Manager response: {response['response']}"}]}

            await asyncio.sleep(2)

        # Timeout
        update_agent_status(db, run_id, agent_name, "timeout", "Clarification timeout")
        insert_event(db, run_id, agent_name, "error", {"error": "Clarification timeout", "question": question})
        logger.error(f"Agent {agent_name} timed out waiting for clarification")
        return {"content": [{"type": "text", "text": "ERROR: Clarification timeout. No response from manager."}]}

    finally:
        db.close()


async def report_progress(status: str, milestone: str | None = None) -> dict:
    """Report progress update.

    Args:
        status: Current status description
        milestone: Optional milestone name (e.g., 'core_impl')

    Returns:
        Tool result dict
    """
    run_id, agent_name = get_run_context()
    db = open_db(run_id)

    try:
        data = {"status": status}
        if milestone:
            data["milestone"] = milestone

        insert_event(db, run_id, agent_name, "progress", data)
        logger.info(f"Agent {agent_name} progress: {status}" + (f" (milestone: {milestone})" if milestone else ""))
        return {"content": [{"type": "text", "text": "Progress recorded."}]}

    finally:
        db.close()


async def report_blocker(issue: str, timeout: int = 300) -> dict:
    """Report blocking issue. BLOCKS until manager responds.

    Args:
        issue: Description of the blocking issue
        timeout: Max seconds to wait for response

    Returns:
        Tool result dict with manager's guidance
    """
    run_id, agent_name = get_run_context()
    db = open_db(run_id)

    try:
        clarification_id = uuid4().hex

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

        # Poll for response (same as request_clarification)
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            response = get_response(db, run_id, clarification_id)
            if response:
                consume_response(db, response["id"])
                update_agent_status(db, run_id, agent_name, "running")
                logger.info(f"Agent {agent_name} received guidance: {response['response']}")
                return {"content": [{"type": "text", "text": f"Manager guidance: {response['response']}"}]}

            await asyncio.sleep(2)

        # Timeout
        update_agent_status(db, run_id, agent_name, "timeout", "Blocker timeout")
        insert_event(db, run_id, agent_name, "error", {"error": "Blocker timeout", "issue": issue})
        logger.error(f"Agent {agent_name} timed out waiting for blocker resolution")
        return {"content": [{"type": "text", "text": "ERROR: Blocker timeout. No response from manager."}]}

    finally:
        db.close()


# Tool definitions for SDK integration
TOOL_DEFINITIONS = [
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


async def handle_tool_call(tool_name: str, args: dict) -> dict:
    """Handle a coordination tool call.

    Args:
        tool_name: Name of the tool
        args: Tool arguments

    Returns:
        Tool result dict
    """
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
    else:
        return {"content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}]}
