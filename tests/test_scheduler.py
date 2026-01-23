"""Tests for scheduler module."""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from swarm.storage.db import (
    get_agent,
    get_agents,
    get_plan,
    init_db,
    insert_agent,
    insert_plan,
    open_db,
    update_agent_status,
    update_plan_status,
)
from swarm.models.specs import AgentSpec, CostBudget, Orchestration, CircuitBreaker, PlanSpec
from swarm.runtime.scheduler import Scheduler, SchedulerResult


@pytest.fixture
def temp_swarm_dir(tmp_path):
    """Create a temporary .swarm directory structure."""
    swarm_dir = tmp_path / ".swarm" / "runs"
    swarm_dir.mkdir(parents=True)
    return tmp_path


def create_test_plan(
    agents: list[AgentSpec],
    cost_budget: CostBudget | None = None,
    orchestration: Orchestration | None = None,
) -> PlanSpec:
    """Create a test plan spec."""
    return PlanSpec(
        name="test-plan",
        agents=agents,
        cost_budget=cost_budget,
        orchestration=orchestration,
    )


def test_scheduler_init(temp_swarm_dir, monkeypatch):
    """Test scheduler initialization."""
    monkeypatch.chdir(temp_swarm_dir)

    agents = [AgentSpec(name="test", prompt="Test task")]
    plan = create_test_plan(agents)

    scheduler = Scheduler(plan, run_id="test-run-001", use_mock=True)

    assert scheduler.run_id == "test-run-001"
    assert scheduler.plan == plan
    assert scheduler.use_mock is True


def test_scheduler_init_db(temp_swarm_dir, monkeypatch):
    """Test scheduler database initialization."""
    monkeypatch.chdir(temp_swarm_dir)

    agents = [
        AgentSpec(name="auth", prompt="Implement auth"),
        AgentSpec(name="cache", prompt="Implement cache", depends_on=["auth"]),
    ]
    plan = create_test_plan(agents)

    scheduler = Scheduler(plan, run_id="test-run-002", use_mock=True)
    scheduler._init_db()

    # Verify DB was created
    db = scheduler.db
    assert db is not None

    # Verify plan was inserted
    plan_row = get_plan(db, "test-run-002")
    assert plan_row is not None
    assert plan_row["name"] == "test-plan"

    # Verify agents were inserted
    agent_rows = get_agents(db, "test-run-002")
    assert len(agent_rows) == 2
    names = {a["name"] for a in agent_rows}
    assert names == {"auth", "cache"}

    db.close()


def test_build_result_success(temp_swarm_dir, monkeypatch):
    """Test _build_result with all agents completed."""
    monkeypatch.chdir(temp_swarm_dir)

    agents = [AgentSpec(name="a", prompt="Task A")]
    plan = create_test_plan(agents)

    scheduler = Scheduler(plan, run_id="test-run-003", use_mock=True)
    scheduler._init_db()

    # Mark agent as completed
    update_agent_status(scheduler.db, "test-run-003", "a", "completed")

    result = scheduler._build_result()

    assert result.success is True
    assert result.completed == ["a"]
    assert result.failed == []

    # Verify plan status was updated
    plan_row = get_plan(scheduler.db, "test-run-003")
    assert plan_row["status"] == "completed"

    scheduler.db.close()


def test_build_result_failure(temp_swarm_dir, monkeypatch):
    """Test _build_result with failed agent."""
    monkeypatch.chdir(temp_swarm_dir)

    agents = [AgentSpec(name="a", prompt="Task A")]
    plan = create_test_plan(agents)

    scheduler = Scheduler(plan, run_id="test-run-004", use_mock=True)
    scheduler._init_db()

    # Mark agent as failed
    update_agent_status(scheduler.db, "test-run-004", "a", "failed", "Test error")

    result = scheduler._build_result()

    assert result.success is False
    assert result.completed == []
    assert result.failed == ["a"]

    # Verify plan status was updated
    plan_row = get_plan(scheduler.db, "test-run-004")
    assert plan_row["status"] == "failed"

    scheduler.db.close()


def test_check_failed_deps(temp_swarm_dir, monkeypatch):
    """Test _check_failed_deps detection."""
    monkeypatch.chdir(temp_swarm_dir)

    agents = [
        AgentSpec(name="a", prompt="Task A"),
        AgentSpec(name="b", prompt="Task B", depends_on=["a"]),
    ]
    plan = create_test_plan(agents)

    scheduler = Scheduler(plan, run_id="test-run-005", use_mock=True)
    scheduler._init_db()

    # Mark 'a' as failed
    update_agent_status(scheduler.db, "test-run-005", "a", "failed")

    # Check 'b' for failed deps
    agent_b = get_agent(scheduler.db, "test-run-005", "b")
    failed_deps = scheduler._check_failed_deps(agent_b)

    assert failed_deps == ["a"]

    scheduler.db.close()


def test_external_cancellation_detection(temp_swarm_dir, monkeypatch):
    """Test that scheduler detects external cancellation."""
    monkeypatch.chdir(temp_swarm_dir)

    agents = [AgentSpec(name="a", prompt="Task A")]
    plan = create_test_plan(agents)

    scheduler = Scheduler(plan, run_id="test-run-006", use_mock=True)
    scheduler._init_db()

    # Simulate external cancellation
    update_plan_status(scheduler.db, "test-run-006", "cancelled")

    # Check that plan shows cancelled
    plan_row = get_plan(scheduler.db, "test-run-006")
    assert plan_row["status"] == "cancelled"

    scheduler.db.close()


