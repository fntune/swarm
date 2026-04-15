"""CLI for swarm.

Commands:
  swarm run        Execute a plan file or inline prompts
  swarm resume     Resume an existing run
  swarm status     Show node status for a run (latest attempt per node)
  swarm logs       View per-agent log files
  swarm merge      Merge completed agent branches
  swarm cancel     Cancel a running plan
  swarm dashboard  Live event tail for a run
  swarm clean      Delete run directories
  swarm db         Query the SQLite database
  swarm profiles   List / describe built-in profiles (renamed from `roles`)
"""

import asyncio
import json
import logging
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any

import click

# Register adapters at import time so `swarm run` can dispatch to any runtime
# without the CLI layer having to know about them. Claude + mock are always
# available; openai is conditional on the extra.
import swarm.adapters.claude  # noqa: F401
import swarm.adapters.mock  # noqa: F401
import swarm.adapters.openai  # noqa: F401
from swarm.batch.input import (
    build_inline_plan,
    generate_run_id,
    parse_plan_file,
)
from swarm.batch.logs import list_logs, read_all_logs, read_log, tail_log
from swarm.batch.merge import merge_run
from swarm.batch.plan import PlanDefaults, PlanSpec, resolve_plan
from swarm.batch.scheduler import run_plan
from swarm.batch.sqlite import (
    get_db,
    get_db_path,
    get_nodes,
    get_run_dir,
    get_total_cost,
    init_db,
    insert_event,
    latest_attempt,
    list_runs,
    run_exists,
    update_attempt_status,
)
from swarm.core.errors import MergeConflictError, SwarmError
from swarm.core.execution import list_runtimes
from swarm.core.profiles import PROFILE_REGISTRY, get_profile

logger = logging.getLogger("swarm.cli")


