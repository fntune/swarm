"""resolve_plan + default-runtime resolution chain."""

import pytest

from swarm.batch.plan import (
    PlanDefaults,
    PlanSpec,
    resolve_default_runtime,
    resolve_plan,
)
from swarm.core.agent import AgentRequest, Limits
from swarm.core.capabilities import Capability
from swarm.core.errors import PlanValidationError


def _plan(*agents, **defaults):
    return PlanSpec(
        name="t",
        agents=tuple(agents),
        defaults=PlanDefaults(**defaults),
    )


def test_default_runtime_fallback_chain_hardcoded(monkeypatch):
    monkeypatch.delenv("SWARM_DEFAULT_RUNTIME", raising=False)
    assert resolve_default_runtime(PlanDefaults()) == "claude"


def test_default_runtime_env_override(monkeypatch):
    monkeypatch.setenv("SWARM_DEFAULT_RUNTIME", "openai")
    assert resolve_default_runtime(PlanDefaults()) == "openai"


def test_default_runtime_invalid_env_raises(monkeypatch):
    monkeypatch.setenv("SWARM_DEFAULT_RUNTIME", "bogus")
    with pytest.raises(PlanValidationError):
        resolve_default_runtime(PlanDefaults())


def test_default_runtime_plan_default_wins_over_env(monkeypatch):
    monkeypatch.setenv("SWARM_DEFAULT_RUNTIME", "openai")
    assert resolve_default_runtime(PlanDefaults(runtime="mock")) == "mock"


def test_resolve_plan_reviewer_keeps_readonly_caps():
    plan = _plan(AgentRequest(name="r", prompt="x", profile="reviewer"))
    resolved = resolve_plan(plan)
    assert resolved[0].profile.name == "reviewer"
    assert Capability.FILE_WRITE not in resolved[0].capabilities
    assert Capability.SHELL in resolved[0].capabilities


def test_resolve_plan_unknown_profile_raises():
    plan = _plan(AgentRequest(name="x", prompt="x", profile="nonsense"))
    with pytest.raises(PlanValidationError):
        resolve_plan(plan)


def test_resolve_plan_unknown_dep_raises():
    plan = _plan(AgentRequest(name="x", prompt="x", depends_on=("missing",)))
    with pytest.raises(PlanValidationError):
        resolve_plan(plan)


def test_resolve_plan_duplicate_name_raises():
    plan = _plan(
        AgentRequest(name="dup", prompt="x"),
        AgentRequest(name="dup", prompt="y"),
    )
    with pytest.raises(PlanValidationError):
        resolve_plan(plan)


def test_resolve_agent_carries_retry_policy():
    plan = _plan(
        AgentRequest(name="a", prompt="x", on_failure="retry", retry_count=5)
    )
    resolved = resolve_plan(plan)
    assert resolved[0].on_failure == "retry"
    assert resolved[0].retry_count == 5


def test_resolve_agent_inherits_defaults():
    plan = _plan(
        AgentRequest(name="a", prompt="x"),
        on_failure="stop",
        retry_count=7,
        runtime="mock",
    )
    resolved = resolve_plan(plan)
    assert resolved[0].on_failure == "stop"
    assert resolved[0].retry_count == 7
    assert resolved[0].runtime == "mock"


def test_resolve_agent_limits_override():
    plan = _plan(
        AgentRequest(
            name="a", prompt="x", limits=Limits(max_iterations=99, max_cost_usd=2.5)
        )
    )
    resolved = resolve_plan(plan)
    assert resolved[0].limits.max_iterations == 99
    assert resolved[0].limits.max_cost_usd == 2.5
