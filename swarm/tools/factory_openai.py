"""OpenAI function_tool wrappers for the coord tool set.

Same underlying implementations (``swarm.tools.worker`` / ``manager``),
different wrapping — bare function_tool decorators so the OpenAI agent
gets plain string returns, no Claude content-block unwrap.
"""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover
    from agents import function_tool
except ImportError as err:  # pragma: no cover
    raise ImportError(
        "swarm.tools.factory_openai requires the openai-agents SDK. "
        "Install with: pip install 'claude-swarm[openai]'"
    ) from err

from swarm.tools import manager, worker


def build_worker_coord_tools(
    run_id: str,
    agent_name: str,
    *,
    parent: str = "",
    tree_path: str = "",
) -> list[Any]:
    """Worker coord tools for an OpenAI agent."""

    @function_tool
    async def mark_complete(summary: str) -> str:
        """Signal task completion; runs check command automatically."""
        return await worker.mark_complete(run_id, agent_name, summary)

    @function_tool
    async def request_clarification(question: str, escalate_to: str = "auto") -> str:
        """Ask manager for guidance. BLOCKS until response."""
        return await worker.request_clarification(
            run_id, agent_name, question, escalate_to,
            parent=parent, tree_path=tree_path,
        )

    @function_tool
    async def report_progress(status: str, milestone: str | None = None) -> str:
        """Report progress update."""
        return await worker.report_progress(run_id, agent_name, status, milestone)

    @function_tool
    async def report_blocker(issue: str) -> str:
        """Report blocking issue. BLOCKS until manager responds."""
        return await worker.report_blocker(
            run_id, agent_name, issue,
            parent=parent, tree_path=tree_path,
        )

    return [mark_complete, request_clarification, report_progress, report_blocker]


def build_manager_coord_tools(run_id: str, manager_name: str) -> list[Any]:
    """Manager coord tools for an OpenAI agent."""

    @function_tool
    async def spawn_worker(name: str, prompt: str, check: str | None = None, model: str = "sonnet") -> str:
        """Spawn a new worker agent."""
        return await manager.spawn_worker(run_id, manager_name, name, prompt, check, model)

    @function_tool
    async def respond_to_clarification(clarification_id: str, response: str) -> str:
        """Respond to a worker's clarification request."""
        return await manager.respond_to_clarification(run_id, manager_name, clarification_id, response)

    @function_tool
    async def cancel_worker(name: str) -> str:
        """Cancel a worker agent."""
        return await manager.cancel_worker(run_id, manager_name, name)

    @function_tool
    async def get_worker_status(name: str | None = None) -> str:
        """Get status of workers (all, or one by name)."""
        return await manager.get_worker_status(run_id, manager_name, name)

    @function_tool
    async def get_pending_clarifications() -> str:
        """List pending clarifications from this manager's workers."""
        return await manager.get_pending_clarifications(run_id, manager_name)

    @function_tool
    async def mark_plan_complete(summary: str) -> str:
        """Signal that this manager's plan is complete."""
        return await manager.mark_plan_complete(run_id, manager_name, summary)

    return [
        spawn_worker,
        respond_to_clarification,
        cancel_worker,
        get_worker_status,
        get_pending_clarifications,
        mark_plan_complete,
    ]
