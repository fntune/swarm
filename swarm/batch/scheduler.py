"""Batch scheduler — parallel execution of a resolved plan.

One pass over list[ResolvedAgent]:

- Initialize the DB (or walk the attempts table for resume).
- Poll for ready nodes (latest attempt pending + deps terminal).
- Allocate a workspace, build a RunContext, dispatch to the executor.
- On completion: persist ExecutionResult, apply on_failure policy (insert a
  new attempts row for retry, or cascade-fail dependents).
- Keep running until every node's latest attempt is terminal, then build
  and return a SchedulerResult.

External controls:
- Circuit breaker (failure_count >= threshold)
- Cost budget (total_cost >= budget)
- Stuck detection (no new events for N polls)
- External cancel (a plan_cancel event)
"""

import asyncio
import dataclasses
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from swarm.batch.input import generate_run_id, load_shared_context
from swarm.batch.plan import PlanSpec
from swarm.batch.sqlite import (
    SqliteCoordinationBackend,
    SqliteSink,
    all_nodes_done,
    get_db,
    get_db_path,
    get_node,
    get_nodes,
    get_total_cost,
    init_db,
    insert_attempt,
    insert_event,
    insert_node,
    insert_workspace,
    latest_attempt,
    mark_attempt_started,
    open_db,
    run_exists,
    update_attempt_cost,
    update_attempt_session,
    update_attempt_status,
)
from swarm.core.agent import ResolvedAgent
from swarm.core.errors import PlanValidationError, WorkspaceError
from swarm.core.events import (
    AgentCompleted,
    AgentStarted,
    EventSink,
)
from swarm.core.execution import (
    Executor,
    ExecutionResult,
    RunContext,
    get_executor,
)
from swarm.core.workspace import Cwd, GitWorktree, TempDir, Workspace

logger = logging.getLogger("swarm.batch.scheduler")

POLL_INTERVAL_SECONDS = 1.0
STUCK_THRESHOLD_ITERATIONS = 30
TERMINAL_STATUSES = {
    "completed",
    "failed",
    "timeout",
    "cancelled",
    "cost_exceeded",
}


@dataclass
class SchedulerResult:
    run_id: str
    success: bool
    completed: list[str]
    failed: list[str]
    total_cost: float
    error: str | None = None


@dataclass
class _AttemptHandle:
    node_name: str
    attempt_id: str
    attempt_number: int
    workspace: Workspace
    task: asyncio.Task[ExecutionResult]


