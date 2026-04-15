"""Git-worktree workspace provider.

Wraps the subprocess-based git logic from the old swarm/gitops/worktrees.py
and exposes it as a WorkspaceProvider. The low-level helpers
(run_git, create_worktree, etc.) move over in full because batch/merge.py
still needs them in commit 5.
"""

import logging
import subprocess
from pathlib import Path
from uuid import uuid4

from swarm.core.errors import WorkspaceError
from swarm.core.workspace import GitWorktree, Workspace

logger = logging.getLogger("swarm.workspaces.git")


class GitError(WorkspaceError):
    pass


def run_git(
    args: list[str],
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    cmd = ["git"] + args
    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise GitError(f"Git command failed: {result.stderr}")
    return result


def get_repo_root(cwd: Path | None = None) -> Path:
    result = run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    return Path(result.stdout.strip())


def get_default_branch(cwd: Path | None = None) -> str:
    result = run_git(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=cwd, check=False)
    if result.returncode == 0:
        return result.stdout.strip().split("/")[-1]
    for branch in ("main", "master"):
        r = run_git(["rev-parse", "--verify", branch], cwd=cwd, check=False)
        if r.returncode == 0:
            return branch
    return "main"


def get_current_branch(cwd: Path | None = None) -> str:
    result = run_git(["branch", "--show-current"], cwd=cwd)
    return result.stdout.strip()


def _worktrees_dir(run_id: str, repo: Path) -> Path:
    return repo / ".swarm" / "runs" / run_id / "worktrees"


def create_worktree(
    run_id: str,
    agent_name: str,
    repo_path: Path | None = None,
) -> Path:
    repo = repo_path or Path.cwd()
    worktree_path = _worktrees_dir(run_id, repo) / agent_name
    branch_name = f"swarm/{run_id}/{agent_name}"

    if worktree_path.exists() and (worktree_path / ".git").exists():
        logger.info("Reusing existing worktree at %s", worktree_path)
        return worktree_path

    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    run_git(["worktree", "add", "-b", branch_name, str(worktree_path)], cwd=repo)
    logger.info("Created worktree at %s on branch %s", worktree_path, branch_name)
    return worktree_path


def remove_worktree(worktree_path: Path, repo_path: Path | None = None) -> None:
    repo = repo_path or Path.cwd()
    run_git(["worktree", "remove", str(worktree_path), "--force"], cwd=repo)
    logger.info("Removed worktree at %s", worktree_path)


def delete_branch(branch: str, repo_path: Path | None = None) -> None:
    repo = repo_path or Path.cwd()
    run_git(["branch", "-D", branch], cwd=repo)
    logger.info("Deleted branch %s", branch)


def list_worktrees(repo_path: Path | None = None) -> list[dict]:
    repo = repo_path or Path.cwd()
    result = run_git(["worktree", "list", "--porcelain"], cwd=repo)
    worktrees: list[dict] = []
    current: dict = {}
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
    msg = message or f"Merge {branch}"
    result = run_git(
        ["merge", branch, "--no-edit", "-m", msg],
        cwd=worktree_path,
        check=False,
    )
    if result.returncode != 0:
        if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
            logger.warning("Merge conflict merging %s", branch)
            return False
        raise GitError(f"Merge failed: {result.stderr}")
    return True


def merge_branch_to_current(
    branch: str,
    message: str | None = None,
    repo_path: Path | None = None,
) -> bool:
    repo = repo_path or Path.cwd()
    msg = message or f"Merge {branch}"
    result = run_git(
        ["merge", branch, "--no-edit", "-m", msg],
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
            logger.warning("Merge conflict merging %s", branch)
            return False
        raise GitError(f"Merge failed: {result.stderr}")
    return True


def get_changed_files(
    branch: str, base: str, repo_path: Path | None = None
) -> list[str]:
    repo = repo_path or Path.cwd()
    result = run_git(["diff", "--name-only", f"{base}...{branch}"], cwd=repo)
    return [f for f in result.stdout.strip().split("\n") if f]


def has_conflicts(worktree_path: Path) -> bool:
    result = run_git(
        ["diff", "--name-only", "--diff-filter=U"],
        cwd=worktree_path,
        check=False,
    )
    return bool(result.stdout.strip())


def abort_merge(worktree_path: Path) -> None:
    run_git(["merge", "--abort"], cwd=worktree_path)


def commit_all(worktree_path: Path, message: str) -> None:
    run_git(["add", "-A"], cwd=worktree_path)
    result = run_git(["diff", "--cached", "--quiet"], cwd=worktree_path, check=False)
    if result.returncode != 0:
        run_git(["commit", "-m", message], cwd=worktree_path)
        logger.info("Committed in %s: %s", worktree_path, message)


def setup_worktree_with_deps(
    run_id: str,
    agent_name: str,
    depends_on: list[str],
    worktree_path: Path,
    mode: str = "full",
    include_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
) -> None:
    repo = get_repo_root(worktree_path)
    for dep_name in depends_on:
        dep_branch = f"swarm/{run_id}/{dep_name}"
        if mode == "full":
            if not merge_branch(worktree_path, dep_branch, f"Merge {dep_name} dependency"):
                raise GitError(f"Conflict merging dependency {dep_name}")
        elif mode == "diff_only":
            base = get_default_branch(repo)
            changed = get_changed_files(dep_branch, base, repo)
            for f in changed:
                run_git(
                    ["checkout", dep_branch, "--", f],
                    cwd=worktree_path,
                    check=False,
                )
            if changed:
                commit_all(worktree_path, f"Import changes from {dep_name}")
        elif mode == "paths":
            base = get_default_branch(repo)
            changed = get_changed_files(dep_branch, base, repo)

            def _matches(f: str, pattern: str) -> bool:
                pat = pattern.rstrip("/")
                return f == pat or f.startswith(pat + "/")

            filtered = []
            for f in changed:
                if include_paths and not any(_matches(f, p) for p in include_paths):
                    continue
                if exclude_paths and any(_matches(f, p) for p in exclude_paths):
                    continue
                filtered.append(f)
            if filtered:
                for f in filtered:
                    run_git(
                        ["checkout", dep_branch, "--", f],
                        cwd=worktree_path,
                        check=False,
                    )
                commit_all(worktree_path, f"Import filtered changes from {dep_name}")


def cleanup_run_worktrees(run_id: str, repo_path: Path | None = None) -> None:
    repo = repo_path or Path.cwd()
    worktrees = list_worktrees(repo)
    expected_prefix = str(_worktrees_dir(run_id, repo))
    for wt in worktrees:
        if expected_prefix in wt.get("path", ""):
            remove_worktree(Path(wt["path"]), repo)
    result = run_git(["branch", "--list", f"swarm/{run_id}/*"], cwd=repo, check=False)
    for branch in result.stdout.strip().split("\n"):
        branch = branch.strip()
        if branch:
            delete_branch(branch, repo)


class GitWorktreeProvider:
    """WorkspaceProvider that allocates one git worktree per agent."""

    def __init__(self, repo_path: Path | None = None):
        self.repo_path = repo_path or Path.cwd()

    async def allocate(self, run_id: str, agent_name: str) -> Workspace:
        path = create_worktree(run_id, agent_name, self.repo_path)
        branch = f"swarm/{run_id}/{agent_name}"
        base = get_default_branch(self.repo_path)
        return GitWorktree(
            path=path,
            branch=branch,
            base_branch=base,
            workspace_id=f"wt-{uuid4().hex[:12]}",
        )

    async def release(self, workspace: Workspace, keep: bool = False) -> None:
        if keep or not isinstance(workspace, GitWorktree):
            return
        try:
            remove_worktree(workspace.path, self.repo_path)
        except GitError as exc:
            logger.warning("Failed to remove worktree %s: %s", workspace.path, exc)
