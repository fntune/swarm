"""SDK-based agent execution for claude-swarm.

Uses the Claude Agent SDK for native execution with custom MCP tools
for coordination between agents.
"""

import asyncio
import logging
import os
import subprocess
from pathlib import Path

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    tool,
    create_sdk_mcp_server,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

from swarm.db import (
    consume_response,
    get_agent,
    get_agents,
    get_pending_clarifications as db_get_pending_clarifications,
    get_response,
    insert_agent,
    insert_event,
    insert_response,
    open_db,
    update_agent_cost,
    update_agent_iteration,
    update_agent_status,
)
from swarm.executor import AgentConfig, build_system_prompt

logger = logging.getLogger("swarm.executor_sdk")


def create_worker_tools(run_id: str, agent_name: str):
    """Create worker coordination tools as SDK MCP tools.

    Args:
        run_id: Current run ID
        agent_name: Name of the agent

    Returns:
        List of tool functions decorated with @tool
    """

    @tool("mark_complete", "Signal task completion. Runs check command automatically.", {"summary": str})
    async def mark_complete(args: dict) -> dict:
        db = open_db(run_id)
        try:
            agent = get_agent(db, run_id, agent_name)
            if not agent:
                return {"content": [{"type": "text", "text": f"ERROR: Agent {agent_name} not found"}], "is_error": True}

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
                insert_event(db, run_id, agent_name, "done", {"summary": args["summary"]})
                logger.info(f"Agent {agent_name} completed successfully")
                return {"content": [{"type": "text", "text": "Task completed successfully. Check passed."}]}
            else:
                output = f"{result.stdout}\n{result.stderr}".strip()
                logger.warning(f"Check failed for {agent_name}: {output[:200]}")
                # Set status to failed and emit error event (parity with subprocess)
                update_agent_status(db, run_id, agent_name, "failed", f"Check failed: {output[:100]}")
                insert_event(db, run_id, agent_name, "error", {"error": f"Check failed: {output[:200]}"})
                return {"content": [{"type": "text", "text": f"Check failed. Task marked as failed.\n\nOutput:\n{output}"}], "is_error": True}
        finally:
            db.close()

    @tool("request_clarification", "Ask manager for guidance. BLOCKS until response.",
          {"question": str, "escalate_to": str})
    async def request_clarification(args: dict) -> dict:
        from uuid import uuid4
        db = open_db(run_id)
        try:
            clarification_id = uuid4().hex
            question = args["question"]
            escalate_to = args.get("escalate_to", "auto")

            insert_event(db, run_id, agent_name, "clarification", {
                "question": question,
                "escalate_to": escalate_to,
                "parent_agent": os.environ.get("SWARM_PARENT_AGENT", ""),
                "tree_path": os.environ.get("SWARM_TREE_PATH", ""),
                "clarification_id": clarification_id,
            })
            update_agent_status(db, run_id, agent_name, "blocked")
            logger.info(f"Agent {agent_name} blocked on clarification: {question}")

            # Poll for response (max 5 minutes)
            timeout = 300
            deadline = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < deadline:
                response = get_response(db, run_id, clarification_id)
                if response:
                    consume_response(db, response["id"])
                    update_agent_status(db, run_id, agent_name, "running")
                    logger.info(f"Agent {agent_name} received response")
                    return {"content": [{"type": "text", "text": f"Manager response: {response['response']}"}]}
                await asyncio.sleep(2)

            update_agent_status(db, run_id, agent_name, "timeout", "Clarification timeout")
            insert_event(db, run_id, agent_name, "error", {"error": "Clarification timeout"})
            return {"content": [{"type": "text", "text": "ERROR: Clarification timeout."}], "is_error": True}
        finally:
            db.close()

    @tool("report_progress", "Report progress update.", {"status": str, "milestone": str})
    async def report_progress(args: dict) -> dict:
        db = open_db(run_id)
        try:
            data = {"status": args["status"]}
            if args.get("milestone"):
                data["milestone"] = args["milestone"]
            insert_event(db, run_id, agent_name, "progress", data)
            logger.info(f"Agent {agent_name} progress: {args['status']}")
            return {"content": [{"type": "text", "text": "Progress recorded."}]}
        finally:
            db.close()

    @tool("report_blocker", "Report blocking issue. BLOCKS until resolved.", {"issue": str})
    async def report_blocker(args: dict) -> dict:
        from uuid import uuid4
        db = open_db(run_id)
        try:
            clarification_id = uuid4().hex
            issue = args["issue"]

            insert_event(db, run_id, agent_name, "blocker", {
                "question": issue,
                "escalate_to": "parent",
                "clarification_id": clarification_id,
            })
            update_agent_status(db, run_id, agent_name, "blocked")
            logger.info(f"Agent {agent_name} blocked: {issue}")

            # Poll for response
            timeout = 300
            deadline = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < deadline:
                response = get_response(db, run_id, clarification_id)
                if response:
                    consume_response(db, response["id"])
                    update_agent_status(db, run_id, agent_name, "running")
                    return {"content": [{"type": "text", "text": f"Manager guidance: {response['response']}"}]}
                await asyncio.sleep(2)

            update_agent_status(db, run_id, agent_name, "timeout", "Blocker timeout")
            return {"content": [{"type": "text", "text": "ERROR: Blocker timeout."}], "is_error": True}
        finally:
            db.close()

    return [mark_complete, request_clarification, report_progress, report_blocker]


