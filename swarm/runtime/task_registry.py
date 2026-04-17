"""Shared registry of live agent asyncio tasks.

The scheduler owns task lifetime, but coordination tools (e.g. a manager
calling `cancel_worker`) need a way to actually cancel the running
asyncio.Task rather than just flipping its DB status. This registry lets
those tools look up and cancel the live task by `(run_id, agent_name)`.
"""

from __future__ import annotations

import asyncio

_tasks: dict[tuple[str, str], asyncio.Task] = {}


def register(run_id: str, agent_name: str, task: asyncio.Task) -> None:
    _tasks[(run_id, agent_name)] = task


def unregister(run_id: str, agent_name: str) -> None:
    _tasks.pop((run_id, agent_name), None)


def get(run_id: str, agent_name: str) -> asyncio.Task | None:
    return _tasks.get((run_id, agent_name))


def cancel(run_id: str, agent_name: str) -> bool:
    """Cancel the task if present and still running. Returns True if cancelled."""
    task = _tasks.get((run_id, agent_name))
    if task is None or task.done():
        return False
    task.cancel()
    return True


def clear_run(run_id: str) -> None:
    for key in [k for k in _tasks if k[0] == run_id]:
        _tasks.pop(key, None)
