"""Agent execution for claude-swarm.

Uses the Claude Agent SDK for native execution with MCP tools
for coordination between agents.
"""

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
)

from swarm.tools.factory import create_manager_tools, create_worker_tools
from swarm.storage.db import (
    get_agent,
    insert_event,
    open_db,
    update_agent_cost,
    update_agent_iteration,
    update_agent_status,
)
from swarm.storage.paths import ensure_log_file

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
    runtime: str = "claude"

    def tree_path(self) -> str:
        """Get full hierarchy path."""
        if self.parent and not self.name.startswith(f"{self.parent}."):
            return f"{self.parent}.{self.name}"
        return self.name


def build_agent_env(config: AgentConfig) -> dict[str, str]:
    """Build environment variables for an agent."""
    env = {
        "SWARM_RUN_ID": config.run_id,
        "SWARM_AGENT_NAME": config.name,
        "SWARM_PARENT_AGENT": config.parent or "",
        "SWARM_TREE_PATH": config.tree_path(),
    }
    if config.env:
        env.update(config.env)
    return env


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


def build_manager_system_prompt(config: AgentConfig) -> str:
    """Build system prompt for manager agent."""
    return f"""You are a manager agent coordinating worker agents.

Task: {config.prompt}

Your tools:
- spawn_worker: Create new workers to handle subtasks
- get_worker_status: Check worker progress
- get_pending_clarifications: See worker questions
- respond_to_clarification: Answer worker questions
- cancel_worker: Stop a worker
- mark_plan_complete: Signal when done (all workers must be complete first)

Orchestrate the work, respond to clarifications, and call mark_plan_complete when finished.

{config.shared_context}
"""


async def run_worker(config: AgentConfig) -> dict:
    """Run a worker agent using the Claude Agent SDK."""
    db = open_db(config.run_id)

    try:
        agent_env = build_agent_env(config)

        update_agent_status(db, config.run_id, config.name, "running")
        insert_event(db, config.run_id, config.name, "started", {"prompt": config.prompt[:200]})

        worker_tools = create_worker_tools(
            config.run_id,
            config.name,
            parent=config.parent or "",
            tree_path=config.tree_path(),
        )
        server = create_sdk_mcp_server("swarm", "1.0.0", worker_tools)

        options = ClaudeAgentOptions(
            cwd=str(config.worktree),
            env=agent_env,
            mcp_servers={"swarm": server},
            allowed_tools=[
                "Read", "Write", "Edit", "Bash", "Glob", "Grep",
                "mcp__swarm__mark_complete",
                "mcp__swarm__request_clarification",
                "mcp__swarm__report_progress",
                "mcp__swarm__report_blocker",
            ],
            model=config.model,
            max_turns=config.max_iterations,
            permission_mode="bypassPermissions",
            system_prompt=build_system_prompt(config),
        )

        logger.info(f"Starting worker {config.name} in {config.worktree}")
        log_path = ensure_log_file(config.run_id, config.name)

        session_id = None
        total_cost = 0.0
        iteration = 0

        async with ClaudeSDKClient(options=options) as client:
            await client.query(f"Execute the task now. When done, call mark_complete with a summary.\n\nTask: {config.prompt}")

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    iteration += 1
                    update_agent_iteration(db, config.run_id, config.name, iteration)

                    with open(log_path, "a") as f:
                        for block in message.content or []:
                            if isinstance(block, TextBlock):
                                f.write(block.text + "\n")

                if isinstance(message, ResultMessage):
                    session_id = message.session_id
                    total_cost = message.total_cost_usd or 0.0
                    break

        update_agent_cost(db, config.run_id, config.name, total_cost)

        if total_cost > config.max_cost_usd:
            logger.warning(f"Worker {config.name} exceeded cost budget (${total_cost:.4f} > ${config.max_cost_usd:.2f})")
            update_agent_status(db, config.run_id, config.name, "cost_exceeded", f"Cost exceeded: ${total_cost:.4f}")
            insert_event(db, config.run_id, config.name, "error", {"error": "cost_exceeded", "cost": total_cost, "budget": config.max_cost_usd})
            return {"success": False, "status": "cost_exceeded", "cost": total_cost, "error": "cost_exceeded"}

        agent = get_agent(db, config.run_id, config.name)
        final_status = agent["status"] if agent else "unknown"

        if final_status == "completed":
            logger.info(f"Worker {config.name} completed (cost: ${total_cost:.4f})")
            return {"success": True, "status": "completed", "cost": total_cost, "session_id": session_id}
        elif final_status in ("failed", "timeout", "cancelled", "cost_exceeded"):
            logger.warning(f"Worker {config.name} ended with status: {final_status}")
            return {"success": False, "status": final_status, "cost": total_cost}
        else:
            update_agent_status(db, config.run_id, config.name, "timeout", "Max iterations without completion")
            logger.warning(f"Worker {config.name} timed out")
            return {"success": False, "status": "timeout", "cost": total_cost}

    except Exception as e:
        logger.error(f"Worker {config.name} failed: {e}")
        update_agent_status(db, config.run_id, config.name, "failed", str(e))
        insert_event(db, config.run_id, config.name, "error", {"error": str(e)})
        return {"success": False, "status": "failed", "error": str(e)}

    finally:
        db.close()


