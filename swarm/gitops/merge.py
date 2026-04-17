"""Branch merging utilities for claude-swarm."""

import asyncio
import concurrent.futures
import json
import logging
import subprocess
from pathlib import Path
from typing import Literal

from swarm.storage.db import get_agents, get_db, insert_agent, update_agent_status
from swarm.core.deps import DependencyGraph
from swarm.runtime.executor import AgentConfig
from swarm.gitops.worktrees import merge_branch_to_current, remove_worktree
from swarm.models.specs import AgentSpec

logger = logging.getLogger("swarm.merge")


def get_merge_order(run_id: str) -> list[str]:
    """Get the order for merging agent branches.

    Args:
        run_id: Run identifier

    Returns:
        List of agent names in merge order
    """
    with get_db(run_id) as db:
        agents = get_agents(db, run_id)

    # Build specs for completed agents
    completed = [a for a in agents if a["status"] == "completed"]
    if not completed:
        return []

    specs = [
        AgentSpec(
            name=a["name"],
            prompt=a["prompt"],
            depends_on=json.loads(a["depends_on"]) if a["depends_on"] else [],
        )
        for a in completed
    ]

    graph = DependencyGraph(specs)
    return graph.topological_order()


def spawn_resolver(
    run_id: str,
    branch: str,
    conflict_files: list[str],
    timeout: int = 120,
    max_cost: float = 2.0,
) -> bool:
    """Spawn a resolver agent to fix merge conflicts.

    Args:
        run_id: Run identifier
        branch: Branch being merged
        conflict_files: List of files with conflicts
        timeout: Max time in seconds
        max_cost: Max cost in USD

    Returns:
        True if resolved successfully
    """
    # Validate inputs
    if not conflict_files:
        logger.warning("spawn_resolver called with empty conflict_files list")
        return False

    # Use full branch path to avoid name collisions
    resolver_name = f"resolver-{branch.replace('/', '-')}"
    conflict_list = "\n".join(f"- {f}" for f in conflict_files)
    prompt = f"""Resolve merge conflicts in the following files:

{conflict_list}

The current branch is being merged with {branch}.
Review each conflict marker (<<<<<<< HEAD, =======, >>>>>>> {branch}) and resolve appropriately.
After resolving, stage the files with git add.

Do NOT run git merge --continue - that will be handled automatically."""

    # Insert resolver agent
    with get_db(run_id) as db:
        insert_agent(
            db,
            run_id,
            resolver_name,
            prompt,
            agent_type="worker",
            model="sonnet",
            max_iterations=10,
            max_cost_usd=max_cost,
        )

    # Run the resolver
    try:
        from swarm.runtime.executor import run_worker

        config = AgentConfig(
            name=resolver_name,
            run_id=run_id,
            prompt=prompt,
            worktree=Path.cwd(),
            model="sonnet",
            max_iterations=10,
            max_cost_usd=max_cost,
        )

        async def run_with_timeout():
            return await asyncio.wait_for(run_worker(config), timeout=timeout)

        # Handle case where event loop may already be running
        try:
            asyncio.get_running_loop()
            # Already in async context - use thread pool
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(asyncio.run, run_with_timeout()).result()
        except RuntimeError:
            # No running loop - safe to use asyncio.run
            result = asyncio.run(run_with_timeout())

        if result.get("success"):
            # Check if conflicts are resolved
            conflict_check = subprocess.run(
                ["git", "diff", "--check"],
                capture_output=True,
                text=True,
            )
            if conflict_check.returncode == 0:
                logger.info(f"Resolver {resolver_name} resolved conflicts")
                return True
            else:
                logger.warning(f"Resolver {resolver_name} completed but conflicts remain")
                return False
        else:
            logger.error(f"Resolver {resolver_name} failed: {result.get('error', 'unknown')}")
            return False

    except ImportError:
        logger.warning("SDK not available for resolver, falling back to manual")
        return False
    except asyncio.TimeoutError:
        logger.error(f"Resolver {resolver_name} timed out after {timeout}s")
        with get_db(run_id) as db:
            update_agent_status(db, run_id, resolver_name, "failed", "timeout")
        return False
    except Exception as e:
        logger.error(f"Resolver {resolver_name} error: {e}")
        # Update agent status on failure
        try:
            with get_db(run_id) as db:
                update_agent_status(db, run_id, resolver_name, "failed", str(e)[:100])
        except Exception as db_err:
            logger.warning(f"Failed to update resolver status in DB: {db_err}")
        return False


