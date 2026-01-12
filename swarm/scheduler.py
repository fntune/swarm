"""Scheduler for claude-swarm orchestration."""

import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import yaml

from swarm.db import (
    all_agents_done,
    get_agent,
    get_agents,
    get_pending_agents,
    get_total_cost,
    init_db,
    insert_agent,
    insert_event,
    insert_plan,
    update_agent_status,
    update_agent_worktree,
    update_plan_status,
)
from swarm.deps import DependencyGraph
from swarm.executor import AgentConfig, spawn_manager, spawn_worker
from swarm.git import create_worktree, setup_worktree_with_deps
from swarm.models import AgentSpec, PlanSpec
from swarm.parser import generate_run_id, load_shared_context

logger = logging.getLogger("swarm.scheduler")


@dataclass
class SchedulerResult:
    """Result of scheduler execution."""

    run_id: str
    success: bool
    completed: list[str]
    failed: list[str]
    total_cost: float
    error: str | None = None


class Scheduler:
    """Orchestrates agent execution."""

    def __init__(
        self,
        plan: PlanSpec,
        run_id: str | None = None,
        use_mock: bool = False,
    ):
        """Initialize scheduler.

        Args:
            plan: Plan specification
            run_id: Optional run ID (generated if not provided)
            use_mock: Use mock workers (for testing)
        """
        self.plan = plan
        self.run_id = run_id or generate_run_id(plan.name)
        self.use_mock = use_mock
        self.tasks: dict[str, asyncio.Task] = {}
        self.db: sqlite3.Connection | None = None

    def _init_db(self) -> None:
        """Initialize database and insert plan/agents."""
        self.db = init_db(self.run_id)

        # Insert plan
        insert_plan(
            self.db,
            self.run_id,
            self.plan.name,
            yaml.dump(self.plan.model_dump()),
            self.plan.cost_budget.total_usd if self.plan.cost_budget else 25.0,
        )

        # Insert agents
        defaults = self.plan.defaults
        for agent in self.plan.agents:
            insert_agent(
                self.db,
                self.run_id,
                agent.name,
                agent.prompt,
                agent_type=agent.type,
                check_command=agent.check or defaults.check,
                model=agent.model or defaults.model,
                max_iterations=agent.max_iterations or defaults.max_iterations,
                max_cost_usd=agent.max_cost_usd or defaults.max_cost_usd,
                depends_on=agent.depends_on,
                plan_name=self.plan.name,
            )

        logger.info(f"Initialized run {self.run_id} with {len(self.plan.agents)} agents")

    async def _spawn_agent(self, agent_row: sqlite3.Row) -> asyncio.Task:
        """Create worktree and spawn agent.

        Args:
            agent_row: Agent database row

        Returns:
            asyncio.Task handle
        """
        name = agent_row["name"]
        agent_type = agent_row["type"] or "worker"

        # Create worktree
        worktree_path = create_worktree(self.run_id, name)

        # Merge dependencies
        depends_on = json.loads(agent_row["depends_on"] or "[]")
        if depends_on:
            dep_context = self.plan.orchestration.dependency_context if self.plan.orchestration else None
            setup_worktree_with_deps(
                self.run_id,
                name,
                depends_on,
                worktree_path,
                mode=dep_context.mode if dep_context else "full",
            )

        # Update DB with worktree info
        update_agent_worktree(
            self.db,
            self.run_id,
            name,
            str(worktree_path),
            f"swarm/{self.run_id}/{name}",
        )

        # Load shared context
        shared_context = ""
        if self.plan.shared_context:
            shared_context = load_shared_context(self.plan.shared_context)

        # Build config
        config = AgentConfig(
            name=name,
            run_id=self.run_id,
            prompt=agent_row["prompt"],
            worktree=worktree_path,
            check_command=agent_row["check_command"] or "true",
            model=agent_row["model"] or "sonnet",
            max_iterations=agent_row["max_iterations"] or 30,
            max_cost_usd=agent_row["max_cost_usd"] or 5.0,
            parent=agent_row["parent"],
        )

        # Spawn based on type
        if agent_type == "manager":
            return await spawn_manager(config)
        else:
            return await spawn_worker(config, use_mock=self.use_mock)

    def _check_failed_deps(self, agent_row: sqlite3.Row) -> list[str]:
        """Check if agent has failed dependencies.

        Args:
            agent_row: Agent database row

        Returns:
            List of failed dependency names
        """
        depends_on = json.loads(agent_row["depends_on"] or "[]")
        if not depends_on:
            return []

        failed = []
        for dep_name in depends_on:
            dep = get_agent(self.db, self.run_id, dep_name)
            if dep and dep["status"] in ("failed", "timeout", "cancelled", "cost_exceeded"):
                failed.append(dep_name)

        return failed

    async def _handle_cost_exceeded(self) -> None:
        """Handle cost budget exceeded."""
        logger.warning(f"Run {self.run_id}: cost budget exceeded")

        # Update plan status
        update_plan_status(self.db, self.run_id, "paused")

        # Cancel running tasks
        for name, task in self.tasks.items():
            if not task.done():
                task.cancel()
                update_agent_status(self.db, self.run_id, name, "paused")

        # Emit event
        total_cost = get_total_cost(self.db, self.run_id)
        budget = self.plan.cost_budget.total_usd if self.plan.cost_budget else 25.0
        insert_event(
            self.db,
            self.run_id,
            "_system",
            "error",
            {"error": "cost_exceeded", "total_cost": total_cost, "budget": budget},
        )

    def _build_result(self) -> SchedulerResult:
        """Build scheduler result from current state."""
        agents = get_agents(self.db, self.run_id)

        completed = [a["name"] for a in agents if a["status"] == "completed"]
        failed = [a["name"] for a in agents if a["status"] in ("failed", "timeout", "cancelled")]
        total_cost = get_total_cost(self.db, self.run_id)

        success = len(failed) == 0 and len(completed) == len(agents)

        return SchedulerResult(
            run_id=self.run_id,
            success=success,
            completed=completed,
            failed=failed,
            total_cost=total_cost,
        )

    async def run(self) -> SchedulerResult:
        """Execute the plan.

        Returns:
            SchedulerResult with execution details
        """
        self._init_db()

        try:
            while not all_agents_done(self.db, self.run_id):
                # Find ready agents
                ready = get_pending_agents(self.db, self.run_id)

                # Check for failed dependencies
                for row in ready:
                    failed_deps = self._check_failed_deps(row)
                    if failed_deps:
                        update_agent_status(
                            self.db,
                            self.run_id,
                            row["name"],
                            "failed",
                            f"Dependency failed: {failed_deps}",
                        )
                        insert_event(
                            self.db,
                            self.run_id,
                            row["name"],
                            "cascade_skip",
                            {"failed_deps": failed_deps},
                        )
                        continue

                    # Spawn if not already running
                    if row["name"] not in self.tasks:
                        task = await self._spawn_agent(row)
                        self.tasks[row["name"]] = task
                        logger.info(f"Spawned agent {row['name']}")

                # Clean up completed tasks
                for name, task in list(self.tasks.items()):
                    if task.done():
                        try:
                            result = task.result()
                            logger.info(f"Agent {name} finished: {result}")
                        except asyncio.CancelledError:
                            logger.info(f"Agent {name} was cancelled")
                        except Exception as e:
                            logger.error(f"Agent {name} raised exception: {e}")
                            update_agent_status(self.db, self.run_id, name, "failed", str(e))
                        del self.tasks[name]

                # Check cost budget
                if self.plan.cost_budget:
                    total_cost = get_total_cost(self.db, self.run_id)
                    if total_cost > self.plan.cost_budget.total_usd:
                        await self._handle_cost_exceeded()
                        break

                await asyncio.sleep(1)

            # Wait for any remaining tasks
            if self.tasks:
                await asyncio.gather(*self.tasks.values(), return_exceptions=True)

            return self._build_result()

        finally:
            if self.db:
                self.db.close()


async def run_plan(
    plan: PlanSpec,
    run_id: str | None = None,
    use_mock: bool = False,
) -> SchedulerResult:
    """Run a plan.

    Args:
        plan: Plan specification
        run_id: Optional run ID
        use_mock: Use mock workers

    Returns:
        SchedulerResult
    """
    scheduler = Scheduler(plan, run_id, use_mock)
    return await scheduler.run()