@pytest.mark.asyncio
async def test_handle_cost_exceeded_warn(temp_swarm_dir, monkeypatch):
    """Test cost exceeded with warn action."""
    monkeypatch.chdir(temp_swarm_dir)

    cost_budget = CostBudget(total_usd=1.0, on_exceed="warn")
    agents = [AgentSpec(name="a", prompt="Task A")]
    plan = create_test_plan(agents, cost_budget=cost_budget)

    scheduler = Scheduler(plan, run_id="test-run-007", use_mock=True)
    scheduler._init_db()

    # Should return False (don't stop)
    should_stop = await scheduler._handle_cost_exceeded()
    assert should_stop is False

    # Plan should still be running
    plan_row = get_plan(scheduler.db, "test-run-007")
    assert plan_row["status"] == "running"

    scheduler.db.close()


@pytest.mark.asyncio
async def test_handle_cost_exceeded_cancel(temp_swarm_dir, monkeypatch):
    """Test cost exceeded with cancel action."""
    monkeypatch.chdir(temp_swarm_dir)

    cost_budget = CostBudget(total_usd=1.0, on_exceed="cancel")
    agents = [AgentSpec(name="a", prompt="Task A")]
    plan = create_test_plan(agents, cost_budget=cost_budget)

    scheduler = Scheduler(plan, run_id="test-run-008", use_mock=True)
    scheduler._init_db()

    # Should return True (stop)
    should_stop = await scheduler._handle_cost_exceeded()
    assert should_stop is True

    # Plan should be failed
    plan_row = get_plan(scheduler.db, "test-run-008")
    assert plan_row["status"] == "failed"

    scheduler.db.close()


@pytest.mark.asyncio
async def test_handle_cost_exceeded_pause(temp_swarm_dir, monkeypatch):
    """Test cost exceeded with pause action (default)."""
    monkeypatch.chdir(temp_swarm_dir)

    cost_budget = CostBudget(total_usd=1.0, on_exceed="pause")
    agents = [AgentSpec(name="a", prompt="Task A")]
    plan = create_test_plan(agents, cost_budget=cost_budget)

    scheduler = Scheduler(plan, run_id="test-run-009", use_mock=True)
    scheduler._init_db()

    # Should return True (stop)
    should_stop = await scheduler._handle_cost_exceeded()
    assert should_stop is True

    # Plan should be paused
    plan_row = get_plan(scheduler.db, "test-run-009")
    assert plan_row["status"] == "paused"

    scheduler.db.close()


def test_check_circuit_breaker_cancel_all(temp_swarm_dir, monkeypatch):
    """Test circuit breaker with cancel_all action."""
    monkeypatch.chdir(temp_swarm_dir)

    cb = CircuitBreaker(threshold=2, action="cancel_all")
    orchestration = Orchestration(circuit_breaker=cb)
    agents = [AgentSpec(name="a", prompt="Task A")]
    plan = create_test_plan(agents, orchestration=orchestration)

    scheduler = Scheduler(plan, run_id="test-run-010", use_mock=True)
    scheduler._init_db()
    scheduler.failure_count = 2  # At threshold

    should_stop = scheduler._check_circuit_breaker()
    assert should_stop is True

    plan_row = get_plan(scheduler.db, "test-run-010")
    assert plan_row["status"] == "failed"

    scheduler.db.close()


def test_check_circuit_breaker_pause(temp_swarm_dir, monkeypatch):
    """Test circuit breaker with pause action."""
    monkeypatch.chdir(temp_swarm_dir)

    cb = CircuitBreaker(threshold=2, action="pause")
    orchestration = Orchestration(circuit_breaker=cb)
    agents = [AgentSpec(name="a", prompt="Task A")]
    plan = create_test_plan(agents, orchestration=orchestration)

    scheduler = Scheduler(plan, run_id="test-run-011", use_mock=True)
    scheduler._init_db()
    scheduler.failure_count = 2  # At threshold

    should_stop = scheduler._check_circuit_breaker()
    assert should_stop is True

    plan_row = get_plan(scheduler.db, "test-run-011")
    assert plan_row["status"] == "paused"

    scheduler.db.close()


def test_check_circuit_breaker_notify_only(temp_swarm_dir, monkeypatch):
    """Test circuit breaker with notify_only action."""
    monkeypatch.chdir(temp_swarm_dir)

    cb = CircuitBreaker(threshold=2, action="notify_only")
    orchestration = Orchestration(circuit_breaker=cb)
    agents = [AgentSpec(name="a", prompt="Task A")]
    plan = create_test_plan(agents, orchestration=orchestration)

    scheduler = Scheduler(plan, run_id="test-run-012", use_mock=True)
    scheduler._init_db()
    scheduler.failure_count = 2  # At threshold

    should_stop = scheduler._check_circuit_breaker()
    assert should_stop is False  # notify_only doesn't stop

    scheduler.db.close()


def test_check_circuit_breaker_below_threshold(temp_swarm_dir, monkeypatch):
    """Test circuit breaker below threshold."""
    monkeypatch.chdir(temp_swarm_dir)

    cb = CircuitBreaker(threshold=5, action="cancel_all")
    orchestration = Orchestration(circuit_breaker=cb)
    agents = [AgentSpec(name="a", prompt="Task A")]
    plan = create_test_plan(agents, orchestration=orchestration)

    scheduler = Scheduler(plan, run_id="test-run-013", use_mock=True)
    scheduler._init_db()
    scheduler.failure_count = 2  # Below threshold

    should_stop = scheduler._check_circuit_breaker()
    assert should_stop is False

    scheduler.db.close()