def get_conflict_files() -> list[str]:
    """Get list of files with merge conflicts."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return [f for f in result.stdout.strip().split("\n") if f]
    return []


def merge_run(
    run_id: str,
    cleanup: bool = True,
    on_conflict: Literal["spawn_resolver", "fail", "manual"] = "manual",
    resolver_timeout: int = 120,
    resolver_max_cost: float = 2.0,
) -> dict:
    """Merge all completed agent branches for a run.

    Args:
        run_id: Run identifier
        cleanup: Remove worktrees after merge
        on_conflict: How to handle conflicts (spawn_resolver, fail, manual)
        resolver_timeout: Timeout for resolver agent in seconds
        resolver_max_cost: Max cost for resolver agent in USD

    Returns:
        Dict with merge results
    """
    with get_db(run_id) as db:
        agents = get_agents(db, run_id)

    results = {
        "merged": [],
        "failed": [],
        "skipped": [],
        "resolved": [],
    }

    # Get merge order
    order = get_merge_order(run_id)
    agent_map = {a["name"]: a for a in agents}

    for name in order:
        agent = agent_map.get(name)
        if not agent:
            results["skipped"].append(name)
            continue

        branch = agent["branch"]
        if not branch:
            results["skipped"].append(name)
            continue

        try:
            merged = merge_branch_to_current(branch)
            if not merged:
                conflict_files = get_conflict_files()
                logger.warning(f"Merge conflict for {name}: {conflict_files}")

                if on_conflict == "spawn_resolver":
                    logger.info(f"Spawning resolver for {name}")
                    if spawn_resolver(run_id, branch, conflict_files, resolver_timeout, resolver_max_cost):
                        # Resolver succeeded, continue merge
                        try:
                            subprocess.run(["git", "add", "."], check=True, capture_output=True)
                            subprocess.run(
                                ["git", "commit", "-m", f"Resolve conflicts from {branch}"],
                                check=True,
                                capture_output=True,
                            )
                            results["resolved"].append(name)
                            logger.info(f"Resolved and merged {name}")

                            if cleanup:
                                worktree = agent["worktree"]
                                if worktree:
                                    try:
                                        remove_worktree(Path(worktree))
                                    except Exception as cleanup_err:
                                        logger.warning(f"Failed to remove worktree {worktree}: {cleanup_err}")
                            continue
                        except subprocess.CalledProcessError as commit_err:
                            logger.error(f"Failed to commit resolved conflicts: {commit_err}")
                            subprocess.run(["git", "merge", "--abort"], capture_output=True)
                            results["failed"].append({"name": name, "error": "commit_failed", "files": conflict_files})
                            continue

                    subprocess.run(["git", "merge", "--abort"], capture_output=True)
                    results["failed"].append({"name": name, "error": "resolver_failed", "files": conflict_files})
                    continue

                if on_conflict == "fail":
                    subprocess.run(["git", "merge", "--abort"], capture_output=True)
                    results["failed"].append({"name": name, "error": "conflict", "files": conflict_files})
                    logger.error(f"Merge conflict for {name}, aborting (on_conflict=fail)")
                    continue

                results["failed"].append({"name": name, "error": "conflict_manual", "files": conflict_files})
                logger.warning(f"Merge conflict for {name}, leaving for manual resolution")
                # Don't abort - leave in conflict state for manual resolution
                break

            results["merged"].append(name)
            logger.info(f"Merged {name} ({branch})")

            # Cleanup worktree
            if cleanup:
                worktree = agent["worktree"]
                if worktree:
                    try:
                        remove_worktree(Path(worktree))
                    except Exception as e:
                        logger.warning(f"Failed to remove worktree {worktree}: {e}")

        except Exception as e:
            # Check if this is a merge conflict
            conflict_files = get_conflict_files()
            if conflict_files:
                logger.warning(f"Merge conflict for {name}: {conflict_files}")

                if on_conflict == "spawn_resolver":
                    logger.info(f"Spawning resolver for {name}")
                    if spawn_resolver(run_id, branch, conflict_files, resolver_timeout, resolver_max_cost):
                        # Resolver succeeded, continue merge
                        try:
                            subprocess.run(["git", "add", "."], check=True, capture_output=True)
                            subprocess.run(
                                ["git", "commit", "-m", f"Resolve conflicts from {branch}"],
                                check=True,
                                capture_output=True,
                            )
                            results["resolved"].append(name)
                            logger.info(f"Resolved and merged {name}")

                            if cleanup:
                                worktree = agent["worktree"]
                                if worktree:
                                    try:
                                        remove_worktree(Path(worktree))
                                    except Exception as cleanup_err:
                                        logger.warning(f"Failed to remove worktree {worktree}: {cleanup_err}")
                            continue
                        except subprocess.CalledProcessError as commit_err:
                            logger.error(f"Failed to commit resolved conflicts: {commit_err}")
                            subprocess.run(["git", "merge", "--abort"], capture_output=True)
                            results["failed"].append({"name": name, "error": "commit_failed", "files": conflict_files})
                    else:
                        # Resolver failed, abort and record failure
                        subprocess.run(["git", "merge", "--abort"], capture_output=True)
                        results["failed"].append({"name": name, "error": "resolver_failed", "files": conflict_files})

                elif on_conflict == "fail":
                    subprocess.run(["git", "merge", "--abort"], capture_output=True)
                    results["failed"].append({"name": name, "error": "conflict", "files": conflict_files})
                    logger.error(f"Merge conflict for {name}, aborting (on_conflict=fail)")

                else:  # manual
                    results["failed"].append({"name": name, "error": "conflict_manual", "files": conflict_files})
                    logger.warning(f"Merge conflict for {name}, leaving for manual resolution")
                    # Don't abort - leave in conflict state for manual resolution
                    break
            else:
                # Non-conflict merge failure - abort to clean up state
                subprocess.run(["git", "merge", "--abort"], capture_output=True)
                results["failed"].append({"name": name, "error": str(e)})
                logger.error(f"Failed to merge {name}: {e}")

    return results


def check_conflicts(run_id: str) -> list[dict]:
    """Check for potential merge conflicts between agent branches.

    Args:
        run_id: Run identifier

    Returns:
        List of conflict info dicts
    """
    with get_db(run_id) as db:
        agents = get_agents(db, run_id)

    completed = [a for a in agents if a["status"] == "completed" and a["branch"]]
    conflicts = []

    # Check each pair
    for i, a1 in enumerate(completed):
        for a2 in completed[i + 1:]:
            # Use git merge-tree to check for conflicts
            try:
                result = subprocess.run(
                    ["git", "merge-tree", "HEAD", a1["branch"], a2["branch"]],
                    capture_output=True,
                    text=True,
                )
                if "<<<<<<" in result.stdout or ">>>>>>>" in result.stdout:
                    conflicts.append({
                        "agents": [a1["name"], a2["name"]],
                        "branches": [a1["branch"], a2["branch"]],
                    })
            except Exception as e:
                logger.warning(f"Failed to check conflicts between {a1['name']} and {a2['name']}: {e}")

    return conflicts


def squash_merge(branch: str, message: str | None = None) -> None:
    """Squash merge a branch into current branch.

    Args:
        branch: Branch name to merge
        message: Commit message (defaults to branch name)
    """
    msg = message or f"Squash merge {branch}"

    subprocess.run(
        ["git", "merge", "--squash", branch],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", msg],
        check=True,
        capture_output=True,
    )


def interactive_merge(run_id: str) -> None:
    """Interactive merge with conflict resolution.

    Args:
        run_id: Run identifier
    """
    order = get_merge_order(run_id)
    with get_db(run_id) as db:
        agents = get_agents(db, run_id)

    agent_map = {a["name"]: a for a in agents}

    for name in order:
        agent = agent_map.get(name)
        if not agent or not agent["branch"]:
            continue

        branch = agent["branch"]
        print(f"\nMerging {name} ({branch})...")

        try:
            if not merge_branch_to_current(branch):
                raise subprocess.CalledProcessError(1, f"git merge {branch}")
            print("  ✓ Merged successfully")
        except subprocess.CalledProcessError:
            print("  ✗ Conflict detected")
            print("    Resolve conflicts and run: git merge --continue")
            print("    Or abort: git merge --abort")
            break
