"""Agent execution for claude-swarm.

This module handles running worker and manager agents. Since the Claude Agent SDK
may not be available, we provide a subprocess-based implementation that runs
the `claude` CLI command.
"""

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from swarm.db import (
    get_agent,
    get_pending_clarifications,
    get_recent_events,
    insert_event,
    insert_response,
    open_db,
    update_agent_cost,
    update_agent_iteration,
    update_agent_status,
)

logger = logging.getLogger("swarm.executor")


@dataclass
class AgentConfig:
    """Configuration for running an agent."""

    name: str
    run_id: str
    prompt: str
    worktree: Path
    check_command: str = "true"
    model: str = "sonnet"
    max_iterations: int = 30
    max_cost_usd: float = 5.0
    parent: str | None = None
    env: dict | None = None
    shared_context: str = ""

    def tree_path(self) -> str:
        """Get full hierarchy path."""
        if self.parent:
            return f"{self.parent}.{self.name}"
        return self.name


def build_system_prompt(config: AgentConfig) -> str:
    """Build system prompt for worker agent."""
    return f"""You are an autonomous coding agent working on a specific task.

Task: {config.prompt}

Check command: {config.check_command}

When you have completed the task:
1. Run the check command to verify your work
2. If the check passes, your task is complete
3. If the check fails, fix the issues and try again

Important:
- Focus only on the assigned task
- Commit your changes frequently
- If you encounter a blocker, describe it clearly

{config.shared_context}
"""


