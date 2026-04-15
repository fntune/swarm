"""AgentRequest (YAML-facing), ResolvedAgent (immutable snapshot), Limits.

AgentRequest is what the plan file or inline builder produces — optional
fields everywhere, defaults fall through to the plan. ResolvedAgent is the
fully-resolved snapshot an Executor receives: every field is populated,
nothing inherits from anywhere, and it's frozen.

Resolution (AgentRequest -> ResolvedAgent) happens once at plan-load time in
batch/plan.py. After that, the scheduler only passes ResolvedAgent around.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from swarm.core.capabilities import Capability
from swarm.core.profiles import AgentProfile


@dataclass(frozen=True)
class Limits:
    max_iterations: int = 30
    max_cost_usd: float = 5.0


OnFailure = Literal["continue", "stop", "retry"]


@dataclass(frozen=True)
class AgentRequest:
    name: str
    prompt: str
    profile: str | None = None
    runtime: Literal["claude", "openai", "mock"] | None = None
    model: str | None = None
    capabilities: frozenset[Capability] | None = None
    limits: Limits | None = None
    check: str | None = None
    depends_on: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    output_schema: dict[str, Any] | None = None
    parent: str | None = None
    on_failure: OnFailure | None = None
    retry_count: int | None = None

    def env_dict(self) -> dict[str, str]:
        return dict(self.env)


@dataclass(frozen=True)
class ResolvedAgent:
    name: str
    prompt: str
    runtime: str
    model: str
    profile: AgentProfile
    capabilities: frozenset[Capability]
    limits: Limits
    check: str
    env: tuple[tuple[str, str], ...]
    output_schema: dict[str, Any] | None
    parent: str | None
    tree_path: str
    depends_on: tuple[str, ...] = ()
    on_failure: OnFailure = "continue"
    retry_count: int = 3

    def env_dict(self) -> dict[str, str]:
        return dict(self.env)
