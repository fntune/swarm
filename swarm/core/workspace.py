"""Workspace ADT and provider protocol.

A workspace is where an agent's code operations happen. Three shapes:

- `GitWorktree`: an isolated git worktree on a per-agent branch. What batch
  mode uses today.
- `Cwd`: the caller's current directory. Zero isolation. What live mode
  pipelines default to and what REPL/script users expect.
- `TempDir`: a throwaway directory for generator-style agents that don't care
  about branches.

Workspaces are their own entity (with a `workspace_id`) so the batch DB can
reference them by id and future shared-workspace patterns (N readers on one
worktree) don't require a schema change.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Union


@dataclass(frozen=True)
class GitWorktree:
    path: Path
    branch: str
    base_branch: str
    workspace_id: str


@dataclass(frozen=True)
class Cwd:
    path: Path
    workspace_id: str = "cwd"


@dataclass(frozen=True)
class TempDir:
    path: Path
    workspace_id: str


Workspace = Union[GitWorktree, Cwd, TempDir]


class WorkspaceProvider(Protocol):
    async def allocate(self, run_id: str, agent_name: str) -> Workspace: ...
    async def release(self, workspace: Workspace, keep: bool = False) -> None: ...
