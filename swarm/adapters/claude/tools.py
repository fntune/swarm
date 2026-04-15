"""Claude-SDK MCP coord server.

Wraps the backend-neutral CoordinationBackend into Claude's @tool + SDK MCP
shape. Each profile's coord_ops set controls which tools get exposed.
"""

from typing import Any

from swarm.core.coordination import CoordinationBackend
from swarm.core.events import CoordCall
from swarm.core.execution import RunContext

MCP_SERVER_NAME = "swarm"
MCP_SERVER_VERSION = "1.0.0"

_OP_TO_MCP_NAME: dict[str, str] = {
    "mark_complete": "mcp__swarm__mark_complete",
    "report_progress": "mcp__swarm__report_progress",
    "report_blocker": "mcp__swarm__report_blocker",
    "request_clarification": "mcp__swarm__request_clarification",
    "spawn": "mcp__swarm__spawn_worker",
    "status": "mcp__swarm__get_worker_status",
    "respond": "mcp__swarm__respond_to_clarification",
    "cancel": "mcp__swarm__cancel_worker",
    "pending_clarifications": "mcp__swarm__get_pending_clarifications",
    "mark_plan_complete": "mcp__swarm__mark_plan_complete",
}


def allowed_coord_tool_names(coord_ops: frozenset[str]) -> list[str]:
    return [_OP_TO_MCP_NAME[op] for op in sorted(coord_ops) if op in _OP_TO_MCP_NAME]


def _text_block(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def build_coord_server(
    ctx: RunContext,
    agent_name: str,
    coord_ops: frozenset[str],
):
    """Build an SDK MCP server exposing the selected coord ops for `agent_name`.

    Returns the server object from create_sdk_mcp_server. The caller wires
    it into ClaudeAgentOptions.mcp_servers.
    """
    from claude_agent_sdk import create_sdk_mcp_server, tool

    backend: CoordinationBackend = ctx.coord
    tools: list[Any] = []

    def _emit(op: str, payload: dict) -> None:
        ctx.events.emit(
            CoordCall(run_id=ctx.run_id, agent=agent_name, op=op, payload=payload)
        )

    if "mark_complete" in coord_ops:
        @tool(
            "mark_complete",
            "Signal task completion. Runs the agent's check command automatically.",
            {"summary": str},
        )
        async def mark_complete(args: dict) -> dict:
            summary = args["summary"]
            _emit("mark_complete", {"summary_len": len(summary)})
            result = await backend.mark_complete(ctx.run_id, agent_name, summary)
            return _text_block(result.text)

        tools.append(mark_complete)

    if "report_progress" in coord_ops:
        @tool(
            "report_progress",
            "Report non-blocking progress status.",
            {"status": str, "milestone": str},
        )
        async def report_progress(args: dict) -> dict:
            _emit("report_progress", {"status": args.get("status", "")})
            result = await backend.report_progress(
                ctx.run_id,
                agent_name,
                args.get("status", ""),
                args.get("milestone"),
            )
            return _text_block(result.text)

        tools.append(report_progress)

    if "request_clarification" in coord_ops:
        @tool(
            "request_clarification",
            "Ask the parent for guidance. BLOCKS until a response arrives or times out.",
            {"question": str, "escalate_to": str},
        )
        async def request_clarification(args: dict) -> dict:
            _emit("request_clarification", {"question_len": len(args.get("question", ""))})
            result = await backend.request_clarification(
                ctx.run_id,
                agent_name,
                args["question"],
                args.get("escalate_to", "auto"),
                timeout=300,
            )
            return _text_block(result.text)

        tools.append(request_clarification)

    if "report_blocker" in coord_ops:
        @tool(
            "report_blocker",
            "Report a blocking issue. BLOCKS until resolved or timed out.",
            {"issue": str},
        )
        async def report_blocker(args: dict) -> dict:
            _emit("report_blocker", {"issue_len": len(args.get("issue", ""))})
            result = await backend.report_blocker(
                ctx.run_id, agent_name, args["issue"], timeout=300
            )
            return _text_block(result.text)

        tools.append(report_blocker)

    if "spawn" in coord_ops:
        from swarm.core.agent import AgentRequest

        @tool(
            "spawn_worker",
            "Spawn a child worker agent under this orchestrator.",
            {"name": str, "prompt": str, "check": str, "model": str, "profile": str},
        )
        async def spawn_worker(args: dict) -> dict:
            _emit("spawn", {"name": args.get("name", "")})
            req = AgentRequest(
                name=args["name"],
                prompt=args["prompt"],
                profile=args.get("profile") or None,
                model=args.get("model") or None,
                check=args.get("check") or None,
            )
            result = await backend.spawn(ctx.run_id, agent_name, req)
            return _text_block(result.text)

        tools.append(spawn_worker)

    if "status" in coord_ops:
        @tool(
            "get_worker_status",
            "Get the status of one or all child workers.",
            {"name": str},
        )
        async def get_worker_status(args: dict) -> dict:
            _emit("status", {"name": args.get("name")})
            result = await backend.status(ctx.run_id, agent_name, args.get("name"))
            return _text_block(result.text)

        tools.append(get_worker_status)

    if "respond" in coord_ops:
        @tool(
            "respond_to_clarification",
            "Reply to a worker clarification/blocker event.",
            {"clarification_id": str, "response": str},
        )
        async def respond(args: dict) -> dict:
            _emit("respond", {"id": args.get("clarification_id", "")[:8]})
            result = await backend.respond(
                ctx.run_id,
                agent_name,
                args["clarification_id"],
                args["response"],
            )
            return _text_block(result.text)

        tools.append(respond)

    if "cancel" in coord_ops:
        @tool("cancel_worker", "Cancel a child worker.", {"name": str})
        async def cancel(args: dict) -> dict:
            _emit("cancel", {"name": args.get("name", "")})
            result = await backend.cancel(ctx.run_id, agent_name, args["name"])
            return _text_block(result.text)

        tools.append(cancel)

    if "pending_clarifications" in coord_ops:
        @tool(
            "get_pending_clarifications",
            "List unanswered clarification/blocker requests from children.",
            {},
        )
        async def pending(_: dict) -> dict:
            _emit("pending_clarifications", {})
            result = await backend.pending_clarifications(ctx.run_id, agent_name)
            return _text_block(result.text)

        tools.append(pending)

    if "mark_plan_complete" in coord_ops:
        @tool(
            "mark_plan_complete",
            "Signal that the orchestrator's plan is complete.",
            {"summary": str},
        )
        async def mark_plan_complete(args: dict) -> dict:
            _emit("mark_plan_complete", {"summary_len": len(args.get("summary", ""))})
            result = await backend.mark_plan_complete(
                ctx.run_id, agent_name, args["summary"]
            )
            return _text_block(result.text)

        tools.append(mark_plan_complete)

    return create_sdk_mcp_server(MCP_SERVER_NAME, MCP_SERVER_VERSION, tools)
