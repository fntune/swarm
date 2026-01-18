"""Tests for coordination tools."""

import asyncio
import os

import pytest

from swarm.db import (
    get_agent,
    get_agents,
    get_pending_clarifications,
    get_response,
    init_db,
    insert_agent,
    insert_plan,
    insert_response,
    update_agent_status,
)
from swarm.tools import (
    get_run_context,
    handle_tool_call,
    mark_complete,
    mark_plan_complete,
    report_progress,
    request_clarification,
    respond_to_clarification,
    spawn_worker,
)


@pytest.fixture
def temp_swarm_dir(tmp_path, monkeypatch):
    """Create a temporary .swarm directory structure."""
    swarm_dir = tmp_path / ".swarm" / "runs"
    swarm_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def setup_env(monkeypatch):
    """Set up environment variables for tools."""
    def _setup(run_id: str, agent_name: str):
        monkeypatch.setenv("SWARM_RUN_ID", run_id)
        monkeypatch.setenv("SWARM_AGENT_NAME", agent_name)
    return _setup


def test_get_run_context_missing_vars(monkeypatch):
    """Test get_run_context raises when env vars missing."""
    monkeypatch.delenv("SWARM_RUN_ID", raising=False)
    monkeypatch.delenv("SWARM_AGENT_NAME", raising=False)

    with pytest.raises(RuntimeError, match="SWARM_RUN_ID and SWARM_AGENT_NAME must be set"):
        get_run_context()


def test_get_run_context_success(setup_env):
    """Test get_run_context returns correct values."""
    setup_env("test-run-123", "test-agent")
    run_id, agent_name = get_run_context()
    assert run_id == "test-run-123"
    assert agent_name == "test-agent"


def test_mark_complete_agent_not_found(temp_swarm_dir, setup_env):
    """Test mark_complete with non-existent agent."""
    run_id = "test-mark-complete-1"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "running", "name: test")
    db.close()

    setup_env(run_id, "nonexistent")
    result = asyncio.run(mark_complete("Done"))

    assert "ERROR" in result["content"][0]["text"]
    assert "not found" in result["content"][0]["text"]


def test_mark_complete_check_passes(temp_swarm_dir, setup_env):
    """Test mark_complete when check command passes."""
    run_id = "test-mark-complete-2"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "running", "name: test")
    insert_agent(db, run_id, "worker1", "Test task", check_command="true")
    # Create worktree dir
    worktree = temp_swarm_dir / ".swarm" / "runs" / run_id / "worktrees" / "worker1"
    worktree.mkdir(parents=True)
    db.execute(
        "UPDATE agents SET worktree = ? WHERE run_id = ? AND name = ?",
        (str(worktree), run_id, "worker1")
    )
    db.commit()
    db.close()

    setup_env(run_id, "worker1")
    result = asyncio.run(mark_complete("Task completed"))

    assert "completed successfully" in result["content"][0]["text"]

    # Verify status updated
    db = init_db(run_id)
    agent = get_agent(db, run_id, "worker1")
    db.close()
    assert agent["status"] == "completed"


def test_mark_complete_check_fails(temp_swarm_dir, setup_env):
    """Test mark_complete when check command fails."""
    run_id = "test-mark-complete-3"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "running", "name: test")
    insert_agent(db, run_id, "worker1", "Test task", check_command="false")
    worktree = temp_swarm_dir / ".swarm" / "runs" / run_id / "worktrees" / "worker1"
    worktree.mkdir(parents=True)
    db.execute(
        "UPDATE agents SET worktree = ? WHERE run_id = ? AND name = ?",
        (str(worktree), run_id, "worker1")
    )
    db.commit()
    db.close()

    setup_env(run_id, "worker1")
    result = asyncio.run(mark_complete("Done"))

    assert "Check failed" in result["content"][0]["text"]


def test_report_progress(temp_swarm_dir, setup_env):
    """Test report_progress creates event."""
    run_id = "test-progress-1"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "running", "name: test")
    insert_agent(db, run_id, "worker1", "Test task")
    db.close()

    setup_env(run_id, "worker1")
    result = asyncio.run(report_progress("50% complete", "halfway"))

    assert "Progress recorded" in result["content"][0]["text"]


