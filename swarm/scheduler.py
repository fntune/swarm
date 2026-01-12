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
    get_retryable_agents,
    get_total_cost,
    increment_retry_attempt,
    init_db,
    insert_agent,
    insert_event,
    insert_plan,
    open_db,
    reset_agent_for_retry,
    reset_failed_agents,
    run_exists,
    update_agent_status,
    update_agent_worktree,
    update_plan_status,
)
from swarm.deps import DependencyGraph
from swarm.executor import AgentConfig, spawn_manager, spawn_worker
from swarm.git import create_worktree, setup_worktree_with_deps
from swarm.models import AgentSpec, PlanSpec
from swarm.parser import generate_run_id, load_shared_context
from swarm.roles import apply_role, get_role_defaults

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
        resume: bool = False,
    ):
        """Initialize scheduler.

        Args:
            plan: Plan specification
            run_id: Optional run ID (generated if not provided)
            use_mock: Use mock workers (for testing)
            resume: Resume existing run (skip completed agents, reset failed)
        """
        self.plan = plan
        self.run_id = run_id or generate_run_id(plan.name)
        self.use_mock = use_mock
        self.resume = resume
        self.tasks: dict[str, asyncio.Task] = {}
        self.db: sqlite3.Connection | None = None

    def _init_db(self) -> None:
        """Initialize database and insert plan/agents."""
        if self.resume and run_exists(self.run_id):
            # Resume existing run
            self.db = open_db(self.run_id)
            update_plan_status(self.db, self.run_id, "running")

            # Reset failed/timeout agents for retry
            reset_names = reset_failed_agents(self.db, self.run_id)
            if reset_names:
                logger.info(f"Reset agents for retry: {reset_names}")

            agents = get_agents(self.db, self.run_id)
            completed = [a["name"] for a in agents if a["status"] == "completed"]
            pending = [a["name"] for a in agents if a["status"] == "pending"]
            logger.info(f"Resuming run {self.run_id}: {len(completed)} completed, {len(pending)} pending")
            return

        # New run - initialize fresh
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
            # Apply role template if specified
            prompt = agent.prompt
            role_defaults = {}
            if agent.use_role:
                prompt = apply_role(agent.prompt, agent.use_role)
                role_defaults = get_role_defaults(agent.use_role)

            insert_agent(
                self.db,
                self.run_id,
                agent.name,
                prompt,
                agent_type=agent.type,
                check_command=agent.check or role_defaults.get("check") or defaults.check,
                model=agent.model or role_defaults.get("model") or defaults.model,
                max_iterations=agent.max_iterations or defaults.max_iterations,
                max_cost_usd=agent.max_cost_usd or defaults.max_cost_usd,
                depends_on=agent.depends_on,
                plan_name=self.plan.name,
                on_failure=agent.on_failure or defaults.on_failure,
                retry_count=agent.retry_count or defaults.retry_count,
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

        # Add error context for retries
        error_context = self._build_error_context(agent_row)
        prompt = agent_row["prompt"]
        if error_context:
            prompt = f"{prompt}\n\n{error_context}"

        # Build config
        config = AgentConfig(
            name=name,
            run_id=self.run_id,
            prompt=prompt,
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

    async def _handle_agent_failure(self, name: str, error: str) -> bool:
        """Handle agent failure based on on_failure setting.

        Returns True if run should stop.
        """
        agent = get_agent(self.db, self.run_id, name)
        if not agent:
            return False

        on_failure = agent["on_failure"] or "continue"

        if on_failure == "stop":
            logger.warning(f"Agent {name} failed with on_failure=stop, cancelling run")
            update_plan_status(self.db, self.run_id, "failed")

            # Cancel all running tasks
            for task_name, task in self.tasks.items():
                if not task.done() and task_name != name:
                    task.cancel()
                    update_agent_status(self.db, self.run_id, task_name, "cancelled")

            # Mark remaining pending agents as cancelled
            for a in get_agents(self.db, self.run_id):
                if a["status"] == "pending":
                    update_agent_status(self.db, self.run_id, a["name"], "cancelled", "Run stopped due to failure")

            return True

        elif on_failure == "retry":
            retry_count = agent["retry_count"] or 3
            attempt = increment_retry_attempt(self.db, self.run_id, name, error)

            if attempt < retry_count:
                logger.info(f"Retrying agent {name} (attempt {attempt + 1}/{retry_count})")
                reset_agent_for_retry(self.db, self.run_id, name)
                insert_event(
                    self.db,
                    self.run_id,
                    name,
                    "progress",
                    {"status": f"Retry attempt {attempt + 1}/{retry_count}", "last_error": error[:200]},
                )
            else:
                logger.warning(f"Agent {name} exhausted retries ({retry_count})")
                update_agent_status(self.db, self.run_id, name, "failed", f"Exhausted {retry_count} retries: {error}")

        # on_failure == "continue" - do nothing special
        return False

    def _build_error_context(self, agent_row: sqlite3.Row) -> str:
        """Build error context for retried agents."""
        last_error = agent_row["last_error"]
        retry_attempt = agent_row["retry_attempt"] or 0

        if not last_error or retry_attempt == 0:
            return ""

        return f"""
## Previous Attempt Failed

This is retry attempt {retry_attempt + 1}. The previous attempt failed with:

```
{last_error[:500]}
```

Please address this error and continue with the task.
"""

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

                # Clean up completed tasks and handle failures
                should_stop = False
                for name, task in list(self.tasks.items()):
                    if task.done():
                        try:
                            result = task.result()
                            logger.info(f"Agent {name} finished: {result}")

                            # Check if agent failed
                            agent = get_agent(self.db, self.run_id, name)
                            if agent and agent["status"] == "failed":
                                error = agent["error"] or "Unknown error"
                                should_stop = await self._handle_agent_failure(name, error)

                        except asyncio.CancelledError:
                            logger.info(f"Agent {name} was cancelled")
                        except Exception as e:
                            logger.error(f"Agent {name} raised exception: {e}")
                            update_agent_status(self.db, self.run_id, name, "failed", str(e))
                            should_stop = await self._handle_agent_failure(name, str(e))

                        del self.tasks[name]

                        if should_stop:
                            break

                if should_stop:
                    break

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
    resume: bool = False,
) -> SchedulerResult:
    """Run a plan.

    Args:
        plan: Plan specification
        run_id: Optional run ID
        use_mock: Use mock workers
        resume: Resume existing run

    Returns:
        SchedulerResult
    """
    scheduler = Scheduler(plan, run_id, use_mock, resume)
    return await scheduler.run()