class Scheduler:
    def __init__(
        self,
        plan: PlanSpec,
        resolved: list[ResolvedAgent] | None = None,
        *,
        run_id: str | None = None,
        resume: bool = False,
        base_path: Path | None = None,
        workspace_provider: Any | None = None,
    ):
        self.plan = plan
        self.resolved_by_name: dict[str, ResolvedAgent] = (
            {r.name: r for r in resolved} if resolved else {}
        )
        self.run_id = run_id or generate_run_id(plan.name)
        self.resume = resume
        self.base_path = base_path or Path.cwd()
        self.workspace_provider = workspace_provider or _default_workspace_provider(
            self.base_path
        )
        self.coord = SqliteCoordinationBackend(base_path=self.base_path)
        self.events: EventSink = SqliteSink(self.run_id, self.base_path)
        self.in_flight: dict[str, _AttemptHandle] = {}
        self.failure_count = 0
        self.idle_iterations = 0
        self.last_event_count = 0
        self._shared_context: str | None = None

    # ------------------------------------------------------------------
    # Init / resume
    # ------------------------------------------------------------------

    def _init_fresh(self) -> None:
        db = init_db(self.run_id, self.base_path)
        try:
            for agent in self.resolved_by_name.values():
                insert_node(
                    db,
                    run_id=self.run_id,
                    name=agent.name,
                    plan_name=self.plan.name,
                    runtime=agent.runtime,
                    profile=agent.profile.name,
                    model=agent.model,
                    prompt=agent.prompt,
                    check_command=agent.check,
                    depends_on=agent.depends_on,
                    max_iterations=agent.limits.max_iterations,
                    max_cost_usd=agent.limits.max_cost_usd,
                    on_failure=agent.on_failure,
                    retry_count=agent.retry_count,
                    parent=agent.parent,
                    tree_path=agent.tree_path,
                    env=agent.env_dict(),
                    output_schema=agent.output_schema,
                )
                insert_attempt(
                    db,
                    run_id=self.run_id,
                    node_name=agent.name,
                    attempt_number=1,
                    status="pending",
                )
            logger.info(
                "Initialized run %s with %d agents", self.run_id, len(self.resolved_by_name)
            )
        finally:
            db.close()

    def _init_resume(self) -> None:
        with get_db(self.run_id, self.base_path) as db:
            nodes = get_nodes(db, self.run_id)
            for row in nodes:
                # Rebuild the in-memory resolved-by-name from the persisted
                # row so dispatch doesn't have to reach back into the DB.
                if row["name"] not in self.resolved_by_name:
                    self.resolved_by_name[row["name"]] = _resolved_from_row(row)
                attempt = latest_attempt(db, self.run_id, row["name"])
                if attempt is None:
                    insert_attempt(
                        db,
                        run_id=self.run_id,
                        node_name=row["name"],
                        attempt_number=1,
                        status="pending",
                    )
                    continue
                if attempt["status"] == "completed":
                    continue
                next_number = (attempt["attempt_number"] or 0) + 1
                insert_attempt(
                    db,
                    run_id=self.run_id,
                    node_name=row["name"],
                    attempt_number=next_number,
                    status="pending",
                )
                logger.info(
                    "Resume: new attempt #%d for %s (prev status=%s)",
                    next_number,
                    row["name"],
                    attempt["status"],
                )

    # ------------------------------------------------------------------
    # Workspace + prompt assembly
    # ------------------------------------------------------------------

    async def _allocate_workspace(self, agent_name: str) -> Workspace:
        workspace = await self.workspace_provider.allocate(self.run_id, agent_name)
        kind = _workspace_kind(workspace)
        branch = getattr(workspace, "branch", None)
        base_branch = getattr(workspace, "base_branch", None)
        with get_db(self.run_id, self.base_path) as db:
            insert_workspace(
                db,
                workspace_id=workspace.workspace_id,
                run_id=self.run_id,
                kind=kind,
                path=str(workspace.path),
                branch=branch,
                base_branch=base_branch,
            )
        if isinstance(workspace, GitWorktree):
            await self._merge_deps(agent_name, workspace)
        return workspace

    async def _merge_deps(self, agent_name: str, workspace: GitWorktree) -> None:
        from swarm.workspaces.git import setup_worktree_with_deps

        agent = self.resolved_by_name.get(agent_name)
        if not agent or not agent.depends_on:
            return
        dep_ctx = None
        if self.plan.orchestration and self.plan.orchestration.dependency_context:
            dep_ctx = self.plan.orchestration.dependency_context
        try:
            setup_worktree_with_deps(
                self.run_id,
                agent_name,
                list(agent.depends_on),
                workspace.path,
                mode=dep_ctx.mode if dep_ctx else "full",
                include_paths=list(dep_ctx.include_paths) if dep_ctx else None,
                exclude_paths=list(dep_ctx.exclude_paths) if dep_ctx else None,
            )
        except Exception as exc:
            raise WorkspaceError(f"Failed to merge deps for {agent_name}: {exc}") from exc

    def _build_prompt(self, agent: ResolvedAgent, attempt_number: int) -> str:
        parts: list[str] = []
        if agent.profile.prompt_preamble:
            parts.append(agent.profile.prompt_preamble)
        if self._shared_context:
            parts.append("## Shared Context\n" + self._shared_context)
        if attempt_number > 1:
            prior_error = self._last_attempt_error(agent.name, attempt_number)
            if prior_error:
                parts.append(
                    "## Previous Attempt Failed\n\n"
                    f"This is retry attempt {attempt_number}. "
                    f"The previous attempt failed with:\n\n```\n{prior_error[:500]}\n```\n\n"
                    "Please address this error and continue with the task."
                )
        parts.append("## Your Task\n\n" + agent.prompt)
        return "\n\n".join(parts)

    def _last_attempt_error(self, node_name: str, current_number: int) -> str | None:
        with get_db(self.run_id, self.base_path) as db:
            row = db.execute(
                """SELECT error FROM attempts
                     WHERE run_id = ? AND node_name = ?
                       AND attempt_number = ?""",
                (self.run_id, node_name, current_number - 1),
            ).fetchone()
        return row["error"] if row else None

    # ------------------------------------------------------------------
    # Dispatch loop
    # ------------------------------------------------------------------

    async def run(self) -> SchedulerResult:
        if self.resume and run_exists(self.run_id, self.base_path):
            self._init_resume()
        else:
            self._init_fresh()

        if self.plan.shared_context:
            self._shared_context = load_shared_context(
                list(self.plan.shared_context), self.base_path
            )

        try:
            while True:
                if await self._external_cancel():
                    break
                await self._dispatch_ready()
                if await self._reap_done():
                    break
                if self._check_circuit_breaker():
                    break
                if await self._check_cost_budget():
                    break
                self._check_stuck()
                with get_db(self.run_id, self.base_path) as db:
                    if all_nodes_done(db, self.run_id) and not self.in_flight:
                        break
                await asyncio.sleep(POLL_INTERVAL_SECONDS)

            if self.in_flight:
                await asyncio.gather(
                    *(h.task for h in self.in_flight.values()),
                    return_exceptions=True,
                )
            return self._build_result()
        finally:
            await self._release_all_workspaces(keep=True)

    async def _dispatch_ready(self) -> None:
        with get_db(self.run_id, self.base_path) as db:
            rows = db.execute(
                """SELECT n.*, a.attempt_id, a.attempt_number, a.status AS attempt_status
                     FROM nodes n
                     JOIN attempts a
                       ON a.run_id = n.run_id AND a.node_name = n.name
                     WHERE n.run_id = ?
                       AND a.attempt_number = (
                           SELECT MAX(attempt_number) FROM attempts b
                           WHERE b.run_id = n.run_id AND b.node_name = n.name
                       )
                       AND a.status = 'pending'""",
                (self.run_id,),
            ).fetchall()

        for row in rows:
            name = row["name"]
            if name in self.in_flight:
                continue
            deps = json.loads(row["depends_on"])
            if not self._deps_ready_or_skip(name, deps):
                continue
            await self._launch(row)

    def _deps_ready_or_skip(self, name: str, deps: list[str]) -> bool:
        if not deps:
            return True
        with get_db(self.run_id, self.base_path) as db:
            failed: list[str] = []
            not_done: list[str] = []
            for dep in deps:
                attempt = latest_attempt(db, self.run_id, dep)
                if attempt is None:
                    not_done.append(dep)
                    continue
                status = attempt["status"]
                if status == "completed":
                    continue
                if status in TERMINAL_STATUSES:
                    failed.append(dep)
                else:
                    not_done.append(dep)
            if not_done and not failed:
                return False
            if failed:
                current = latest_attempt(db, self.run_id, name)
                if current is not None:
                    update_attempt_status(
                        db,
                        current["attempt_id"],
                        "failed",
                        f"Dependency failed: {failed}",
                    )
                    insert_event(
                        db,
                        run_id=self.run_id,
                        agent=name,
                        event_type="cascade_skip",
                        data={"failed_deps": failed},
                    )
                return False
        return True

    async def _launch(self, row: sqlite3.Row) -> None:
        name = row["name"]
        agent = self.resolved_by_name.get(name)
        if agent is None:
            agent = _resolved_from_row(row)
            self.resolved_by_name[name] = agent

        try:
            workspace = await self._allocate_workspace(name)
        except WorkspaceError as exc:
            logger.error("Workspace allocation failed for %s: %s", name, exc)
            with get_db(self.run_id, self.base_path) as db:
                update_attempt_status(db, row["attempt_id"], "failed", str(exc))
            return

        with get_db(self.run_id, self.base_path) as db:
            db.execute(
                "UPDATE attempts SET workspace_id = ? WHERE attempt_id = ?",
                (workspace.workspace_id, row["attempt_id"]),
            )
            db.commit()
            mark_attempt_started(db, row["attempt_id"])

        prompt = self._build_prompt(agent, row["attempt_number"])
        dispatch_agent = dataclasses.replace(agent, prompt=prompt)

        ctx = RunContext(
            run_id=self.run_id,
            workspace=workspace,
            coord=self.coord,
            events=self.events,
        )

        try:
            executor: Executor = get_executor(agent.runtime)
        except KeyError as exc:
            with get_db(self.run_id, self.base_path) as db:
                update_attempt_status(db, row["attempt_id"], "failed", str(exc))
            logger.error("No executor for runtime %s: %s", agent.runtime, exc)
            return

        self.events.emit(
            AgentStarted(run_id=self.run_id, agent=name, runtime=agent.runtime)
        )

        task = asyncio.create_task(executor.run(dispatch_agent, ctx))
        self.in_flight[name] = _AttemptHandle(
            node_name=name,
            attempt_id=row["attempt_id"],
            attempt_number=row["attempt_number"],
            workspace=workspace,
            task=task,
        )
        logger.info("Launched %s (runtime=%s)", name, agent.runtime)

    async def _reap_done(self) -> bool:
        stop = False
        for name, handle in list(self.in_flight.items()):
            if not handle.task.done():
                continue
            exc: BaseException | None = None
            result: ExecutionResult | None = None
            try:
                result = handle.task.result()
            except asyncio.CancelledError:
                logger.info("Agent %s was cancelled", name)
                exc = asyncio.CancelledError()
            except Exception as e:  # noqa: BLE001
                logger.exception("Agent %s raised: %s", name, e)
                exc = e

            if exc is not None:
                with get_db(self.run_id, self.base_path) as db:
                    update_attempt_status(
                        db, handle.attempt_id, "failed", str(exc)
                    )
                self.events.emit(
                    AgentCompleted(
                        run_id=self.run_id,
                        agent=name,
                        status="failed",
                        error=str(exc),
                    )
                )
                stop = stop or await self._apply_failure_policy(name)
            elif result is not None:
                await self._persist_result(handle, result)
                if result.status != "completed":
                    self.failure_count += 1
                    stop = stop or await self._apply_failure_policy(name)

            del self.in_flight[name]

            if stop:
                break
        return stop

    async def _persist_result(
        self, handle: _AttemptHandle, result: ExecutionResult
    ) -> None:
        with get_db(self.run_id, self.base_path) as db:
            update_attempt_cost(
                db, handle.attempt_id, result.cost_usd, result.cost_source
            )
            if result.vendor_session_id:
                update_attempt_session(
                    db, handle.attempt_id, result.vendor_session_id
                )
            update_attempt_status(
                db, handle.attempt_id, result.status, result.error
            )
        self.events.emit(
            AgentCompleted(
                run_id=self.run_id,
                agent=handle.node_name,
                status=result.status,
                error=result.error,
            )
        )

    async def _apply_failure_policy(self, name: str) -> bool:
        """Return True if the whole run should stop."""
        with get_db(self.run_id, self.base_path) as db:
            node = get_node(db, self.run_id, name)
            if node is None:
                return False
            policy = node["on_failure"] or "continue"
            retry_count = node["retry_count"] or 0
            last = latest_attempt(db, self.run_id, name)
            attempt_number = last["attempt_number"] if last else 1

        if policy == "stop":
            logger.warning("on_failure=stop for %s, stopping run", name)
            await self._cancel_in_flight("cancelled", "Run stopped due to failure")
            self._mark_remaining_pending_as("cancelled", "Run stopped due to failure")
            return True

        if policy == "retry":
            if attempt_number < retry_count:
                with get_db(self.run_id, self.base_path) as db:
                    insert_attempt(
                        db,
                        run_id=self.run_id,
                        node_name=name,
                        attempt_number=attempt_number + 1,
                        status="pending",
                    )
                    insert_event(
                        db,
                        run_id=self.run_id,
                        agent=name,
                        event_type="progress",
                        data={
                            "status": f"Retry attempt {attempt_number + 1}/{retry_count}",
                        },
                    )
                logger.info(
                    "Queued retry %d/%d for %s",
                    attempt_number + 1,
                    retry_count,
                    name,
                )
            else:
                logger.warning("Agent %s exhausted retries (%d)", name, retry_count)
        return False

    async def _cancel_in_flight(self, status: str, reason: str) -> None:
        for handle in self.in_flight.values():
            if not handle.task.done():
                handle.task.cancel()
            with get_db(self.run_id, self.base_path) as db:
                update_attempt_status(db, handle.attempt_id, status, reason)

    def _mark_remaining_pending_as(self, status: str, reason: str) -> None:
        with get_db(self.run_id, self.base_path) as db:
            db.execute(
                """UPDATE attempts
                     SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP
                     WHERE run_id = ?
                       AND attempt_id IN (
                           SELECT attempt_id FROM attempts a
                           WHERE a.run_id = ? AND a.status = 'pending'
                             AND a.attempt_number = (
                                 SELECT MAX(attempt_number) FROM attempts b
                                 WHERE b.run_id = a.run_id AND b.node_name = a.node_name
                             )
                       )""",
                (status, reason, self.run_id, self.run_id),
            )
            db.commit()

    async def _external_cancel(self) -> bool:
        with get_db(self.run_id, self.base_path) as db:
            row = db.execute(
                """SELECT event_id FROM events
                     WHERE run_id = ? AND event_type = 'plan_cancel'
                     LIMIT 1""",
                (self.run_id,),
            ).fetchone()
        if row is None:
            return False
        logger.info("External cancel detected for run %s", self.run_id)
        await self._cancel_in_flight("cancelled", "Externally cancelled")
        self._mark_remaining_pending_as("cancelled", "Externally cancelled")
        return True

    # ------------------------------------------------------------------
    # Safety checks
    # ------------------------------------------------------------------

    def _check_circuit_breaker(self) -> bool:
        cfg = None
        if self.plan.orchestration and self.plan.orchestration.circuit_breaker:
            cfg = self.plan.orchestration.circuit_breaker
        if cfg is None:
            return False
        if self.failure_count < cfg.threshold:
            return False
        logger.warning(
            "Circuit breaker tripped: %d failures >= %d",
            self.failure_count,
            cfg.threshold,
        )
        with get_db(self.run_id, self.base_path) as db:
            insert_event(
                db,
                run_id=self.run_id,
                agent=None,
                event_type="circuit_breaker_tripped",
                data={
                    "failure_count": self.failure_count,
                    "threshold": cfg.threshold,
                    "action": cfg.action,
                },
            )
        if cfg.action in ("cancel_all", "pause"):
            status = "cancelled" if cfg.action == "cancel_all" else "paused"
            # Note: we don't persist "paused" on attempts because it's not a
            # valid terminal state; keep the attempt as cancelled so the run
            # cleanly exits.
            asyncio.get_event_loop().create_task(
                self._cancel_in_flight("cancelled", "Circuit breaker tripped")
            )
            self._mark_remaining_pending_as("cancelled", "Circuit breaker tripped")
            return True
        return False

    async def _check_cost_budget(self) -> bool:
        if not self.plan.cost_budget:
            return False
        with get_db(self.run_id, self.base_path) as db:
            total = get_total_cost(db, self.run_id)
        if total < self.plan.cost_budget.total_usd:
            return False
        action = self.plan.cost_budget.on_exceed
        logger.warning(
            "Cost budget exceeded: $%.2f >= $%.2f (action=%s)",
            total,
            self.plan.cost_budget.total_usd,
            action,
        )
        with get_db(self.run_id, self.base_path) as db:
            insert_event(
                db,
                run_id=self.run_id,
                agent=None,
                event_type="cost_exceeded",
                data={
                    "total": total,
                    "budget": self.plan.cost_budget.total_usd,
                    "action": action,
                },
            )
        if action == "warn":
            return False
        await self._cancel_in_flight("cost_exceeded", "Cost budget exceeded")
        self._mark_remaining_pending_as("cost_exceeded", "Cost budget exceeded")
        return True

    def _check_stuck(self) -> None:
        with get_db(self.run_id, self.base_path) as db:
            count = db.execute(
                "SELECT COUNT(*) FROM events WHERE run_id = ?",
                (self.run_id,),
            ).fetchone()[0]
        if count == self.last_event_count and self.in_flight:
            self.idle_iterations += 1
        else:
            self.idle_iterations = 0
        self.last_event_count = count
        threshold = STUCK_THRESHOLD_ITERATIONS
        if self.plan.orchestration and self.plan.orchestration.stuck_threshold is not None:
            threshold = self.plan.orchestration.stuck_threshold
        if self.idle_iterations >= threshold:
            with get_db(self.run_id, self.base_path) as db:
                insert_event(
                    db,
                    run_id=self.run_id,
                    agent=None,
                    event_type="stuck_detected",
                    data={"idle_iterations": self.idle_iterations},
                )
            self.idle_iterations = 0

    # ------------------------------------------------------------------
    # Result / cleanup
    # ------------------------------------------------------------------

    async def _release_all_workspaces(self, keep: bool) -> None:
        for handle in self.in_flight.values():
            try:
                await self.workspace_provider.release(handle.workspace, keep=keep)
            except Exception:  # noqa: BLE001
                logger.debug("workspace release failed", exc_info=True)

    def _build_result(self) -> SchedulerResult:
        completed: list[str] = []
        failed: list[str] = []
        with get_db(self.run_id, self.base_path) as db:
            nodes = get_nodes(db, self.run_id)
            for n in nodes:
                a = latest_attempt(db, self.run_id, n["name"])
                if a is None:
                    continue
                status = a["status"]
                if status == "completed":
                    completed.append(n["name"])
                elif status in TERMINAL_STATUSES:
                    failed.append(n["name"])
            total = get_total_cost(db, self.run_id)
        success = not failed and len(completed) == len(self.resolved_by_name)
        return SchedulerResult(
            run_id=self.run_id,
            success=success,
            completed=completed,
            failed=failed,
            total_cost=total,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _workspace_kind(workspace: Workspace) -> str:
    if isinstance(workspace, GitWorktree):
        return "worktree"
    if isinstance(workspace, TempDir):
        return "tempdir"
    return "cwd"


def _default_workspace_provider(base_path: Path) -> Any:
    from swarm.workspaces.git import GitWorktreeProvider

    return GitWorktreeProvider(repo_path=base_path)


def _resolved_from_row(row: sqlite3.Row) -> ResolvedAgent:
    """Rebuild a ResolvedAgent from a nodes-table row (used on spawn / resume)."""
    from swarm.core.agent import Limits
    from swarm.core.capabilities import Capability
    from swarm.core.profiles import get_profile

    profile = get_profile(row["profile"])
    env_dict = json.loads(row["env"] or "{}")
    output_schema = json.loads(row["output_schema"]) if row["output_schema"] else None
    depends_on = tuple(json.loads(row["depends_on"] or "[]"))
    caps = profile.capabilities  # we didn't persist per-agent overrides in nodes
    return ResolvedAgent(
        name=row["name"],
        prompt=row["prompt"],
        runtime=row["runtime"],
        model=row["model"],
        profile=profile,
        capabilities=caps,
        limits=Limits(
            max_iterations=row["max_iterations"],
            max_cost_usd=row["max_cost_usd"],
        ),
        check=row["check_command"],
        env=tuple(env_dict.items()),
        output_schema=output_schema,
        parent=row["parent"],
        tree_path=row["tree_path"],
        depends_on=depends_on,
        on_failure=row["on_failure"],
        retry_count=row["retry_count"],
    )


async def run_plan(
    plan: PlanSpec,
    resolved: list[ResolvedAgent] | None = None,
    *,
    run_id: str | None = None,
    resume: bool = False,
    base_path: Path | None = None,
    workspace_provider: Any | None = None,
) -> SchedulerResult:
    scheduler = Scheduler(
        plan,
        resolved,
        run_id=run_id,
        resume=resume,
        base_path=base_path,
        workspace_provider=workspace_provider,
    )
    return await scheduler.run()
