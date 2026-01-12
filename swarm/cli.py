"""CLI for claude-swarm."""

import asyncio
import logging
from pathlib import Path

import click

from swarm.logs import list_logs, read_all_logs, read_log, setup_logging, tail_log
from swarm.models import Defaults
from swarm.parser import create_inline_plan, parse_plan_file, validate_plan
from swarm.scheduler import run_plan

logger = logging.getLogger("swarm.cli")


@click.group()
@click.version_option()
def main() -> None:
    """Claude Swarm - Multi-agent orchestration."""
    pass


@main.command()
@click.option("-f", "--file", "plan_file", type=click.Path(exists=True), help="Plan YAML file")
@click.option("-p", "--prompt", multiple=True, help="Inline agent prompts")
@click.option("--check", "check_cmd", default=None, help="Check command for inline prompts")
@click.option("--sequential", is_flag=True, help="Run agents sequentially")
@click.option("--mock", is_flag=True, help="Use mock workers (for testing)")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
def run(
    plan_file: str | None,
    prompt: tuple[str, ...],
    check_cmd: str | None,
    sequential: bool,
    mock: bool,
    verbose: bool,
) -> None:
    """Run a swarm plan."""
    if plan_file:
        plan = parse_plan_file(Path(plan_file))
    elif prompt:
        defaults = Defaults(check=check_cmd) if check_cmd else None
        plan = create_inline_plan(list(prompt), sequential=sequential, defaults=defaults)
    else:
        raise click.UsageError("Either --file or --prompt is required")

    # Validate
    errors = validate_plan(plan)
    if errors:
        for error in errors:
            click.echo(f"Error: {error}", err=True)
        raise click.Abort()

    # Set up logging
    from swarm.parser import generate_run_id
    run_id = generate_run_id(plan.name)
    setup_logging(run_id, verbose)

    click.echo(f"Starting run: {run_id}")
    click.echo(f"Agents: {[a.name for a in plan.agents]}")

    # Run
    result = asyncio.run(run_plan(plan, run_id, use_mock=mock))

    # Output result
    click.echo(f"\nRun completed: {result.run_id}")
    click.echo(f"Success: {result.success}")
    click.echo(f"Completed: {result.completed}")
    click.echo(f"Failed: {result.failed}")
    click.echo(f"Total cost: ${result.total_cost:.4f}")


@main.command()
@click.argument("run_id")
def status(run_id: str) -> None:
    """Show status of a run."""
    from swarm.db import get_agents, get_plan, open_db

    try:
        db = open_db(run_id)
    except FileNotFoundError:
        click.echo(f"Run not found: {run_id}", err=True)
        raise click.Abort()

    plan = get_plan(db, run_id)
    if not plan:
        click.echo(f"Plan not found for run: {run_id}", err=True)
        raise click.Abort()

    agents = get_agents(db, run_id)

    click.echo(f"Run: {run_id}")
    click.echo(f"Plan: {plan['name']}")
    click.echo(f"Status: {plan['status']}")
    click.echo(f"\nAgents:")

    for agent in agents:
        status_str = agent["status"]
        if agent["error"]:
            status_str += f" ({agent['error'][:50]})"
        click.echo(f"  {agent['name']}: {status_str}")

    db.close()


@main.command()
@click.argument("run_id")
@click.option("-a", "--agent", help="Specific agent name")
@click.option("-n", "--lines", type=int, help="Number of lines")
@click.option("-f", "--follow", is_flag=True, help="Follow log output")
@click.option("--all", "show_all", is_flag=True, help="Show all agent logs")
def logs(
    run_id: str,
    agent: str | None,
    lines: int | None,
    follow: bool,
    show_all: bool,
) -> None:
    """View logs for a run."""
    if show_all:
        content = read_all_logs(run_id)
        click.echo(content)
    elif agent:
        if follow:
            tail_log(run_id, agent, follow=True)
        else:
            content = read_log(run_id, agent, lines=lines)
            click.echo(content)
    else:
        # List available logs
        available = list_logs(run_id)
        if available:
            click.echo(f"Available logs for {run_id}:")
            for name in sorted(available):
                click.echo(f"  {name}")
        else:
            click.echo(f"No logs found for {run_id}")


