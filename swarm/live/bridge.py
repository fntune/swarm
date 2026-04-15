"""Explicit vendor bridges for exposing an AgentRequest as a tool.

Two functions, one per target vendor. No auto-detection, no union return
type — callers pick by importing the right one. Both build a closure that
runs a fresh nested pipeline([req]) when invoked and returns the final
text.
"""

from typing import Any

from swarm.core.agent import AgentRequest
from swarm.live.pipeline import pipeline


def as_claude_tool(request: AgentRequest):
    """Wrap an AgentRequest as a Claude Agent SDK @tool-decorated closure.

    The closure name is `run_<agent_name>`. Returns the final text from
    the nested pipeline run; on failure returns the error string.
    """
    from claude_agent_sdk import tool

    tool_name = f"run_{request.name}"
    description = f"Run the {request.name!r} agent with a custom prompt override."

    @tool(tool_name, description, {"prompt_override": str})
    async def _closure(args: dict) -> dict[str, Any]:
        override = args.get("prompt_override") or request.prompt
        nested = AgentRequest(
            name=request.name,
            prompt=override,
            profile=request.profile,
            runtime=request.runtime,
            model=request.model,
            capabilities=request.capabilities,
            limits=request.limits,
            check=request.check,
            depends_on=request.depends_on,
            env=request.env,
            output_schema=request.output_schema,
            parent=request.parent,
            on_failure=request.on_failure,
            retry_count=request.retry_count,
        )
        results = await pipeline([nested])
        r = results[0]
        text = r.final_text if r.status == "completed" else f"[{r.status}] {r.error or r.final_text}"
        return {"content": [{"type": "text", "text": text}]}

    return _closure


def as_openai_tool(request: AgentRequest):
    """Wrap an AgentRequest as an OpenAI Agents SDK @function_tool closure."""
    from agents import function_tool

    @function_tool
    async def _closure(prompt_override: str = "") -> str:
        override = prompt_override or request.prompt
        nested = AgentRequest(
            name=request.name,
            prompt=override,
            profile=request.profile,
            runtime=request.runtime,
            model=request.model,
            capabilities=request.capabilities,
            limits=request.limits,
            check=request.check,
            depends_on=request.depends_on,
            env=request.env,
            output_schema=request.output_schema,
            parent=request.parent,
            on_failure=request.on_failure,
            retry_count=request.retry_count,
        )
        results = await pipeline([nested])
        r = results[0]
        return r.final_text if r.status == "completed" else f"[{r.status}] {r.error or r.final_text}"

    _closure.__name__ = f"run_{request.name}"
    return _closure