@click.group()
@click.version_option()
def main() -> None:
    """Swarm — multi-agent orchestration for Claude + OpenAI."""


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@main.command("run")
@click.option("-f", "--file", "plan_file", type=click.Path(exists=True), help="Plan YAML file")
@click.option("-p", "--prompt", multiple=True, help="Inline agent prompts (name: text or just text)")
@click.option("--check", "check_cmd", default=None, help="Check command for inline prompts")
@click.option("--sequential", is_flag=True, help="Run inline agents in a chain")
@click.option("--run-id", "run_id_opt", default=None, help="Explicit run ID")
@click.option("--resume", is_flag=True, help="Resume existing run")
@click.option("--mock", is_flag=True, help="Force the mock runtime for all agents (implies --workspace=cwd)")
@click.option(
    "--workspace",
    type=click.Choice(["worktree", "cwd", "tempdir"]),
    default=None,
    help="Workspace strategy (default: worktree, mock implies cwd)",
)
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
def run_command(
    plan_file: str | None,
    prompt: tuple[str, ...],
    check_cmd: str | None,
    sequential: bool,
    run_id_opt: str | None,
    resume: bool,
    mock: bool,
    workspace: str | None,
    verbose: bool,
) -> None:
    """Execute a plan."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if resume:
        if not run_id_opt:
            raise click.UsageError("--resume requires --run-id")
        if not run_exists(run_id_opt):
            raise click.UsageError(f"Run not found: {run_id_opt}")
        _run_resume(run_id_opt)
        return

    plan = _build_plan(plan_file, prompt, check_cmd, sequential, mock)
    try:
        resolved = resolve_plan(plan)
    except SwarmError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.Abort() from exc

    run_id = run_id_opt or generate_run_id(plan.name)
    click.echo(f"Starting run: {run_id}")
    click.echo(f"Agents: {[a.name for a in plan.agents]}")

    workspace_choice = workspace or ("cwd" if mock else "worktree")
    provider = _build_workspace_provider(workspace_choice)

    result = asyncio.run(
        run_plan(plan, resolved, run_id=run_id, workspace_provider=provider)
    )

    click.echo(f"\nRun finished: {result.run_id}")
    click.echo(f"Success: {result.success}")
    click.echo(f"Completed: {result.completed}")
    click.echo(f"Failed: {result.failed}")
    click.echo(f"Total cost: ${result.total_cost:.4f}")


def _build_plan(
    plan_file: str | None,
    prompts: tuple[str, ...],
    check_cmd: str | None,
    sequential: bool,
    mock: bool,
) -> PlanSpec:
    if plan_file:
        plan = parse_plan_file(Path(plan_file))
        if mock:
            plan = _force_runtime(plan, "mock")
        return plan
    if prompts:
        defaults = PlanDefaults(
            runtime="mock" if mock else None,
            check=check_cmd or "true",
        )
        return build_inline_plan(list(prompts), sequential=sequential, defaults=defaults)
    raise click.UsageError("Either --file or --prompt is required")


def _force_runtime(plan: PlanSpec, runtime: str) -> PlanSpec:
    from dataclasses import replace

    defaults = replace(plan.defaults, runtime=runtime)  # type: ignore[arg-type]
    agents = tuple(replace(a, runtime=runtime) for a in plan.agents)  # type: ignore[arg-type]
    return replace(plan, defaults=defaults, agents=agents)


def _build_workspace_provider(kind: str):
    if kind == "cwd":
        from swarm.workspaces.cwd import CwdProvider

        return CwdProvider()
    if kind == "tempdir":
        from swarm.workspaces.temp import TempDirProvider

        return TempDirProvider()
    from swarm.workspaces.git import GitWorktreeProvider

    return GitWorktreeProvider()


def _run_resume(run_id: str) -> None:
    # Build a synthetic PlanSpec from the nodes table so the Scheduler has
    # something to hang its config on. Resume walks the DB for the real
    # state.
    with get_db(run_id) as db:
        nodes = get_nodes(db, run_id)
    if not nodes:
        raise click.UsageError(f"No nodes found for run {run_id}")
    plan_name = nodes[0]["plan_name"]
    plan = PlanSpec(name=plan_name, agents=())
    click.echo(f"Resuming run: {run_id}")
    result = asyncio.run(run_plan(plan, None, run_id=run_id, resume=True))
    click.echo(f"\nRun finished: {result.run_id}")
    click.echo(f"Success: {result.success}")
    click.echo(f"Completed: {result.completed}")
    click.echo(f"Failed: {result.failed}")
    click.echo(f"Total cost: ${result.total_cost:.4f}")


# ---------------------------------------------------------------------------
# resume
# ---------------------------------------------------------------------------


@main.command("resume")
@click.argument("run_id")
@click.option("-v", "--verbose", is_flag=True)
def resume_command(run_id: str, verbose: bool) -> None:
    """Resume a previous run (alias for `run --resume --run-id <id>`)."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    if not run_exists(run_id):
        click.echo(f"Run not found: {run_id}", err=True)
        raise click.Abort()
    _run_resume(run_id)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@main.command("status")
@click.argument("run_id", required=False)
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def status_command(run_id: str | None, as_json: bool) -> None:
    """Show node status for a run."""
    run_id = _resolve_run_id(run_id)
    try:
        with get_db(run_id) as db:
            nodes = get_nodes(db, run_id)
            total = get_total_cost(db, run_id)
            rows: list[dict[str, Any]] = []
            for n in nodes:
                attempt = latest_attempt(db, run_id, n["name"])
                rows.append(
                    {
                        "name": n["name"],
                        "runtime": n["runtime"],
                        "profile": n["profile"],
                        "status": attempt["status"] if attempt else "pending",
                        "attempt": attempt["attempt_number"] if attempt else 0,
                        "iteration": attempt["iteration"] if attempt else 0,
                        "max_iterations": n["max_iterations"],
                        "cost": attempt["cost_usd"] if attempt else 0.0,
                        "error": attempt["error"] if attempt else None,
                    }
                )
    except FileNotFoundError as exc:
        click.echo(f"Run not found: {run_id}", err=True)
        raise click.Abort() from exc

    if as_json:
        click.echo(json.dumps({"run_id": run_id, "total_cost": total, "nodes": rows}, indent=2))
        return

    click.echo(f"Run: {run_id}")
    click.echo(f"Cost: ${total:.4f}")
    click.echo("\nNodes:")
    for r in rows:
        line = (
            f"  {r['name']} [{r['runtime']}/{r['profile']}] "
            f"{r['status']} (attempt {r['attempt']}, iter {r['iteration']}/{r['max_iterations']})"
        )
        if r["error"]:
            line += f" err={str(r['error'])[:60]}"
        click.echo(line)


