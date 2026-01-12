"""Branch merging utilities for claude-swarm."""

import logging
import subprocess
from pathlib import Path

import json

from swarm.db import get_agents, open_db
from swarm.deps import DependencyGraph
from swarm.git import merge_branch_to_current, remove_worktree
from swarm.models import AgentSpec

logger = logging.getLogger("swarm.merge")


def get_merge_order(run_id: str) -> list[str]:
    """Get the order for merging agent branches.

    Args:
        run_id: Run identifier

    Returns:
        List of agent names in merge order
    """
    db = open_db(run_id)
    agents = get_agents(db, run_id)
    db.close()

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


def merge_run(run_id: str, cleanup: bool = True) -> dict:
    """Merge all completed agent branches for a run.

    Args:
        run_id: Run identifier
        cleanup: Remove worktrees after merge

    Returns:
        Dict with merge results
    """
    db = open_db(run_id)
    agents = get_agents(db, run_id)

    results = {
        "merged": [],
        "failed": [],
        "skipped": [],
    }

    # Get merge order
    order = get_merge_order(run_id)
    agent_map = {a["name"]: a for a in agents}

    for name in order:
        agent = agent_map.get(name)
        if not agent:
            results["skipped"].append(name)
            continue

        branch = agent.get("branch")
        if not branch:
            results["skipped"].append(name)
            continue

        try:
            merge_branch_to_current(branch)
            results["merged"].append(name)
            logger.info(f"Merged {name} ({branch})")

            # Cleanup worktree
            if cleanup:
                worktree = agent.get("worktree")
                if worktree:
                    try:
                        remove_worktree(Path(worktree))
                    except Exception as e:
                        logger.warning(f"Failed to remove worktree {worktree}: {e}")

        except Exception as e:
            results["failed"].append({"name": name, "error": str(e)})
            logger.error(f"Failed to merge {name}: {e}")

    db.close()
    return results


def check_conflicts(run_id: str) -> list[dict]:
    """Check for potential merge conflicts between agent branches.

    Args:
        run_id: Run identifier

    Returns:
        List of conflict info dicts
    """
    db = open_db(run_id)
    agents = get_agents(db, run_id)
    db.close()

    completed = [a for a in agents if a["status"] == "completed" and a.get("branch")]
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
    db = open_db(run_id)
    agents = get_agents(db, run_id)
    db.close()

    agent_map = {a["name"]: a for a in agents}

    for name in order:
        agent = agent_map.get(name)
        if not agent or not agent.get("branch"):
            continue

        branch = agent["branch"]
        print(f"\nMerging {name} ({branch})...")

        try:
            merge_branch(branch)
            print(f"  ✓ Merged successfully")
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Conflict detected")
            print(f"    Resolve conflicts and run: git merge --continue")
            print(f"    Or abort: git merge --abort")
            break
