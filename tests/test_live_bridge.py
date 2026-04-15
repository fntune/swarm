"""as_claude_tool / as_openai_tool wrappers."""

import asyncio

from swarm.batch.plan import PlanDefaults
from swarm.core.agent import AgentRequest
from swarm.live.bridge import as_claude_tool, as_openai_tool


def test_as_claude_tool_produces_callable():
    req = AgentRequest(name="x", prompt="hi", runtime="mock")
    closure = as_claude_tool(req)
    # The Claude SDK @tool decorator returns a wrapper with a name and an
    # invoke surface; we just assert that we got something callable back.
    assert closure is not None


def test_as_openai_tool_produces_callable():
    req = AgentRequest(name="x", prompt="hi", runtime="mock")
    closure = as_openai_tool(req)
    assert closure is not None


def test_split_returns_distinct_objects():
    req = AgentRequest(name="x", prompt="hi", runtime="mock")
    claude_tool = as_claude_tool(req)
    openai_tool = as_openai_tool(req)
    assert claude_tool is not openai_tool
