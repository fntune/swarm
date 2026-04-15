"""TempDir workspace provider.

Allocates a fresh tempfile.TemporaryDirectory per agent. Useful for
generator-style agents whose output lives in a sandbox and gets consumed
rather than branched/merged.
"""

import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from swarm.core.workspace import TempDir, Workspace


class TempDirProvider:
    def __init__(self, parent: Path | None = None):
        self.parent = parent

    async def allocate(self, run_id: str, agent_name: str) -> Workspace:
        root = Path(tempfile.mkdtemp(prefix=f"swarm-{run_id}-{agent_name}-", dir=self.parent))
        return TempDir(path=root, workspace_id=f"tmp-{uuid4().hex[:12]}")

    async def release(self, workspace: Workspace, keep: bool = False) -> None:
        if keep or not isinstance(workspace, TempDir):
            return
        shutil.rmtree(workspace.path, ignore_errors=True)
