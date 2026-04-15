"""Cwd workspace provider — zero isolation.

What live mode defaults to and what REPL / script users expect. `keep=True`
on release is a no-op because there's nothing to clean up.
"""

from pathlib import Path

from swarm.core.workspace import Cwd, Workspace


class CwdProvider:
    def __init__(self, path: Path | None = None):
        self.path = path or Path.cwd()

    async def allocate(self, run_id: str, agent_name: str) -> Workspace:
        return Cwd(path=self.path)

    async def release(self, workspace: Workspace, keep: bool = False) -> None:
        return None
