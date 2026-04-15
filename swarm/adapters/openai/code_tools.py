"""File, shell, grep, and glob tools exposed to OpenAI agents.

Each tool is a thin @function_tool wrapper over stdlib / subprocess. The
adapter filters them by the agent's capability set at call time so a
read-only profile doesn't ship write/edit tools.
"""

import subprocess
from pathlib import Path
from typing import Any

from swarm.core.capabilities import Capability


def build_code_tools(
    *,
    workspace_cwd: Path,
    capabilities: frozenset[Capability],
) -> list[Any]:
    from agents import function_tool

    tools: list[Any] = []
    cwd = Path(workspace_cwd)

    if Capability.FILE_READ in capabilities:
        @function_tool
        async def read_file(path: str) -> str:
            """Read a text file relative to the workspace."""
            p = (cwd / path).resolve()
            if not str(p).startswith(str(cwd.resolve())):
                return f"ERROR: {path} escapes workspace"
            if not p.exists():
                return f"ERROR: {path} does not exist"
            return p.read_text()

        tools.append(read_file)

    if Capability.FILE_WRITE in capabilities:
        @function_tool
        async def write_file(path: str, content: str) -> str:
            """Write content to a file, creating parent dirs."""
            p = (cwd / path).resolve()
            if not str(p).startswith(str(cwd.resolve())):
                return f"ERROR: {path} escapes workspace"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return f"wrote {len(content)} chars to {path}"

        tools.append(write_file)

    if Capability.FILE_EDIT in capabilities:
        @function_tool
        async def edit_file(path: str, old_text: str, new_text: str) -> str:
            """Replace old_text with new_text in a file. old_text must be unique."""
            p = (cwd / path).resolve()
            if not str(p).startswith(str(cwd.resolve())):
                return f"ERROR: {path} escapes workspace"
            if not p.exists():
                return f"ERROR: {path} does not exist"
            text = p.read_text()
            if text.count(old_text) == 0:
                return "ERROR: old_text not found"
            if text.count(old_text) > 1:
                return "ERROR: old_text appears multiple times; make it more specific"
            p.write_text(text.replace(old_text, new_text, 1))
            return f"edited {path}"

        tools.append(edit_file)

    if Capability.SHELL in capabilities:
        @function_tool
        async def run_shell(command: str) -> str:
            """Run a shell command in the workspace. Returns combined stdout+stderr."""
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                text=True,
            )
            out = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
            return f"exit={proc.returncode}\n{out[-4000:]}"

        tools.append(run_shell)

    if Capability.GREP in capabilities:
        @function_tool
        async def grep(pattern: str, path: str = ".") -> str:
            """Run ripgrep for a pattern under the workspace."""
            proc = subprocess.run(
                ["rg", "--json", "-n", pattern, path],
                cwd=str(cwd),
                capture_output=True,
                text=True,
            )
            return (proc.stdout or "no matches")[-4000:]

        tools.append(grep)

    if Capability.GLOB in capabilities:
        @function_tool
        async def glob_files(pattern: str) -> str:
            """Glob files relative to the workspace."""
            matches = sorted(str(p.relative_to(cwd)) for p in cwd.glob(pattern))
            return "\n".join(matches[:500]) if matches else "no matches"

        tools.append(glob_files)

    return tools