@main.command()
@click.argument("run_id")
def cancel(run_id: str) -> None:
    """Cancel a running swarm."""
    from swarm.db import get_agents, open_db, update_agent_status, update_plan_status

    try:
        db = open_db(run_id)
    except FileNotFoundError:
        click.echo(f"Run not found: {run_id}", err=True)
        raise click.Abort()

    # Update plan status
    update_plan_status(db, run_id, "cancelled")

    # Cancel running agents
    agents = get_agents(db, run_id)
    cancelled = 0
    for agent in agents:
        if agent["status"] == "running":
            update_agent_status(db, run_id, agent["name"], "cancelled")
            cancelled += 1

    click.echo(f"Cancelled run {run_id}")
    click.echo(f"Agents cancelled: {cancelled}")

    db.close()


@main.command()
@click.argument("run_id")
@click.option("--dry-run", is_flag=True, help="Show what would be merged")
def merge(run_id: str, dry_run: bool) -> None:
    """Merge completed agent branches."""
    import json

    from swarm.db import get_agents, open_db
    from swarm.deps import DependencyGraph
    from swarm.git import merge_branch_to_current
    from swarm.models import AgentSpec

    try:
        db = open_db(run_id)
    except FileNotFoundError:
        click.echo(f"Run not found: {run_id}", err=True)
        raise click.Abort()

    agents = get_agents(db, run_id)

    # Filter completed agents
    completed = [a for a in agents if a["status"] == "completed"]
    if not completed:
        click.echo("No completed agents to merge")
        db.close()
        return

    # Build dependency graph for merge order
    specs = [
        AgentSpec(
            name=a["name"],
            prompt=a["prompt"],
            depends_on=json.loads(a["depends_on"]) if a["depends_on"] else [],
        )
        for a in completed
    ]
    graph = DependencyGraph(specs)

    try:
        merge_order = graph.topological_order()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        db.close()
        raise click.Abort()

    click.echo(f"Merge order: {merge_order}")

    if dry_run:
        click.echo("(dry run - no changes made)")
        db.close()
        return

    # Merge in order
    for name in merge_order:
        agent = next(a for a in completed if a["name"] == name)
        branch = agent["branch"]
        if branch:
            click.echo(f"Merging {name} ({branch})...")
            try:
                merge_branch_to_current(branch)
                click.echo(f"  Merged successfully")
            except Exception as e:
                click.echo(f"  Failed: {e}", err=True)

    db.close()


@main.command()
@click.argument("run_id")
def dashboard(run_id: str) -> None:
    """Show live dashboard for a run."""
    import time
    from swarm.db import get_agents, get_plan, get_total_cost, open_db

    try:
        db = open_db(run_id)
    except FileNotFoundError:
        click.echo(f"Run not found: {run_id}", err=True)
        raise click.Abort()

    try:
        while True:
            # Clear screen
            click.clear()

            plan = get_plan(db, run_id)
            agents = get_agents(db, run_id)
            cost = get_total_cost(db, run_id)

            click.echo(f"=== {run_id} ===")
            click.echo(f"Status: {plan['status'] if plan else 'unknown'}")
            click.echo(f"Cost: ${cost:.4f}")
            click.echo()

            # Status counts
            counts = {}
            for a in agents:
                counts[a["status"]] = counts.get(a["status"], 0) + 1
            click.echo(f"Agents: {counts}")
            click.echo()

            # Agent details
            for agent in agents:
                icon = {
                    "pending": "⏳",
                    "running": "🔄",
                    "completed": "✅",
                    "failed": "❌",
                    "cancelled": "🚫",
                    "paused": "⏸️",
                }.get(agent["status"], "?")
                click.echo(f"{icon} {agent['name']}: {agent['status']}")

            # Check if done
            all_done = all(a["status"] in ("completed", "failed", "cancelled") for a in agents)
            if all_done:
                click.echo("\nAll agents finished.")
                break

            time.sleep(2)

    except KeyboardInterrupt:
        click.echo("\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