def _resolve_run_id(run_id: str | None) -> str:
    if run_id:
        return run_id
    runs = list_runs()
    if not runs:
        click.echo("No runs found", err=True)
        raise click.Abort()
    return runs[0]


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------


@main.command("logs")
@click.argument("run_id")
@click.option("-a", "--agent", help="Specific agent")
@click.option("-n", "--lines", type=int, help="Tail N lines")
@click.option("-f", "--follow", is_flag=True, help="Follow")
@click.option("--all", "show_all", is_flag=True, help="All agents concatenated")
def logs_command(
    run_id: str,
    agent: str | None,
    lines: int | None,
    follow: bool,
    show_all: bool,
) -> None:
    """View per-agent log files."""
    if show_all:
        click.echo(read_all_logs(run_id))
        return
    if agent:
        if follow:
            tail_log(run_id, agent, follow=True)
        else:
            click.echo(read_log(run_id, agent, lines=lines))
        return
    names = list_logs(run_id)
    if not names:
        click.echo(f"No logs for {run_id}")
        return
    click.echo(f"Available logs for {run_id}:")
    for name in names:
        click.echo(f"  {name}")


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------


@main.command("merge")
@click.argument("run_id")
@click.option(
    "--strategy",
    type=click.Choice(["manual", "fail", "auto"]),
    default="manual",
    help="Conflict handling (auto raises MergeConflictError since spawn_resolver is gone)",
)
@click.option("--dry-run", is_flag=True)
def merge_command(run_id: str, strategy: str, dry_run: bool) -> None:
    """Merge completed agent branches."""
    if dry_run:
        from swarm.batch.merge import get_merge_order

        click.echo(f"Merge order: {get_merge_order(run_id)}")
        click.echo("(dry run — no changes made)")
        return
    try:
        result = merge_run(run_id, on_conflict=strategy)  # type: ignore[arg-type]
    except MergeConflictError as exc:
        click.echo(f"Merge aborted: {exc}", err=True)
        raise click.Abort() from exc
    click.echo(f"Merged: {result['merged']}")
    if result.get("failed"):
        click.echo(f"Failed: {result['failed']}", err=True)
    if result.get("skipped"):
        click.echo(f"Skipped: {result['skipped']}")


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


@main.command("cancel")
@click.argument("run_id")
def cancel_command(run_id: str) -> None:
    """Cancel a running plan."""
    if not run_exists(run_id):
        click.echo(f"Run not found: {run_id}", err=True)
        raise click.Abort()
    with get_db(run_id) as db:
        insert_event(
            db,
            run_id=run_id,
            agent=None,
            event_type="plan_cancel",
            data={"source": "cli"},
        )
        for node in get_nodes(db, run_id):
            attempt = latest_attempt(db, run_id, node["name"])
            if attempt and attempt["status"] in ("pending", "running", "blocked"):
                update_attempt_status(
                    db, attempt["attempt_id"], "cancelled", "Cancelled via CLI"
                )
    click.echo(f"Cancelled run {run_id}")


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------


@main.command("dashboard")
@click.argument("run_id")
def dashboard_command(run_id: str) -> None:
    """Live status view — refreshes every 2s until the run is done."""
    if not run_exists(run_id):
        click.echo(f"Run not found: {run_id}", err=True)
        raise click.Abort()
    icons = {
        "pending": "o",
        "running": ">",
        "blocked": "!",
        "completed": "+",
        "failed": "x",
        "cancelled": "-",
        "cost_exceeded": "$",
        "timeout": "~",
    }
    try:
        while True:
            click.clear()
            with get_db(run_id) as db:
                nodes = get_nodes(db, run_id)
                cost = get_total_cost(db, run_id)
                statuses = []
                counts: dict[str, int] = {}
                for n in nodes:
                    a = latest_attempt(db, run_id, n["name"])
                    s = a["status"] if a else "pending"
                    statuses.append((n["name"], s, a["iteration"] if a else 0, n["max_iterations"]))
                    counts[s] = counts.get(s, 0) + 1
            click.echo(f"=== {run_id} ===")
            click.echo(f"Cost: ${cost:.4f}")
            click.echo(f"Agents: {counts}")
            click.echo()
            for name, status, itr, mx in statuses:
                icon = icons.get(status, "?")
                click.echo(f"{icon} {name}: {status} (iter {itr}/{mx})")
            if all(s[1] in ("completed", "failed", "cancelled", "cost_exceeded", "timeout") for s in statuses):
                click.echo("\nAll agents finished.")
                return
            time.sleep(2)
    except KeyboardInterrupt:
        click.echo("\n")


