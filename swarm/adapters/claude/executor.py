"""ClaudeExecutor — runs a ResolvedAgent through the Claude Agent SDK.

Takes an immutable (agent, ctx) pair, builds ClaudeAgentOptions from the
agent's capabilities + profile.coord_ops, invokes ClaudeSDKClient, and
returns an ExecutionResult. Emits iteration ticks, log text, and cost
updates through ctx.events; all coordination (mark_complete, clarification,
spawn, ...) flows through ctx.coord via the MCP server in tools.py.
"""

import logging
from typing import ClassVar

from swarm.adapters.claude.builtins import expand_tools
from swarm.adapters.claude.tools import allowed_coord_tool_names, build_coord_server
from swarm.core.agent import ResolvedAgent
from swarm.core.events import CostUpdate, IterationTick, LogText
from swarm.core.execution import Executor, ExecutionResult, RunContext

logger = logging.getLogger("swarm.adapters.claude.executor")


class ClaudeExecutor(Executor):
    runtime: ClassVar[str] = "claude"

    async def run(
        self, agent: ResolvedAgent, ctx: RunContext
    ) -> ExecutionResult:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ClaudeSDKClient,
            ResultMessage,
            TextBlock,
        )

        server = build_coord_server(ctx, agent.name, agent.profile.coord_ops)
        allowed = expand_tools(agent.capabilities) + allowed_coord_tool_names(
            agent.profile.coord_ops
        )

        env = agent.env_dict()
        env.setdefault("SWARM_RUN_ID", ctx.run_id)
        env.setdefault("SWARM_AGENT_NAME", agent.name)

        options = ClaudeAgentOptions(
            cwd=str(ctx.workspace.path),
            env=env,
            mcp_servers={"swarm": server},
            allowed_tools=allowed,
            model=agent.model,
            max_turns=agent.limits.max_iterations,
            permission_mode="bypassPermissions",
            system_prompt=agent.prompt,
        )

        logger.info(
            "Starting Claude agent %s in %s (model=%s)",
            agent.name,
            ctx.workspace.path,
            agent.model,
        )

        total_cost = 0.0
        iteration = 0
        session_id: str | None = None
        final_text_parts: list[str] = []

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(
                    f"Execute the task now. When done, call mark_complete with a summary.\n\nTask: {agent.prompt}"
                )
                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        iteration += 1
                        ctx.events.emit(
                            IterationTick(
                                run_id=ctx.run_id,
                                agent=agent.name,
                                iteration=iteration,
                            )
                        )
                        for block in message.content or []:
                            if isinstance(block, TextBlock):
                                ctx.events.emit(
                                    LogText(
                                        run_id=ctx.run_id,
                                        agent=agent.name,
                                        text=block.text,
                                    )
                                )
                                final_text_parts.append(block.text)
                    elif isinstance(message, ResultMessage):
                        session_id = message.session_id
                        total_cost = message.total_cost_usd or 0.0
                        break
        except Exception as exc:  # noqa: BLE001
            logger.exception("Claude executor raised for %s", agent.name)
            return ExecutionResult(
                status="failed",
                final_text="\n".join(final_text_parts),
                cost_usd=total_cost,
                cost_source="sdk",
                vendor_session_id=session_id,
                error=str(exc),
                iterations=iteration,
            )

        ctx.events.emit(
            CostUpdate(
                run_id=ctx.run_id,
                agent=agent.name,
                cost_usd=total_cost,
                source="sdk",
            )
        )

        if total_cost > agent.limits.max_cost_usd:
            return ExecutionResult(
                status="cost_exceeded",
                final_text="\n".join(final_text_parts),
                cost_usd=total_cost,
                cost_source="sdk",
                vendor_session_id=session_id,
                error=f"Cost ${total_cost:.4f} exceeded budget ${agent.limits.max_cost_usd:.2f}",
                iterations=iteration,
            )

        # The coord backend marks the attempt completed/failed via mark_complete.
        # In batch mode the attempts table is the source of truth; in live mode
        # there's no DB, so we fall back to the InMemoryCoordinationBackend's
        # in-process status (or a safe default).
        attempt_status = _read_attempt_status(ctx, agent.name)

        if attempt_status == "completed":
            status = "completed"
            error = None
        elif attempt_status in ("failed", "timeout", "cancelled", "cost_exceeded"):
            status = attempt_status
            error = None
        else:
            status = "timeout"
            error = "Max iterations without completion"

        return ExecutionResult(
            status=status,  # type: ignore[arg-type]
            final_text="\n".join(final_text_parts),
            cost_usd=total_cost,
            cost_source="sdk",
            vendor_session_id=session_id,
            error=error,
            iterations=iteration,
        )


def _read_attempt_status(ctx: RunContext, agent_name: str) -> str | None:
    """Read the attempt status from the batch DB if available.

    Returns None when the DB doesn't exist or isn't initialized (live mode).
    """
    try:
        from swarm.batch.sqlite import get_db, latest_attempt

        with get_db(ctx.run_id) as db:
            attempt = latest_attempt(db, ctx.run_id, agent_name)
        return attempt["status"] if attempt else None
    except Exception:  # noqa: BLE001
        pass

    if hasattr(ctx.coord, "get_status"):
        return ctx.coord.get_status(ctx.run_id, agent_name)
    return None
