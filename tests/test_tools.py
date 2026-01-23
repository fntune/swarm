"""Tests for coordination tools."""

import asyncio

import pytest

from swarm.storage.db import (
    get_agent,
    get_response,
    init_db,
    insert_agent,
    insert_plan,
    update_agent_status,
)
from swarm.tools.worker import mark_complete, report_progress
from swarm.tools.manager import (
    mark_plan_complete,
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


def test_mark_complete_agent_not_found(temp_swarm_dir):
    """Test mark_complete with non-existent agent."""
    run_id = "test-mark-complete-1"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "name: test", 25.0)
    db.close()

    result = asyncio.run(mark_complete(run_id, "nonexistent", "Done"))

    assert "ERROR" in result["content"][0]["text"]
    assert "not found" in result["content"][0]["text"]


def test_mark_complete_check_passes(temp_swarm_dir):
    """Test mark_complete when check command passes."""
    run_id = "test-mark-complete-2"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "name: test", 25.0)
    insert_agent(db, run_id, "worker1", "Test task", check_command="true")
    worktree = temp_swarm_dir / ".swarm" / "runs" / run_id / "worktrees" / "worker1"
    worktree.mkdir(parents=True)
    db.execute(
        "UPDATE agents SET worktree = ? WHERE run_id = ? AND name = ?",
        (str(worktree), run_id, "worker1")
    )
    db.commit()
    db.close()

    result = asyncio.run(mark_complete(run_id, "worker1", "Task completed"))

    assert "completed successfully" in result["content"][0]["text"]

    db = init_db(run_id)
    agent = get_agent(db, run_id, "worker1")
    db.close()
    assert agent["status"] == "completed"


def test_mark_complete_check_fails(temp_swarm_dir):
    """Test mark_complete when check command fails."""
    run_id = "test-mark-complete-3"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "name: test", 25.0)
    insert_agent(db, run_id, "worker1", "Test task", check_command="false")
    worktree = temp_swarm_dir / ".swarm" / "runs" / run_id / "worktrees" / "worker1"
    worktree.mkdir(parents=True)
    db.execute(
        "UPDATE agents SET worktree = ? WHERE run_id = ? AND name = ?",
        (str(worktree), run_id, "worker1")
    )
    db.commit()
    db.close()

    result = asyncio.run(mark_complete(run_id, "worker1", "Done"))

    assert "Check failed" in result["content"][0]["text"]


def test_report_progress(temp_swarm_dir):
    """Test report_progress creates event."""
    run_id = "test-progress-1"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "name: test", 25.0)
    insert_agent(db, run_id, "worker1", "Test task")
    db.close()

    result = asyncio.run(report_progress(run_id, "worker1", "50% complete", "halfway"))

    assert "Progress recorded" in result["content"][0]["text"]


def test_spawn_worker_success(temp_swarm_dir):
    """Test spawn_worker creates new agent."""
    run_id = "test-spawn-1"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "name: test", 25.0)
    insert_agent(db, run_id, "manager", "Manage workers", agent_type="manager")
    db.close()

    result = asyncio.run(spawn_worker(run_id, "manager", "task1", "Do something", "pytest", "sonnet"))

    assert "Spawned worker: manager.task1" in result["content"][0]["text"]

    db = init_db(run_id)
    agent = get_agent(db, run_id, "manager.task1")
    db.close()
    assert agent is not None
    assert agent["parent"] == "manager"
    assert agent["prompt"] == "Do something"


def test_spawn_worker_already_exists(temp_swarm_dir):
    """Test spawn_worker fails if agent already exists."""
    run_id = "test-spawn-2"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "name: test", 25.0)
    insert_agent(db, run_id, "manager", "Manage workers", agent_type="manager")
    insert_agent(db, run_id, "manager.task1", "Existing", parent="manager")
    db.close()

    result = asyncio.run(spawn_worker(run_id, "manager", "task1", "Do something"))

    assert "already exists" in result["content"][0]["text"]


def test_respond_to_clarification(temp_swarm_dir):
    """Test respond_to_clarification creates response."""
    run_id = "test-respond-1"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "name: test", 25.0)
    insert_agent(db, run_id, "manager", "Manage workers")
    db.close()

    result = asyncio.run(respond_to_clarification(run_id, "manager", "clar123", "Use JWT"))

    assert "Response sent" in result["content"][0]["text"]

    db = init_db(run_id)
    response = get_response(db, run_id, "clar123")
    db.close()
    assert response is not None
    assert response["response"] == "Use JWT"


def test_mark_plan_complete_workers_pending(temp_swarm_dir):
    """Test mark_plan_complete fails if workers still running."""
    run_id = "test-plan-complete-1"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "name: test", 25.0)
    insert_agent(db, run_id, "manager", "Manage workers", agent_type="manager")
    insert_agent(db, run_id, "manager.task1", "Running task", parent="manager")
    update_agent_status(db, run_id, "manager.task1", "running")
    db.close()

    result = asyncio.run(mark_plan_complete(run_id, "manager", "All done"))

    assert "Cannot complete" in result["content"][0]["text"]
    assert "still running" in result["content"][0]["text"]


def test_mark_plan_complete_success(temp_swarm_dir):
    """Test mark_plan_complete when all workers done."""
    run_id = "test-plan-complete-2"
    db = init_db(run_id)
    insert_plan(db, run_id, "test", "name: test", 25.0)
    insert_agent(db, run_id, "manager", "Manage workers", agent_type="manager")
    insert_agent(db, run_id, "manager.task1", "Task 1", parent="manager")
    update_agent_status(db, run_id, "manager.task1", "completed")
    db.close()

    result = asyncio.run(mark_plan_complete(run_id, "manager", "All done"))

    assert "Plan complete" in result["content"][0]["text"]

    db = init_db(run_id)
    agent = get_agent(db, run_id, "manager")
    db.close()
    assert agent["status"] == "completed"
