"""OpenAIExecutor — runs a ResolvedAgent through the OpenAI Agents SDK.

Budget enforcement is a soft cap: cost is estimated from a small inline
price table after the run, so the executor returns cost_source='estimated'.
Structured output (ResolvedAgent.output_schema) is supported when the
caller passes a Pydantic-compatible dict schema; otherwise final_output is
stringified.
"""

import logging
from typing import Any, ClassVar

# Force ImportError at module load time if openai-agents isn't installed, so
# `from swarm.adapters import openai` degrades cleanly on a base install
# (the __init__.py's try/except swallows the failure).
import agents  # noqa: F401

from swarm.adapters.openai.code_tools import build_code_tools
from swarm.adapters.openai.tools import build_coord_tools
from swarm.core.agent import ResolvedAgent
from swarm.core.events import CostUpdate, IterationTick, LogText
from swarm.core.execution import Executor, ExecutionResult, RunContext

logger = logging.getLogger("swarm.adapters.openai.executor")


# Rough per-million-token prices (USD) for budget estimation. Unknown models
# fall back to 0.0 and cost_source still reports "estimated".
_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "o4-mini": (1.10, 4.40),
    "o3-mini": (1.10, 4.40),
}


def _estimate_cost(model: str, usage: Any) -> float:
    if usage is None:
        return 0.0
    in_price, out_price = _PRICES.get(model, (0.0, 0.0))
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    return (input_tokens * in_price + output_tokens * out_price) / 1_000_000


class OpenAIExecutor(Executor):
    runtime: ClassVar[str] = "openai"

    async def run(
        self, agent: ResolvedAgent, ctx: RunContext
    ) -> ExecutionResult:
        from agents import Agent, Runner

        coord_tools = build_coord_tools(ctx, agent.name, agent.profile.coord_ops)
        code_tools = build_code_tools(
            workspace_cwd=ctx.workspace.path, capabilities=agent.capabilities
        )
        all_tools = [*code_tools, *coord_tools]

        model = agent.model or "gpt-4.1-mini"

        sdk_agent_kwargs: dict[str, Any] = {
            "name": agent.name,
            "instructions": agent.prompt,
            "tools": all_tools,
            "model": model,
        }
        if agent.output_schema is not None:
            sdk_agent_kwargs["output_type"] = agent.output_schema

        sdk_agent = Agent(**sdk_agent_kwargs)

        logger.info(
            "Starting OpenAI agent %s in %s (model=%s)",
            agent.name,
            ctx.workspace.path,
            model,
        )

        ctx.events.emit(
            LogText(
                run_id=ctx.run_id,
                agent=agent.name,
                text=f"[openai] launching with model={model}, tools={len(all_tools)}",
            )
        )

        try:
            run_result = await Runner.run(
                sdk_agent,
                agent.prompt,
                max_turns=agent.limits.max_iterations,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("OpenAI executor raised for %s", agent.name)
            return ExecutionResult(
                status="failed",
                final_text="",
                cost_usd=0.0,
                cost_source="estimated",
                error=str(exc),
            )

        usage = getattr(run_result, "usage", None)
        cost = _estimate_cost(model, usage)
        iterations = getattr(run_result, "num_turns", None) or 0
        final_output = getattr(run_result, "final_output", None)
        final_text = (
            final_output.model_dump_json() if hasattr(final_output, "model_dump_json")
            else str(final_output)
            if final_output is not None
            else ""
        )

        ctx.events.emit(
            IterationTick(
                run_id=ctx.run_id, agent=agent.name, iteration=int(iterations)
            )
        )
        ctx.events.emit(
            CostUpdate(
                run_id=ctx.run_id,
                agent=agent.name,
                cost_usd=cost,
                source="estimated",
            )
        )
        if final_text:
            ctx.events.emit(
                LogText(run_id=ctx.run_id, agent=agent.name, text=final_text[:4000])
            )

        if cost > agent.limits.max_cost_usd:
            return ExecutionResult(
                status="cost_exceeded",
                final_text=final_text,
                cost_usd=cost,
                cost_source="estimated",
                structured_output=final_output if agent.output_schema else None,
                error=f"Cost ${cost:.4f} exceeded budget ${agent.limits.max_cost_usd:.2f}",
                iterations=int(iterations),
            )

        from swarm.batch.sqlite import get_db, latest_attempt

        with get_db(ctx.run_id) as db:
            attempt = latest_attempt(db, ctx.run_id, agent.name)
        attempt_status = attempt["status"] if attempt else None

        if attempt_status == "completed":
            status = "completed"
            error = None
        elif attempt_status in ("failed", "timeout", "cancelled", "cost_exceeded"):
            status = attempt_status
            error = attempt["error"] if attempt else None
        else:
            # OpenAI agents return final output without needing mark_complete,
            # so treat a clean Runner.run as completed unless the backend says
            # otherwise.
            status = "completed"
            error = None

        return ExecutionResult(
            status=status,  # type: ignore[arg-type]
            final_text=final_text,
            cost_usd=cost,
            cost_source="estimated",
            structured_output=final_output if agent.output_schema else None,
            error=error,
            iterations=int(iterations),
        )