async def run_worker_subprocess(config: AgentConfig) -> dict:
    """Run a worker agent via subprocess.

    This is a fallback implementation that runs the `claude` CLI.
    In production, this would use the Claude Agent SDK.

    Args:
        config: Agent configuration

    Returns:
        Result dict with success status and details
    """
    db = open_db(config.run_id)

    try:
        # Set up environment
        env = os.environ.copy()
        env.update({
            "SWARM_RUN_ID": config.run_id,
            "SWARM_AGENT_NAME": config.name,
            "SWARM_PARENT_AGENT": config.parent or "",
            "SWARM_TREE_PATH": config.tree_path(),
        })
        if config.env:
            env.update(config.env)

        # Update status to running
        update_agent_status(db, config.run_id, config.name, "running")
        insert_event(db, config.run_id, config.name, "started", {"prompt": config.prompt[:200]})

        # Build the prompt
        system_prompt = build_system_prompt(config)
        full_prompt = f"{system_prompt}\n\nNow execute the task."

        # Run claude CLI
        # Note: In production, this would use the SDK's query() function
        cmd = [
            "claude",
            "--print",
            "--dangerously-skip-permissions",
            "--model", config.model,
            "-p", full_prompt,
        ]

        logger.info(f"Starting worker {config.name} in {config.worktree}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(config.worktree),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        # Log output
        log_path = Path(f".swarm/runs/{config.run_id}/logs/{config.name}.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(stdout.decode())
            if stderr:
                f.write(f"\nSTDERR:\n{stderr.decode()}")

        # Check result
        # Note: Subprocess mode cannot track actual cost - CLI doesn't output cost data
        # Use --sdk flag for accurate cost tracking
        update_agent_cost(db, config.run_id, config.name, 0.0)

        if process.returncode == 0:
            # Run check command
            check_result = subprocess.run(
                config.check_command,
                shell=True,
                cwd=str(config.worktree),
                capture_output=True,
                text=True,
            )

            if check_result.returncode == 0:
                update_agent_status(db, config.run_id, config.name, "completed")
                insert_event(db, config.run_id, config.name, "done", {"summary": "Task completed"})
                return {"success": True, "status": "completed", "cost": 0.0}
            else:
                update_agent_status(
                    db,
                    config.run_id,
                    config.name,
                    "failed",
                    f"Check failed: {check_result.stderr}",
                )
                insert_event(db, config.run_id, config.name, "error", {"error": "Check failed"})
                return {"success": False, "status": "failed", "error": "Check failed", "cost": 0.0}
        else:
            update_agent_status(
                db,
                config.run_id,
                config.name,
                "failed",
                stderr.decode()[:500],
            )
            insert_event(db, config.run_id, config.name, "error", {"error": stderr.decode()[:200]})
            return {"success": False, "status": "failed", "error": stderr.decode()[:500], "cost": 0.0}

    except Exception as e:
        logger.error(f"Worker {config.name} failed: {e}")
        update_agent_status(db, config.run_id, config.name, "failed", str(e))
        insert_event(db, config.run_id, config.name, "error", {"error": str(e)})
        return {"success": False, "status": "failed", "error": str(e)}

    finally:
        db.close()


async def run_worker_mock(config: AgentConfig) -> dict:
    """Mock worker for testing without the Claude CLI.

    Just runs the check command directly.
    """
    db = open_db(config.run_id)

    try:
        update_agent_status(db, config.run_id, config.name, "running")
        insert_event(db, config.run_id, config.name, "started", {"prompt": config.prompt[:200]})

        # Simulate some work
        await asyncio.sleep(0.5)

        # Run check command
        result = subprocess.run(
            config.check_command,
            shell=True,
            cwd=str(config.worktree),
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            update_agent_status(db, config.run_id, config.name, "completed")
            insert_event(db, config.run_id, config.name, "done", {"summary": "Mock task completed"})
            return {"success": True, "status": "completed"}
        else:
            update_agent_status(db, config.run_id, config.name, "failed", result.stderr[:500])
            insert_event(db, config.run_id, config.name, "error", {"error": result.stderr[:200]})
            return {"success": False, "status": "failed", "error": result.stderr[:500]}

    except Exception as e:
        logger.error(f"Mock worker {config.name} failed: {e}")
        update_agent_status(db, config.run_id, config.name, "failed", str(e))
        return {"success": False, "status": "failed", "error": str(e)}

    finally:
        db.close()


async def spawn_worker(config: AgentConfig, use_mock: bool = False, use_sdk: bool = False) -> asyncio.Task:
    """Spawn a worker agent as an asyncio task.

    Args:
        config: Agent configuration
        use_mock: Use mock implementation (for testing)
        use_sdk: Use Claude Agent SDK (preferred)

    Returns:
        asyncio.Task handle
    """
    if use_mock:
        return asyncio.create_task(run_worker_mock(config), name=f"worker-{config.name}")
    elif use_sdk:
        from swarm.executor_sdk import run_worker_sdk
        return asyncio.create_task(run_worker_sdk(config), name=f"worker-sdk-{config.name}")
    else:
        return asyncio.create_task(run_worker_subprocess(config), name=f"worker-{config.name}")


def format_events_for_manager(events: list, clarifications: list) -> str:
    """Format events for injection into manager prompt."""
    lines = []
    if clarifications:
        lines.append("## Pending Clarifications")
        for c in clarifications:
            lines.append(f"- [{c['id'][:8]}] {c['agent']}: {c['question']}")
    if events:
        lines.append("\n## Recent Events")
        for e in events:
            data = json.loads(e["data"]) if e["data"] else {}
            lines.append(f"- [{e['ts']}] {e['agent']}: {e['event_type']}")
    return "\n".join(lines) or "No new events."


async def run_manager_subprocess(config: AgentConfig) -> dict:
    """Run a manager agent with event injection loop.

    This is a simplified implementation. In production, this would use
    ClaudeSDKClient for multi-turn conversations.
    """
    db = open_db(config.run_id)

    try:
        update_agent_status(db, config.run_id, config.name, "running")
        insert_event(db, config.run_id, config.name, "started", {"prompt": config.prompt[:200]})

        iteration = 0
        max_iterations = config.max_iterations

        while iteration < max_iterations:
            iteration += 1
            update_agent_iteration(db, config.run_id, config.name, iteration)

            # Get events and clarifications
            events = get_recent_events(db, config.run_id)
            clarifications = get_pending_clarifications(db, config.run_id)

            # Build prompt with events
            event_summary = format_events_for_manager(events, clarifications)
            prompt = f"""You are a manager agent coordinating workers.

Task: {config.prompt}

{event_summary}

Respond to any pending clarifications or check if workers are done.
If all work is complete, say "MANAGER_COMPLETE".
"""

            # Run claude CLI
            cmd = [
                "claude",
                "--print",
                "--dangerously-skip-permissions",
                "--model", config.model,
                "-p", prompt,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(config.worktree),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()
            output = stdout.decode()

            # Log output
            log_path = Path(f".swarm/runs/{config.run_id}/logs/{config.name}.log")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as f:
                f.write(f"\n--- Iteration {iteration} ---\n")
                f.write(output)

            # Check for completion signal
            if "MANAGER_COMPLETE" in output:
                update_agent_status(db, config.run_id, config.name, "completed")
                insert_event(db, config.run_id, config.name, "done", {"summary": "Manager completed"})
                return {"success": True, "status": "completed"}

            # Parse responses to clarifications from output
            # (simplified - in production would parse structured output)
            for c in clarifications:
                if c["id"][:8] in output:
                    # Extract response (naive implementation)
                    insert_response(db, config.run_id, c["id"], f"Manager response at iteration {iteration}")

            await asyncio.sleep(5)  # Poll interval

        # Max iterations reached
        update_agent_status(db, config.run_id, config.name, "timeout", "Max iterations reached")
        return {"success": False, "status": "timeout", "error": "Max iterations reached"}

    except Exception as e:
        logger.error(f"Manager {config.name} failed: {e}")
        update_agent_status(db, config.run_id, config.name, "failed", str(e))
        return {"success": False, "status": "failed", "error": str(e)}

    finally:
        db.close()


async def spawn_manager(config: AgentConfig, use_sdk: bool = False) -> asyncio.Task:
    """Spawn a manager agent as an asyncio task.

    Args:
        config: Agent configuration
        use_sdk: Use Claude Agent SDK (preferred)

    Returns:
        asyncio.Task handle
    """
    if use_sdk:
        from swarm.executor_sdk import run_manager_sdk
        return asyncio.create_task(run_manager_sdk(config), name=f"manager-sdk-{config.name}")
    else:
        return asyncio.create_task(run_manager_subprocess(config), name=f"manager-{config.name}")
