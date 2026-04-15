"""Branch consolidation for batch runs.

Ported from the old swarm/gitops/merge.py. The key behavior change:
`spawn_resolver` is gone. `merge --strategy auto` (on_conflict='fail') now
raises MergeConflictError on conflict instead of spawning a Claude agent
to fix it. Users get a clear message telling them to rerun with
`--strategy manual` or resolve by hand.

Merge order comes from the dependency DAG of completed nodes; branches
come from the workspaces table.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Literal

from swarm.batch.dag import DependencyGraph
from swarm.batch.sqlite import get_db, get_nodes, get_workspace, latest_attempt
from swarm.core.errors import MergeConflictError
from swarm.workspaces.git import merge_branch_to_current, remove_worktree

logger = logging.getLogger("swarm.batch.merge")

OnConflict = Literal["auto", "fail", "manual"]


def _completed_with_branches(run_id: str) -> list[dict]:
    out: list[dict] = []
    with get_db(run_id) as db:
        for node in get_nodes(db, run_id):
            attempt = latest_attempt(db, run_id, node["name"])
            if attempt is None or attempt["status"] != "completed":
                continue
            workspace_id = attempt["workspace_id"]
            if not workspace_id:
                continue
            ws = get_workspace(db, workspace_id)
            if ws is None or not ws["branch"]:
                continue
            out.append(
                {
                    "name": node["name"],
                    "branch": ws["branch"],
                    "depends_on": json.loads(node["depends_on"]),
                    "workspace_path": ws["path"],
                }
            )
    return out


def get_merge_order(run_id: str) -> list[str]:
    completed = _completed_with_branches(run_id)
    if not completed:
        return []
    deps = {n["name"]: set(n["depends_on"]) for n in completed}
    # Drop deps that aren't in the completed set so the graph stays closed.
    names = set(deps)
    deps = {n: (d & names) for n, d in deps.items()}
    return DependencyGraph(deps).topological_order()


def _get_conflict_files(cwd: Path | None = None) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.strip().split("\n") if f]


def merge_run(
    run_id: str,
    *,
    cleanup: bool = True,
    on_conflict: OnConflict = "manual",
    repo_path: Path | None = None,
) -> dict:
    """Merge all completed agent branches for a run.

    Strategy values:
    - 'manual' (default): on conflict, leave the repo mid-merge and record
      the failure in the result dict; the user resolves by hand.
    - 'fail': on conflict, abort the merge and record the failure.
    - 'auto': same as 'fail' for this release. spawn_resolver is gone;
      the old auto path raised MergeConflictError pointing users at manual.
    """
    repo = repo_path or Path.cwd()
    order = get_merge_order(run_id)
    by_name = {n["name"]: n for n in _completed_with_branches(run_id)}

    results = {
        "merged": [],
        "failed": [],
        "skipped": [],
    }

    for name in order:
        node = by_name.get(name)
        if node is None:
            results["skipped"].append(name)
            continue

        branch = node["branch"]
        try:
            success = merge_branch_to_current(branch, repo_path=repo)
        except Exception as exc:  # noqa: BLE001
            results["failed"].append({"name": name, "error": str(exc)})
            logger.error("Merge failed for %s: %s", name, exc)
            continue

        if success:
            results["merged"].append(name)
            logger.info("Merged %s (%s)", name, branch)
            if cleanup and node["workspace_path"]:
                try:
                    remove_worktree(Path(node["workspace_path"]), repo_path=repo)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to remove worktree %s: %s",
                        node["workspace_path"],
                        exc,
                    )
            continue

        # Conflict path
        conflict_files = _get_conflict_files(repo)
        logger.warning("Merge conflict for %s: %s", name, conflict_files)

        if on_conflict == "auto":
            subprocess.run(
                ["git", "merge", "--abort"],
                cwd=str(repo),
                capture_output=True,
            )
            raise MergeConflictError(
                f"Auto-resolve is no longer supported. Conflict merging {branch!r}:\n"
                f"  files: {conflict_files}\n"
                f"  Rerun `swarm merge {run_id} --strategy manual` and resolve by hand."
            )

        if on_conflict == "fail":
            subprocess.run(
                ["git", "merge", "--abort"],
                cwd=str(repo),
                capture_output=True,
            )
            results["failed"].append(
                {"name": name, "error": "conflict", "files": conflict_files}
            )
            continue

        # manual: leave the repo mid-merge and stop processing the queue
        results["failed"].append(
            {"name": name, "error": "conflict_manual", "files": conflict_files}
        )
        break

    return results


def check_conflicts(run_id: str, repo_path: Path | None = None) -> list[dict]:
    """Pairwise pre-flight conflict check using git merge-tree.

    Returns a list of {agents, branches} dicts; empty list means no
    predicted conflicts.
    """
    completed = _completed_with_branches(run_id)
    conflicts: list[dict] = []
    for i, a in enumerate(completed):
        for b in completed[i + 1 :]:
            result = subprocess.run(
                ["git", "merge-tree", "HEAD", a["branch"], b["branch"]],
                cwd=str(repo_path) if repo_path else None,
                capture_output=True,
                text=True,
            )
            if "<<<<<<" in result.stdout or ">>>>>>>" in result.stdout:
                conflicts.append(
                    {
                        "agents": [a["name"], b["name"]],
                        "branches": [a["branch"], b["branch"]],
                    }
                )
    return conflicts
