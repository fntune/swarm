"""Tool factory for creating SDK MCP tools."""

from claude_agent_sdk import tool

from swarm.tools import manager, worker


def create_worker_tools(run_id: str, agent_name: str):
    """Create worker coordination tools as SDK MCP tools with captured context."""

    @tool("mark_complete", "Signal task completion. Runs check command automatically.", {"summary": str})
    async def mark_complete(args: dict) -> dict:
        return await worker.mark_complete(run_id, agent_name, args["summary"])

    @tool("request_clarification", "Ask manager for guidance. BLOCKS until response.",
          {"question": str, "escalate_to": str})
    async def request_clarification(args: dict) -> dict:
        return await worker.request_clarification(
            run_id,
            agent_name,
            args["question"],
            args.get("escalate_to", "auto"),
        )

    @tool("report_progress", "Report progress update.", {"status": str, "milestone": str})
    async def report_progress(args: dict) -> dict:
        return await worker.report_progress(run_id, agent_name, args["status"], args.get("milestone"))

    @tool("report_blocker", "Report blocking issue. BLOCKS until resolved.", {"issue": str})
    async def report_blocker(args: dict) -> dict:
        return await worker.report_blocker(run_id, agent_name, args["issue"])

    return [mark_complete, request_clarification, report_progress, report_blocker]


def create_manager_tools(run_id: str, manager_name: str):
    """Create manager coordination tools as SDK MCP tools with captured context."""

    @tool("spawn_worker", "Spawn a new worker agent.", {"name": str, "prompt": str, "check": str, "model": str})
    async def spawn_worker_tool(args: dict) -> dict:
        return await manager.spawn_worker(
            run_id,
            manager_name,
            args["name"],
            args["prompt"],
            args.get("check"),
            args.get("model", "sonnet"),
        )

    @tool("respond_to_clarification", "Respond to worker's clarification.", {"clarification_id": str, "response": str})
    async def respond_to_clarification(args: dict) -> dict:
        return await manager.respond_to_clarification(
            run_id,
            manager_name,
            args["clarification_id"],
            args["response"],
        )

    @tool("cancel_worker", "Cancel a worker agent.", {"name": str})
    async def cancel_worker(args: dict) -> dict:
        return await manager.cancel_worker(run_id, manager_name, args["name"])

    @tool("get_worker_status", "Get status of workers.", {"name": str})
    async def get_worker_status(args: dict) -> dict:
        return await manager.get_worker_status(run_id, manager_name, args.get("name"))

    @tool("get_pending_clarifications", "Get pending clarifications from workers.", {})
    async def get_pending_clarifications(_: dict) -> dict:
        return await manager.get_pending_clarifications(run_id, manager_name)

    @tool("mark_plan_complete", "Signal plan completion.", {"summary": str})
    async def mark_plan_complete(args: dict) -> dict:
        return await manager.mark_plan_complete(run_id, manager_name, args["summary"])

    return [spawn_worker_tool, respond_to_clarification, cancel_worker, get_worker_status, get_pending_clarifications, mark_plan_complete]
