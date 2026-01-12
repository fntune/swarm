"""Git worktree management for claude-swarm."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("swarm.git")


class GitError(Exception):
    """Git operation failed."""

    pass


def run_git(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command."""
    cmd = ["git"] + args
    logger.debug(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise GitError(f"Git command failed: {result.stderr}")
    return result


def get_repo_root(cwd: Path | None = None) -> Path:
    """Get the root of the git repository."""
    result = run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    return Path(result.stdout.strip())


def get_default_branch(cwd: Path | None = None) -> str:
    """Detect the default branch (main or master)."""
    # Try to get from remote HEAD
    result = run_git(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=cwd, check=False)
    if result.returncode == 0:
        return result.stdout.strip().split("/")[-1]

    # Fallback: check if main or master exists
    for branch in ["main", "master"]:
        result = run_git(["rev-parse", "--verify", branch], cwd=cwd, check=False)
        if result.returncode == 0:
            return branch

    return "main"


def get_current_branch(cwd: Path | None = None) -> str:
    """Get current branch name."""
    result = run_git(["branch", "--show-current"], cwd=cwd)
    return result.stdout.strip()


def create_worktree(
    run_id: str,
    agent_name: str,
    repo_path: Path | None = None,
) -> Path:
    """Create a git worktree for an agent.

    Args:
        run_id: The run identifier
        agent_name: Name of the agent
        repo_path: Path to git repo (defaults to cwd)

    Returns:
        Path to the created worktree
    """
    repo = repo_path or Path.cwd()
    worktree_path = repo / ".swarm" / "runs" / run_id / "worktrees" / agent_name
    branch_name = f"swarm/{run_id}/{agent_name}"

    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    # Create worktree with new branch
    run_git(["worktree", "add", "-b", branch_name, str(worktree_path)], cwd=repo)
    logger.info(f"Created worktree at {worktree_path} on branch {branch_name}")

    return worktree_path


def remove_worktree(worktree_path: Path, repo_path: Path | None = None) -> None:
    """Remove a git worktree."""
    repo = repo_path or Path.cwd()
    run_git(["worktree", "remove", str(worktree_path), "--force"], cwd=repo)
    logger.info(f"Removed worktree at {worktree_path}")


def delete_branch(branch: str, repo_path: Path | None = None) -> None:
    """Delete a git branch."""
    repo = repo_path or Path.cwd()
    run_git(["branch", "-D", branch], cwd=repo)
    logger.info(f"Deleted branch {branch}")


def list_worktrees(repo_path: Path | None = None) -> list[dict]:
    """List all worktrees."""
    repo = repo_path or Path.cwd()
    result = run_git(["worktree", "list", "--porcelain"], cwd=repo)

    worktrees = []
    current = {}
    for line in result.stdout.strip().split("\n"):
        if not line:
            if current:
                worktrees.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            current["path"] = line[9:]
        elif line.startswith("HEAD "):
            current["head"] = line[5:]
        elif line.startswith("branch "):
            current["branch"] = line[7:]
        elif line == "bare":
            current["bare"] = True
        elif line == "detached":
            current["detached"] = True

    if current:
        worktrees.append(current)

    return worktrees


def merge_branch(
    worktree_path: Path,
    branch: str,
    message: str | None = None,
) -> bool:
    """Merge a branch into the worktree.

    Returns:
        True if merge succeeded, False if there were conflicts
    """
    msg = message or f"Merge {branch}"
    result = run_git(["merge", branch, "--no-edit", "-m", msg], cwd=worktree_path, check=False)

    if result.returncode != 0:
        if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
            logger.warning(f"Merge conflict merging {branch}")
            return False
        raise GitError(f"Merge failed: {result.stderr}")

    logger.info(f"Merged {branch} into {worktree_path}")
    return True


def get_changed_files(branch: str, base: str, repo_path: Path | None = None) -> list[str]:
    """Get files changed between base and branch."""
    repo = repo_path or Path.cwd()
    result = run_git(["diff", "--name-only", f"{base}...{branch}"], cwd=repo)
    return [f for f in result.stdout.strip().split("\n") if f]


def has_conflicts(worktree_path: Path) -> bool:
    """Check if worktree has unresolved conflicts."""
    result = run_git(["diff", "--name-only", "--diff-filter=U"], cwd=worktree_path, check=False)
    return bool(result.stdout.strip())


def abort_merge(worktree_path: Path) -> None:
    """Abort an in-progress merge."""
    run_git(["merge", "--abort"], cwd=worktree_path)


def commit(worktree_path: Path, message: str) -> None:
    """Create a commit in a worktree."""
    run_git(["add", "-A"], cwd=worktree_path)
    result = run_git(["diff", "--cached", "--quiet"], cwd=worktree_path, check=False)
    if result.returncode != 0:
        run_git(["commit", "-m", message], cwd=worktree_path)
        logger.info(f"Committed in {worktree_path}: {message}")
    else:
        logger.debug("Nothing to commit")


def setup_worktree_with_deps(
    run_id: str,
    agent_name: str,
    depends_on: list[str],
    worktree_path: Path,
    mode: str = "full",
    include_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
) -> None:
    """Merge dependency branches into agent's worktree.

    Args:
        run_id: The run identifier
        agent_name: Name of the agent
        depends_on: List of dependency agent names
        worktree_path: Path to the worktree
        mode: "full", "diff_only", or "paths"
        include_paths: Paths to include (for mode="paths")
        exclude_paths: Paths to exclude
    """
    repo = get_repo_root(worktree_path)

    for dep_name in depends_on:
        dep_branch = f"swarm/{run_id}/{dep_name}"

        if mode == "full":
            if not merge_branch(worktree_path, dep_branch, f"Merge {dep_name} dependency"):
                raise GitError(f"Conflict merging dependency {dep_name}")

        elif mode == "diff_only":
            base = get_default_branch(repo)
            changed_files = get_changed_files(dep_branch, base, repo)
            # Cherry-pick only changed files
            for file in changed_files:
                run_git(["checkout", dep_branch, "--", file], cwd=worktree_path, check=False)
            commit(worktree_path, f"Import changes from {dep_name}")

        elif mode == "paths":
            # Filter by include/exclude paths
            if not merge_branch(worktree_path, dep_branch, f"Merge {dep_name} dependency"):
                raise GitError(f"Conflict merging dependency {dep_name}")

    logger.info(f"Setup worktree with deps: {depends_on}")


def cleanup_run_worktrees(run_id: str, repo_path: Path | None = None) -> None:
    """Clean up all worktrees and branches for a run."""
    repo = repo_path or Path.cwd()
    worktrees = list_worktrees(repo)

    # Remove worktrees
    for wt in worktrees:
        if f".swarm/runs/{run_id}/worktrees" in wt.get("path", ""):
            remove_worktree(Path(wt["path"]), repo)

    # Delete branches
    result = run_git(["branch", "--list", f"swarm/{run_id}/*"], cwd=repo, check=False)
    for branch in result.stdout.strip().split("\n"):
        branch = branch.strip()
        if branch:
            delete_branch(branch, repo)

    logger.info(f"Cleaned up worktrees and branches for run {run_id}")
