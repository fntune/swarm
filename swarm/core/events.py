"""SwarmEvent ADT and EventSink protocol.

One emit(event) surface, two backends: SqliteSink (batch) writes events to the
events table and forwards LogText to per-agent log files; StdoutSink (live)
prints to a writer. Adapters only know about the Protocol.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, Union


@dataclass(frozen=True)
class AgentStarted:
    run_id: str
    agent: str
    runtime: str


@dataclass(frozen=True)
class IterationTick:
    run_id: str
    agent: str
    iteration: int


@dataclass(frozen=True)
class LogText:
    run_id: str
    agent: str
    text: str


@dataclass(frozen=True)
class CostUpdate:
    run_id: str
    agent: str
    cost_usd: float
    source: Literal["sdk", "estimated"]


@dataclass(frozen=True)
class CoordCall:
    run_id: str
    agent: str
    op: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentCompleted:
    run_id: str
    agent: str
    status: str
    error: str | None = None


SwarmEvent = Union[
    AgentStarted,
    IterationTick,
    LogText,
    CostUpdate,
    CoordCall,
    AgentCompleted,
]


class EventSink(Protocol):
    def emit(self, event: SwarmEvent) -> None: ...


class NullSink:
    """Drops everything. Useful for tests and adapters that don't care."""

    def emit(self, event: SwarmEvent) -> None:
        return None
