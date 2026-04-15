"""Live pipeline behavior with the mock adapter."""

import asyncio

import pytest

from swarm.batch.plan import PlanDefaults
from swarm.core.agent import AgentRequest
from swarm.core.coordination import CoordOp
from swarm.core.errors import CoordinationNotSupported
from swarm.core.events import NullSink
from swarm.live.in_memory import InMemoryCoordinationBackend
from swarm.live.pipeline import handoff, pipeline


def test_pipeline_runs_mock_in_cwd(cwd_tmp):
    req = AgentRequest(name="t", prompt="anything", runtime="mock")

    async def go():
        return await pipeline(
            [req],
            event_sink=NullSink(),
            defaults=PlanDefaults(runtime="mock"),
        )

    results = asyncio.run(go())
    assert len(results) == 1
    assert results[0].status == "completed"


def test_handoff_runs_two_steps(cwd_tmp):
    a = AgentRequest(name="a", prompt="x", runtime="mock")
    b = AgentRequest(name="b", prompt="y", runtime="mock")

    async def go():
        return await handoff(
            a, b, event_sink=NullSink(), defaults=PlanDefaults(runtime="mock")
        )

    results = asyncio.run(go())
    assert [r.status for r in results] == ["completed", "completed"]


def test_in_memory_backend_does_not_support_spawn():
    backend = InMemoryCoordinationBackend()
    assert backend.supports(CoordOp.MARK_COMPLETE)
    assert backend.supports(CoordOp.REQUEST_CLARIFICATION)
    assert not backend.supports(CoordOp.SPAWN)
    assert not backend.supports(CoordOp.STATUS)

    async def call_spawn():
        await backend.spawn("r", "p", AgentRequest(name="x", prompt="y"))

    with pytest.raises(CoordinationNotSupported):
        asyncio.run(call_spawn())
