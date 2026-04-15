"""End-to-end scheduler with stub executors.

Avoids any real SDK calls — registers a custom Executor, then runs short
plans to verify dispatch, cascade-failure, and retry-with-attempts-row
behavior.
"""

import asyncio

import pytest

from swarm.batch.input import build_inline_plan
from swarm.batch.plan import PlanDefaults, PlanSpec, resolve_plan
from swarm.batch.scheduler import run_plan
from swarm.core.agent import AgentRequest
from swarm.core.execution import (
    EXECUTOR_REGISTRY,
    Executor,
    ExecutionResult,
    register,
)
from swarm.workspaces.cwd import CwdProvider


@pytest.fixture
def stub_runtime(monkeypatch):
    """Reset the executor registry to just a stub mock for this test."""
    saved = EXECUTOR_REGISTRY.copy()
    EXECUTOR_REGISTRY.clear()
    try:
        yield
    finally:
        EXECUTOR_REGISTRY.clear()
        EXECUTOR_REGISTRY.update(saved)


def _register_always_ok():
    class OK(Executor):
        runtime = "mock"

        async def run(self, agent, ctx):
            return ExecutionResult(
                status="completed",
                final_text=f"ok {agent.name}",
                cost_usd=0.01,
                cost_source="estimated",
            )

    register(OK())


def _register_flakey(succeed_on: int):
    counter = {"n": 0}

    class Flakey(Executor):
        runtime = "mock"

        async def run(self, agent, ctx):
            counter["n"] += 1
            if counter["n"] < succeed_on:
                return ExecutionResult(
                    status="failed",
                    final_text="",
                    cost_usd=0.01,
                    cost_source="estimated",
                    error=f"flake #{counter['n']}",
                )
            return ExecutionResult(
                status="completed",
                final_text="ok",
                cost_usd=0.02,
                cost_source="estimated",
            )

    register(Flakey())
    return counter


def _register_always_fail():
    class Bad(Executor):
        runtime = "mock"

        async def run(self, agent, ctx):
            return ExecutionResult(
                status="failed",
                final_text="",
                cost_usd=0.0,
                cost_source="estimated",
                error="never works",
            )

    register(Bad())


def test_two_agent_sequential_completes(cwd_tmp, stub_runtime):
    _register_always_ok()
    plan = build_inline_plan(
        ["a: do a", "b: do b"],
        sequential=True,
        defaults=PlanDefaults(runtime="mock"),
    )
    result = asyncio.run(
        run_plan(
            plan,
            resolve_plan(plan),
            base_path=cwd_tmp,
            workspace_provider=CwdProvider(cwd_tmp),
        )
    )
    assert result.success
    assert result.completed == ["a", "b"]
    assert result.failed == []


def test_retry_inserts_new_attempts_until_success(cwd_tmp, stub_runtime):
    counter = _register_flakey(succeed_on=3)
    request = AgentRequest(
        name="r", prompt="hello", on_failure="retry", retry_count=3
    )
    plan = PlanSpec(
        name="retry-test",
        agents=(request,),
        defaults=PlanDefaults(runtime="mock"),
    )
    result = asyncio.run(
        run_plan(
            plan,
            resolve_plan(plan),
            base_path=cwd_tmp,
            workspace_provider=CwdProvider(cwd_tmp),
        )
    )
    assert result.success
    assert counter["n"] == 3

    # Verify three attempts rows persist
    from swarm.batch.sqlite import get_db

    with get_db(result.run_id, cwd_tmp) as db:
        rows = db.execute(
            "SELECT attempt_number, status FROM attempts WHERE node_name='r' ORDER BY attempt_number"
        ).fetchall()
    assert [(r["attempt_number"], r["status"]) for r in rows] == [
        (1, "failed"),
        (2, "failed"),
        (3, "completed"),
    ]


def test_cascade_failure_skips_dependents(cwd_tmp, stub_runtime):
    _register_always_fail()
    plan = PlanSpec(
        name="cascade",
        defaults=PlanDefaults(runtime="mock"),
        agents=(
            AgentRequest(name="a", prompt="x"),
            AgentRequest(name="b", prompt="y", depends_on=("a",)),
            AgentRequest(name="c", prompt="z", depends_on=("b",)),
        ),
    )
    result = asyncio.run(
        run_plan(
            plan,
            resolve_plan(plan),
            base_path=cwd_tmp,
            workspace_provider=CwdProvider(cwd_tmp),
        )
    )
    assert not result.success
    assert "a" in result.failed
    assert "b" in result.failed
    assert "c" in result.failed