# ---------------------------------------------------------------------------
# clean
# ---------------------------------------------------------------------------


@main.command("clean")
@click.argument("run_id", required=False)
@click.option("--all", "clean_all", is_flag=True)
def clean_command(run_id: str | None, clean_all: bool) -> None:
    """Delete run directories and their artifacts."""
    if clean_all:
        runs = list_runs()
        for rid in runs:
            d = get_run_dir(rid)
            if d.exists():
                shutil.rmtree(d)
                click.echo(f"Cleaned: {rid}")
        click.echo(f"Cleaned {len(runs)} runs")
        return
    if not run_id:
        raise click.UsageError("Provide a run_id or use --all")
    d = get_run_dir(run_id)
    if not d.exists():
        click.echo(f"Run not found: {run_id}", err=True)
        raise click.Abort()
    shutil.rmtree(d)
    click.echo(f"Cleaned: {run_id}")


# ---------------------------------------------------------------------------
# db
# ---------------------------------------------------------------------------


@main.command("db")
@click.argument("run_id", required=False)
@click.argument("query", required=False)
def db_command(run_id: str | None, query: str | None) -> None:
    """Query the SQLite database for a run.

    Tables: nodes, attempts, workspaces, events, coord_responses.
    """
    if not run_id:
        runs = list_runs()
        if not runs:
            click.echo("No runs found")
            return
        click.echo("Available runs:")
        for rid in runs[:10]:
            click.echo(f"  {rid}")
        if len(runs) > 10:
            click.echo(f"  ... and {len(runs) - 10} more")
        return
    path = get_db_path(run_id)
    if not path.exists():
        click.echo(f"Run not found: {run_id}", err=True)
        raise click.Abort()
    if not query:
        click.echo(f"Database: {path}")
        click.echo("Tables: nodes, attempts, workspaces, events, coord_responses")
        click.echo('Usage: swarm db <run_id> "SELECT * FROM nodes"')
        return
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        if not rows:
            click.echo("No results")
            return
        cols = [d[0] for d in cursor.description]
        click.echo("\t".join(cols))
        click.echo("-" * 60)
        for r in rows:
            click.echo("\t".join(str(v) for v in r))
    except sqlite3.Error as exc:
        click.echo(f"Query error: {exc}", err=True)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# profiles (renamed from roles — clean break, no alias)
# ---------------------------------------------------------------------------


@main.command("profiles")
@click.argument("name", required=False)
def profiles_command(name: str | None) -> None:
    """List built-in agent profiles, or describe one in detail."""
    if name:
        try:
            profile = get_profile(name)
        except KeyError as exc:
            click.echo(f"Profile not found: {name}", err=True)
            click.echo(f"Available: {', '.join(sorted(PROFILE_REGISTRY))}")
            raise click.Abort() from exc
        click.echo(f"Profile: {profile.name}")
        click.echo(f"Description: {profile.description}")
        click.echo(f"Read-only: {profile.read_only}")
        click.echo(
            f"Capabilities: {sorted(c.value for c in profile.capabilities)}"
        )
        click.echo(f"Coord ops: {sorted(profile.coord_ops)}")
        if profile.default_model:
            click.echo(f"Default model: {profile.default_model}")
        if profile.default_check:
            click.echo(f"Default check: {profile.default_check}")
        click.echo(f"\nPrompt preamble:\n{profile.prompt_preamble}")
        return
    click.echo("Available profiles:")
    for profile in PROFILE_REGISTRY.values():
        readonly = " [read-only]" if profile.read_only else ""
        click.echo(f"  {profile.name}{readonly}: {profile.description}")
    click.echo(f"\nRegistered runtimes: {list_runtimes()}")


if __name__ == "__main__":
    main()
