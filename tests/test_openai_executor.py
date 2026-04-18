"""Tests for the OpenAI executor, its tool bridges, and the cost estimator.

Skipped when the openai-agents SDK isn't installed (optional [openai] extra).
"""

from __future__ import annotations

import pytest

pytest.importorskip("agents", reason="openai-agents SDK not installed")

from pathlib import Path

from swarm.core.budget import estimate_cost_usd
from swarm.runtime.executors.base import get_executor
from swarm.runtime.executors.openai import OpenAIExecutor
from swarm.tools.openai_code import build_code_tools


def test_openai_executor_registers():
    ex = get_executor("openai")
    assert isinstance(ex, OpenAIExecutor)
    assert ex.runtime == "openai"


def test_budget_estimates_known_model():
    cost = estimate_cost_usd("gpt-5", 1_000_000, 1_000_000)
    assert cost == pytest.approx(5.00 + 15.00, rel=1e-6)


def test_budget_estimates_unknown_model_uses_default():
    cost = estimate_cost_usd("no-such-model", 100_000, 100_000)
    expected = (100_000 / 1_000_000) * 5.00 + (100_000 / 1_000_000) * 15.00
    assert cost == pytest.approx(expected, rel=1e-6)


def test_budget_strips_date_suffix():
    assert estimate_cost_usd("gpt-5-2025-08-14", 1_000_000, 0) == pytest.approx(5.00)
    assert estimate_cost_usd("gpt-4o-2024-08-06", 1_000_000, 0) == pytest.approx(2.50)


def test_code_tools_write_allowed_includes_write_edit_bash(tmp_path):
    tools = build_code_tools(tmp_path, write_allowed=True)
    names = {t.name for t in tools}
    assert names == {"Read", "Write", "Edit", "Bash", "Glob", "Grep"}


def test_code_tools_read_only_strips_write_edit_bash(tmp_path):
    tools = build_code_tools(tmp_path, write_allowed=False)
    names = {t.name for t in tools}
    assert names == {"Read", "Glob", "Grep"}


def test_factory_openai_builds_coord_tools():
    from swarm.tools.factory_openai import build_manager_coord_tools, build_worker_coord_tools

    worker_tools = build_worker_coord_tools("run-x", "agent-a")
    worker_names = {t.name for t in worker_tools}
    assert worker_names == {
        "mark_complete", "request_clarification", "report_progress", "report_blocker",
    }

    manager_tools = build_manager_coord_tools("run-x", "manager-a")
    manager_names = {t.name for t in manager_tools}
    assert manager_names == {
        "spawn_worker", "respond_to_clarification", "cancel_worker",
        "get_worker_status", "get_pending_clarifications", "mark_plan_complete",
    }


@pytest.mark.asyncio
async def test_api_accepts_openai_runtime_on_agentspec(tmp_path, monkeypatch):
    """AgentSpec(runtime='openai') is accepted and persisted to the agents table."""
    from swarm import agent, run
    from swarm.storage.db import get_db

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".swarm" / "runs").mkdir(parents=True)

    def fake_create_worktree(run_id, agent_name, *args, **kwargs):
        path = tmp_path / ".swarm" / "runs" / run_id / "worktrees" / agent_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr("swarm.runtime.scheduler.create_worktree", fake_create_worktree)
    monkeypatch.setattr("swarm.runtime.scheduler.setup_worktree_with_deps", lambda *a, **kw: None)

    # use_mock=True bypasses the vendor executor — we're only verifying that
    # runtime="openai" survives the YAML/AgentSpec → scheduler → DB path.
    result = await run(
        [agent("gpt", "task", check="true", runtime="openai")],
        name="mixed-runtime",
        use_mock=True,
    )

    assert result.success is True
    with get_db(result.run_id) as db:
        row = db.execute(
            "SELECT runtime, cost_source FROM agents WHERE run_id = ? AND name = ?",
            (result.run_id, "gpt"),
        ).fetchone()
    assert row["runtime"] == "openai"
    assert row["cost_source"] == "estimated"