def create_manager_tools(run_id: str, manager_name: str):
    """Create manager coordination tools as SDK MCP tools.

    Args:
        run_id: Current run ID
        manager_name: Name of the manager agent

    Returns:
        List of tool functions decorated with @tool
    """

    @tool("spawn_worker", "Spawn a new worker agent.", {"name": str, "prompt": str, "check": str, "model": str})
    async def spawn_worker(args: dict) -> dict:
        db = open_db(run_id)
        try:
            worker_name = f"{manager_name}.{args['name']}"
            existing = get_agent(db, run_id, worker_name)
            if existing:
                return {"content": [{"type": "text", "text": f"Worker {worker_name} already exists (status: {existing['status']})"}]}

            manager = get_agent(db, run_id, manager_name)
            default_check = manager["check_command"] if manager else "true"

            insert_agent(
                db, run_id, worker_name, args["prompt"],
                agent_type="worker",
                check_command=args.get("check") or default_check,
                model=args.get("model", "sonnet"),
                parent=manager_name,
            )
            insert_event(db, run_id, manager_name, "progress", {"status": f"Spawned {worker_name}"})
            logger.info(f"Manager {manager_name} spawned worker {worker_name}")
            return {"content": [{"type": "text", "text": f"Spawned worker: {worker_name}"}]}
        finally:
            db.close()

    @tool("respond_to_clarification", "Respond to worker's clarification.", {"clarification_id": str, "response": str})
    async def respond_to_clarification(args: dict) -> dict:
        db = open_db(run_id)
        try:
            insert_response(db, run_id, args["clarification_id"], args["response"])
            logger.info(f"Manager responded to clarification {args['clarification_id'][:8]}")
            return {"content": [{"type": "text", "text": "Response sent."}]}
        finally:
            db.close()

    @tool("cancel_worker", "Cancel a worker agent.", {"name": str})
    async def cancel_worker(args: dict) -> dict:
        db = open_db(run_id)
        try:
            worker_name = args["name"] if "." in args["name"] else f"{manager_name}.{args['name']}"
            agent = get_agent(db, run_id, worker_name) or get_agent(db, run_id, args["name"])
            if not agent:
                return {"content": [{"type": "text", "text": f"Worker not found: {args['name']}"}], "is_error": True}
            if agent["status"] in ("completed", "failed", "cancelled"):
                return {"content": [{"type": "text", "text": f"Worker already in terminal state: {agent['status']}"}]}
            update_agent_status(db, run_id, agent["name"], "cancelled", "Cancelled by manager")
            return {"content": [{"type": "text", "text": f"Cancelled: {agent['name']}"}]}
        finally:
            db.close()

    @tool("get_worker_status", "Get status of workers.", {"name": str})
    async def get_worker_status(args: dict) -> dict:
        db = open_db(run_id)
        try:
            if args.get("name"):
                worker_name = args["name"] if "." in args["name"] else f"{manager_name}.{args['name']}"
                agent = get_agent(db, run_id, worker_name) or get_agent(db, run_id, args["name"])
                if not agent:
                    return {"content": [{"type": "text", "text": f"Worker not found: {args['name']}"}]}
                return {"content": [{"type": "text", "text": f"{agent['name']}: {agent['status']} ({agent['iteration']}/{agent['max_iterations']})"}]}
            else:
                all_agents = get_agents(db, run_id)
                workers = [a for a in all_agents if a["parent"] == manager_name]
                if not workers:
                    return {"content": [{"type": "text", "text": "No workers spawned."}]}
                lines = [f"  {w['name'].split('.')[-1]}: {w['status']}" for w in workers]
                return {"content": [{"type": "text", "text": "Workers:\n" + "\n".join(lines)}]}
        finally:
            db.close()

    @tool("get_pending_clarifications", "Get pending clarifications from workers.", {})
    async def get_pending_clarifications(args: dict) -> dict:
        db = open_db(run_id)
        try:
            clarifications = db_get_pending_clarifications(db, run_id)
            my_clars = [c for c in clarifications if c["agent"].startswith(f"{manager_name}.")]
            if not my_clars:
                return {"content": [{"type": "text", "text": "No pending clarifications."}]}
            lines = [f"  [{c['id'][:8]}] {c['agent'].split('.')[-1]}: {c['question']}" for c in my_clars]
            return {"content": [{"type": "text", "text": "Pending:\n" + "\n".join(lines)}]}
        finally:
            db.close()

    @tool("mark_plan_complete", "Signal plan completion.", {"summary": str})
    async def mark_plan_complete(args: dict) -> dict:
        db = open_db(run_id)
        try:
            all_agents = get_agents(db, run_id)
            workers = [a for a in all_agents if a["parent"] == manager_name]
            pending = [w for w in workers if w["status"] not in ("completed", "failed", "cancelled", "timeout")]
            if pending:
                names = [w["name"].split(".")[-1] for w in pending]
                return {"content": [{"type": "text", "text": f"Cannot complete: workers still running: {names}"}], "is_error": True}

            update_agent_status(db, run_id, manager_name, "completed")
            insert_event(db, run_id, manager_name, "done", {"summary": args["summary"]})
            logger.info(f"Manager {manager_name} completed: {args['summary']}")
            return {"content": [{"type": "text", "text": "Plan marked complete."}]}
        finally:
            db.close()

    return [spawn_worker, respond_to_clarification, cancel_worker, get_worker_status, get_pending_clarifications, mark_plan_complete]


