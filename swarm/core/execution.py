"""Executor ABC, RunContext, ExecutionResult, and the executor registry.

An executor takes one immutable ResolvedAgent plus one RunContext (mutable
services: workspace, coordination backend, event sink) and returns an
ExecutionResult. Vendor adapters register their executor at import time.

The scheduler (batch) and pipeline (live) call get_executor(runtime) to
dispatch — neither knows which vendor is on the other side.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Literal

from swarm.core.agent import ResolvedAgent
from swarm.core.coordination import CoordinationBackend
from swarm.core.events import EventSink
from swarm.core.workspace import Workspace

ExecutionStatus = Literal[
    "completed",
    "failed",
    "timeout",
    "cancelled",
    "cost_exceeded",
]


@dataclass
class RunContext:
    run_id: str
    workspace: Workspace
    coord: CoordinationBackend
    events: EventSink

    @property
    def cwd(self) -> Path:
        return self.workspace.path


@dataclass(frozen=True)
class ExecutionResult:
    status: ExecutionStatus
    final_text: str
    cost_usd: float
    cost_source: Literal["sdk", "estimated"]
    vendor_session_id: str | None = None
    structured_output: Any = None
    files_modified: tuple[str, ...] = ()
    error: str | None = None
    iterations: int = 0


class Executor(ABC):
    runtime: ClassVar[str]

    @abstractmethod
    async def run(self, agent: ResolvedAgent, ctx: RunContext) -> ExecutionResult: ...


EXECUTOR_REGISTRY: dict[str, Executor] = {}


def register(executor: Executor) -> None:
    EXECUTOR_REGISTRY[executor.runtime] = executor


def get_executor(runtime: str) -> Executor:
    if runtime not in EXECUTOR_REGISTRY:
        raise KeyError(
            f"No executor registered for runtime={runtime!r}. "
            f"Registered: {sorted(EXECUTOR_REGISTRY)}"
        )
    return EXECUTOR_REGISTRY[runtime]


def list_runtimes() -> list[str]:
    return sorted(EXECUTOR_REGISTRY)