def test_spawn_worker_success(temp_swarm_dir, setup_env):
    """Test spawn_worker creates new agent."""
    run_id = "test-spawn-1"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "running", "name: test")
    insert_agent(db, run_id, "manager", "Manage workers", agent_type="manager")
    db.close()

    setup_env(run_id, "manager")
    result = asyncio.run(spawn_worker("task1", "Do something", "pytest", "sonnet"))

    assert "Spawned worker: manager.task1" in result["content"][0]["text"]

    # Verify worker was created
    db = init_db(run_id)
    agent = get_agent(db, run_id, "manager.task1")
    db.close()
    assert agent is not None
    assert agent["parent"] == "manager"
    assert agent["prompt"] == "Do something"


def test_spawn_worker_already_exists(temp_swarm_dir, setup_env):
    """Test spawn_worker fails if agent already exists."""
    run_id = "test-spawn-2"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "running", "name: test")
    insert_agent(db, run_id, "manager", "Manage workers", agent_type="manager")
    insert_agent(db, run_id, "manager.task1", "Existing", parent="manager")
    db.close()

    setup_env(run_id, "manager")
    result = asyncio.run(spawn_worker("task1", "Do something"))

    assert "already exists" in result["content"][0]["text"]


def test_respond_to_clarification(temp_swarm_dir, setup_env):
    """Test respond_to_clarification creates response."""
    run_id = "test-respond-1"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "running", "name: test")
    insert_agent(db, run_id, "manager", "Manage workers")
    db.close()

    setup_env(run_id, "manager")
    result = asyncio.run(respond_to_clarification("clar123", "Use JWT"))

    assert "Response sent" in result["content"][0]["text"]

    # Verify response was inserted
    db = init_db(run_id)
    response = get_response(db, run_id, "clar123")
    db.close()
    assert response is not None
    assert response["response"] == "Use JWT"


def test_mark_plan_complete_workers_pending(temp_swarm_dir, setup_env):
    """Test mark_plan_complete fails if workers still running."""
    run_id = "test-plan-complete-1"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "running", "name: test")
    insert_agent(db, run_id, "manager", "Manage workers", agent_type="manager")
    insert_agent(db, run_id, "manager.task1", "Running task", parent="manager")
    update_agent_status(db, run_id, "manager.task1", "running")
    db.close()

    setup_env(run_id, "manager")
    result = asyncio.run(mark_plan_complete("All done"))

    assert "Cannot complete" in result["content"][0]["text"]
    assert "still running" in result["content"][0]["text"]


def test_mark_plan_complete_success(temp_swarm_dir, setup_env):
    """Test mark_plan_complete when all workers done."""
    run_id = "test-plan-complete-2"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "running", "name: test")
    insert_agent(db, run_id, "manager", "Manage workers", agent_type="manager")
    insert_agent(db, run_id, "manager.task1", "Task 1", parent="manager")
    update_agent_status(db, run_id, "manager.task1", "completed")
    db.close()

    setup_env(run_id, "manager")
    result = asyncio.run(mark_plan_complete("All done"))

    assert "Plan complete" in result["content"][0]["text"]

    # Verify manager marked completed
    db = init_db(run_id)
    agent = get_agent(db, run_id, "manager")
    db.close()
    assert agent["status"] == "completed"


def test_handle_tool_call_mark_complete(temp_swarm_dir, setup_env):
    """Test handle_tool_call dispatches to mark_complete."""
    run_id = "test-handle-1"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "running", "name: test")
    insert_agent(db, run_id, "worker1", "Test task", check_command="true")
    worktree = temp_swarm_dir / ".swarm" / "runs" / run_id / "worktrees" / "worker1"
    worktree.mkdir(parents=True)
    db.execute(
        "UPDATE agents SET worktree = ? WHERE run_id = ? AND name = ?",
        (str(worktree), run_id, "worker1")
    )
    db.commit()
    db.close()

    setup_env(run_id, "worker1")
    result = asyncio.run(handle_tool_call("mark_complete", {"summary": "Done"}))

    assert "completed successfully" in result["content"][0]["text"]


def test_handle_tool_call_unknown(setup_env):
    """Test handle_tool_call returns error for unknown tool."""
    setup_env("run-1", "agent-1")
    result = asyncio.run(handle_tool_call("nonexistent_tool", {}))

    assert "Unknown tool" in result["content"][0]["text"]