async def run_worker_sdk(config: AgentConfig) -> dict:
    """Run a worker agent using the Claude Agent SDK.

    Args:
        config: Agent configuration

    Returns:
        Result dict with success status and details
    """
    db = open_db(config.run_id)

    try:
        # Build environment (parity with subprocess mode)
        agent_env = {
            "SWARM_RUN_ID": config.run_id,
            "SWARM_AGENT_NAME": config.name,
            "SWARM_PARENT_AGENT": config.parent or "",
            "SWARM_TREE_PATH": config.tree_path(),
        }
        if config.env:
            agent_env.update(config.env)

        # Also set in os.environ for tool access
        os.environ.update(agent_env)

        # Update status
        update_agent_status(db, config.run_id, config.name, "running")
        insert_event(db, config.run_id, config.name, "started", {"prompt": config.prompt[:200]})

        # Create coordination tools
        worker_tools = create_worker_tools(config.run_id, config.name)
        server = create_sdk_mcp_server("swarm", "1.0.0", worker_tools)

        # Build options
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

        logger.info(f"Starting SDK worker {config.name} in {config.worktree}")

        # Log file
        log_path = Path(f".swarm/runs/{config.run_id}/logs/{config.name}.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Run agent
        session_id = None
        total_cost = 0.0
        iteration = 0

        async with ClaudeSDKClient(options=options) as client:
            await client.query(f"Execute the task now. When done, call mark_complete with a summary.\n\nTask: {config.prompt}")

            async for message in client.receive_response():
                # Track iterations
                if isinstance(message, AssistantMessage):
                    iteration += 1
                    update_agent_iteration(db, config.run_id, config.name, iteration)

                    # Log assistant output
                    with open(log_path, "a") as f:
                        for block in message.content or []:
                            if isinstance(block, TextBlock):
                                f.write(block.text + "\n")

                # Capture final result
                if isinstance(message, ResultMessage):
                    session_id = message.session_id
                    total_cost = message.total_cost_usd
                    break

        # Update cost
        update_agent_cost(db, config.run_id, config.name, total_cost)

        # Check per-agent cost budget
        if total_cost > config.max_cost_usd:
            logger.warning(f"Worker {config.name} exceeded cost budget (${total_cost:.4f} > ${config.max_cost_usd:.2f})")
            update_agent_status(db, config.run_id, config.name, "failed", f"Cost exceeded: ${total_cost:.4f}")
            insert_event(db, config.run_id, config.name, "error", {"error": "cost_exceeded", "cost": total_cost, "budget": config.max_cost_usd})
            return {"success": False, "status": "failed", "cost": total_cost, "error": "cost_exceeded"}

        # Check final status
        agent = get_agent(db, config.run_id, config.name)
        final_status = agent["status"] if agent else "unknown"

        if final_status == "completed":
            logger.info(f"Worker {config.name} completed (cost: ${total_cost:.4f})")
            return {"success": True, "status": "completed", "cost": total_cost, "session_id": session_id}
        elif final_status in ("failed", "timeout", "cancelled"):
            logger.warning(f"Worker {config.name} ended with status: {final_status}")
            return {"success": False, "status": final_status, "cost": total_cost}
        else:
            # Agent didn't call mark_complete - treat as timeout
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


async def run_manager_sdk(config: AgentConfig) -> dict:
    """Run a manager agent using the Claude Agent SDK.

    Args:
        config: Agent configuration

    Returns:
        Result dict with success status and details
    """
    db = open_db(config.run_id)

    try:
        # Build environment (parity with subprocess mode)
        agent_env = {
            "SWARM_RUN_ID": config.run_id,
            "SWARM_AGENT_NAME": config.name,
            "SWARM_PARENT_AGENT": config.parent or "",
            "SWARM_TREE_PATH": config.tree_path(),
        }
        if config.env:
            agent_env.update(config.env)

        # Also set in os.environ for tool access
        os.environ.update(agent_env)

        # Update status
        update_agent_status(db, config.run_id, config.name, "running")
        insert_event(db, config.run_id, config.name, "started", {"prompt": config.prompt[:200]})

        # Create manager tools
        manager_tools = create_manager_tools(config.run_id, config.name)
        server = create_sdk_mcp_server("swarm", "1.0.0", manager_tools)

        # Build options
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
            system_prompt=f"""You are a manager agent coordinating worker agents.

Task: {config.prompt}

Your tools:
- spawn_worker: Create new workers to handle subtasks
- get_worker_status: Check worker progress
- get_pending_clarifications: See worker questions
- respond_to_clarification: Answer worker questions
- cancel_worker: Stop a worker
- mark_plan_complete: Signal when done (all workers must be complete first)

Orchestrate the work, respond to clarifications, and call mark_plan_complete when finished.
""",
        )

        logger.info(f"Starting SDK manager {config.name} in {config.worktree}")

        # Log file
        log_path = Path(f".swarm/runs/{config.run_id}/logs/{config.name}.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)

        session_id = None
        total_cost = 0.0
        iteration = 0

        async with ClaudeSDKClient(options=options) as client:
            # Initial prompt
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
                    total_cost = message.total_cost_usd
                    break

        update_agent_cost(db, config.run_id, config.name, total_cost)

        # Check per-agent cost budget
        if total_cost > config.max_cost_usd:
            logger.warning(f"Manager {config.name} exceeded cost budget (${total_cost:.4f} > ${config.max_cost_usd:.2f})")
            update_agent_status(db, config.run_id, config.name, "failed", f"Cost exceeded: ${total_cost:.4f}")
            insert_event(db, config.run_id, config.name, "error", {"error": "cost_exceeded", "cost": total_cost, "budget": config.max_cost_usd})
            return {"success": False, "status": "failed", "cost": total_cost, "error": "cost_exceeded"}

        agent = get_agent(db, config.run_id, config.name)
        final_status = agent["status"] if agent else "unknown"

        if final_status == "completed":
            logger.info(f"Manager {config.name} completed (cost: ${total_cost:.4f})")
            return {"success": True, "status": "completed", "cost": total_cost, "session_id": session_id}
        else:
            if final_status not in ("failed", "timeout", "cancelled"):
                update_agent_status(db, config.run_id, config.name, "timeout", "Max iterations")
            return {"success": False, "status": final_status, "cost": total_cost}

    except Exception as e:
        logger.error(f"Manager {config.name} failed: {e}")
        update_agent_status(db, config.run_id, config.name, "failed", str(e))
        insert_event(db, config.run_id, config.name, "error", {"error": str(e)})
        return {"success": False, "status": "failed", "error": str(e)}

    finally:
        db.close()


async def spawn_worker_sdk(config: AgentConfig) -> asyncio.Task:
    """Spawn a worker agent using SDK as an asyncio task.

    Args:
        config: Agent configuration

    Returns:
        asyncio.Task handle
    """
    return asyncio.create_task(run_worker_sdk(config), name=f"worker-sdk-{config.name}")


async def spawn_manager_sdk(config: AgentConfig) -> asyncio.Task:
    """Spawn a manager agent using SDK as an asyncio task.

    Args:
        config: Agent configuration

    Returns:
        asyncio.Task handle
    """
    return asyncio.create_task(run_manager_sdk(config), name=f"manager-sdk-{config.name}")
