"""Pydantic models for claude-swarm."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class RunConfig(BaseModel):
    """Run identity and resumption settings."""

    id: str | None = None
    resume: bool = False


class Defaults(BaseModel):
    """Plan-level default settings."""

    max_iterations: int = 30
    check: str | None = "true"
    on_failure: Literal["continue", "stop", "retry"] = "continue"
    retry_count: int = 3
    model: Literal["sonnet", "opus", "haiku"] = "sonnet"
    max_cost_usd: float = 5.0


class CostBudget(BaseModel):
    """Plan-level cost budget."""

    total_usd: float = 25.0
    on_exceed: Literal["pause", "cancel", "warn"] = "pause"


class CircuitBreaker(BaseModel):
    """Circuit breaker settings."""

    threshold: int = 3
    action: Literal["cancel_all", "pause", "notify_only"] = "cancel_all"


class DependencyContext(BaseModel):
    """Dependency context inheritance settings."""

    mode: Literal["full", "diff_only", "paths"] = "full"
    include_paths: list[str] = Field(default_factory=list)
    exclude_paths: list[str] = Field(default_factory=list)


class MergeConfig(BaseModel):
    """Merge settings."""

    target_branch: str | None = None
    strategy: Literal["bottom_up", "root_only"] = "bottom_up"
    on_conflict: Literal["spawn_resolver", "fail", "manual"] = "manual"
    resolver_timeout: int = 120
    resolver_max_cost: float = 2.0
    fallback: Literal["manual", "fail"] = "manual"
    auto_cleanup: bool = True


class Orchestration(BaseModel):
    """Orchestration settings."""

    event_injection: bool = True
    circuit_breaker: CircuitBreaker | None = None
    dependency_context: DependencyContext | None = None
    merge: MergeConfig | None = None


class Milestone(BaseModel):
    """Named milestone for progress tracking."""

    name: str
    description: str = ""


class ManagerSettings(BaseModel):
    """Manager-specific settings."""

    max_subagents: int = 5
    event_poll_interval: int = 10
    guidance_enabled: bool = True


class AgentSpec(BaseModel):
    """Agent specification in a plan."""

    name: str
    type: Literal["worker", "manager"] = "worker"
    use_role: str | None = None
    prompt: str
    max_iterations: int | None = None
    check: str | None = None
    on_failure: Literal["continue", "stop", "retry"] | None = None
    retry_count: int | None = None
    model: Literal["sonnet", "opus", "haiku"] | None = None
    max_cost_usd: float | None = None
    depends_on: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    milestones: list[Milestone] = Field(default_factory=list)
    manager: ManagerSettings | None = None


class PlanSpec(BaseModel):
    """Full plan specification."""

    name: str
    description: str = ""
    run: RunConfig | None = None
    defaults: Defaults = Field(default_factory=Defaults)
    cost_budget: CostBudget | None = None
    shared_context: list[str] = Field(default_factory=list)
    orchestration: Orchestration | None = None
    agents: list[AgentSpec] = Field(default_factory=list)
    on_complete: Literal["merge", "none", "notify"] = "none"


class AgentState(BaseModel):
    """Runtime state of an agent."""

    name: str
    run_id: str
    status: Literal[
        "pending",
        "running",
        "blocked",
        "checking",
        "paused",
        "completed",
        "failed",
        "timeout",
        "cancelled",
        "cost_exceeded",
    ] = "pending"
    iteration: int = 0
    max_iterations: int = 30
    worktree: str | None = None
    branch: str | None = None
    prompt: str = ""
    check_command: str | None = None
    model: str = "sonnet"
    parent: str | None = None
    cost_usd: float = 0.0
    max_cost_usd: float = 5.0
    error: str | None = None
    depends_on: list[str] = Field(default_factory=list)


class Event(BaseModel):
    """Event emitted by an agent."""

    id: str
    run_id: str
    ts: str
    agent: str
    event_type: Literal[
        "started",
        "progress",
        "clarification",
        "blocker",
        "done",
        "error",
        "cascade_skip",
        "circuit_breaker_tripped",
    ]
    data: dict = Field(default_factory=dict)


class Response(BaseModel):
    """Response to a clarification request."""

    id: int
    run_id: str
    clarification_id: str
    response: str
    consumed: bool = False