async def run_worker_mock(config: AgentConfig) -> dict:
    """Mock worker for testing without the Claude SDK."""
    db = open_db(config.run_id)

    try:
        update_agent_status(db, config.run_id, config.name, "running")
        insert_event(db, config.run_id, config.name, "started", {"prompt": config.prompt[:200]})

        await asyncio.sleep(0.5)

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


async def run_manager(config: AgentConfig) -> dict:
    """Run a manager agent using the Claude Agent SDK."""
    db = open_db(config.run_id)

    try:
        agent_env = build_agent_env(config)

        update_agent_status(db, config.run_id, config.name, "running")
        insert_event(db, config.run_id, config.name, "started", {"prompt": config.prompt[:200]})

        manager_tools = create_manager_tools(config.run_id, config.name)
        server = create_sdk_mcp_server("swarm", "1.0.0", manager_tools)

        options = ClaudeAgentOptions(
            cwd=str(config.worktree),
            env=agent_env,
            mcp_servers={"swarm": server},
            allowed_tools=[
                "Read", "Write", "Edit", "Bash", "Glob", "Grep",
                "mcp__swarm__spawn_worker",
                "mcp__swarm__respond_to_clarification",
                "mcp__swarm__cancel_worker",
                "mcp__swarm__get_worker_status",
                "mcp__swarm__get_pending_clarifications",
                "mcp__swarm__mark_plan_complete",
            ],
            model=config.model,
            max_turns=config.max_iterations,
            permission_mode="bypassPermissions",
            system_prompt=build_manager_system_prompt(config),
        )

        logger.info(f"Starting manager {config.name} in {config.worktree}")
        log_path = ensure_log_file(config.run_id, config.name)

        session_id = None
        total_cost = 0.0
        iteration = 0

        async with ClaudeSDKClient(options=options) as client:
            await client.query(f"Execute the task. Spawn workers as needed. When all work is done, call mark_plan_complete.\n\nTask: {config.prompt}")

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    iteration += 1
                    update_agent_iteration(db, config.run_id, config.name, iteration)

                    with open(log_path, "a") as f:
                        for block in message.content or []:
                            if isinstance(block, TextBlock):
                                f.write(block.text + "\n")

                if isinstance(message, ResultMessage):
                    session_id = message.session_id
                    total_cost = message.total_cost_usd or 0.0
                    break

        update_agent_cost(db, config.run_id, config.name, total_cost)

        if total_cost > config.max_cost_usd:
            logger.warning(f"Manager {config.name} exceeded cost budget (${total_cost:.4f} > ${config.max_cost_usd:.2f})")
            update_agent_status(db, config.run_id, config.name, "cost_exceeded", f"Cost exceeded: ${total_cost:.4f}")
            insert_event(db, config.run_id, config.name, "error", {"error": "cost_exceeded", "cost": total_cost, "budget": config.max_cost_usd})
            return {"success": False, "status": "cost_exceeded", "cost": total_cost, "error": "cost_exceeded"}

        agent = get_agent(db, config.run_id, config.name)
        final_status = agent["status"] if agent else "unknown"

        if final_status == "completed":
            logger.info(f"Manager {config.name} completed (cost: ${total_cost:.4f})")
            return {"success": True, "status": "completed", "cost": total_cost, "session_id": session_id}
        else:
            if final_status not in ("failed", "timeout", "cancelled", "cost_exceeded"):
                update_agent_status(db, config.run_id, config.name, "timeout", "Max iterations")
            return {"success": False, "status": final_status, "cost": total_cost}

    except Exception as e:
        logger.error(f"Manager {config.name} failed: {e}")
        update_agent_status(db, config.run_id, config.name, "failed", str(e))
        insert_event(db, config.run_id, config.name, "error", {"error": str(e)})
        return {"success": False, "status": "failed", "error": str(e)}

    finally:
        db.close()


def spawn_worker(config: AgentConfig, use_mock: bool = False) -> asyncio.Task:
    """Spawn a worker agent as an asyncio task."""
    if use_mock:
        return asyncio.create_task(run_worker_mock(config), name=f"worker-{config.name}")
    return asyncio.create_task(run_worker(config), name=f"worker-{config.name}")


def spawn_manager(config: AgentConfig) -> asyncio.Task:
    """Spawn a manager agent as an asyncio task."""
    return asyncio.create_task(run_manager(config), name=f"manager-{config.name}")
