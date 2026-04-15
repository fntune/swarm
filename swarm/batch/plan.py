"""PlanSpec, PlanDefaults, and resolution (AgentRequest -> ResolvedAgent).

The plan spec is the in-memory representation of a YAML plan file or an
inline -p invocation. It's frozen after resolution: every agent becomes a
ResolvedAgent with no defaults fall-through.

Resolution is the *only* place where profile lookup, capability overrides,
default-runtime resolution, and limits inheritance happen. Once the
scheduler has `list[ResolvedAgent]`, nothing else needs to know about
defaults.

Default runtime resolution order (first match wins):
1. PlanDefaults.runtime                (plan-level default)
2. os.environ["SWARM_DEFAULT_RUNTIME"] (env var fallback)
3. "claude"                            (hard fallback)
"""

import os
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from swarm.core.agent import AgentRequest, Limits, OnFailure, ResolvedAgent
from swarm.core.capabilities import Capability
from swarm.core.errors import PlanValidationError
from swarm.core.profiles import PROFILE_REGISTRY, AgentProfile, get_profile

ValidRuntime = Literal["claude", "openai", "mock"]
_VALID_RUNTIMES = {"claude", "openai", "mock"}
_DEFAULT_RUNTIME_FALLBACK = "claude"


@dataclass(frozen=True)
class CircuitBreakerConfig:
    threshold: int = 3
    action: Literal["cancel_all", "pause", "notify_only"] = "cancel_all"


@dataclass(frozen=True)
class CostBudget:
    total_usd: float = 25.0
    on_exceed: Literal["pause", "cancel", "warn"] = "pause"


@dataclass(frozen=True)
class DependencyContext:
    mode: Literal["full", "diff_only", "paths"] = "full"
    include_paths: tuple[str, ...] = ()
    exclude_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class MergeConfig:
    target_branch: str | None = None
    strategy: Literal["bottom_up", "root_only"] = "bottom_up"
    on_conflict: Literal["fail", "manual"] = "manual"
    auto_cleanup: bool = True


@dataclass(frozen=True)
class Orchestration:
    circuit_breaker: CircuitBreakerConfig | None = None
    dependency_context: DependencyContext | None = None
    merge: MergeConfig | None = None
    stuck_threshold: int | None = None


@dataclass(frozen=True)
class PlanDefaults:
    runtime: ValidRuntime | None = None
    profile: str = "implementer"
    model: str = "sonnet"
    check: str = "true"
    on_failure: OnFailure = "continue"
    retry_count: int = 3
    max_iterations: int = 30
    max_cost_usd: float = 5.0


@dataclass(frozen=True)
class PlanSpec:
    name: str
    agents: tuple[AgentRequest, ...]
    description: str = ""
    defaults: PlanDefaults = field(default_factory=PlanDefaults)
    cost_budget: CostBudget | None = None
    orchestration: Orchestration | None = None
    shared_context: tuple[str, ...] = ()


def resolve_default_runtime(plan_defaults: PlanDefaults) -> ValidRuntime:
    if plan_defaults.runtime is not None:
        return plan_defaults.runtime
    env_value = os.environ.get("SWARM_DEFAULT_RUNTIME")
    if env_value:
        if env_value not in _VALID_RUNTIMES:
            raise PlanValidationError(
                f"SWARM_DEFAULT_RUNTIME={env_value!r} is not one of {sorted(_VALID_RUNTIMES)}"
            )
        return env_value  # type: ignore[return-value]
    return _DEFAULT_RUNTIME_FALLBACK


def _coerce_capabilities(
    raw: Sequence[Any] | None,
) -> frozenset[Capability] | None:
    if raw is None:
        return None
    caps: set[Capability] = set()
    for item in raw:
        if isinstance(item, Capability):
            caps.add(item)
            continue
        try:
            caps.add(Capability(item))
        except ValueError as exc:
            raise PlanValidationError(f"Unknown capability: {item!r}") from exc
    return frozenset(caps)


def resolve_agent(
    request: AgentRequest,
    *,
    defaults: PlanDefaults,
    parent: str | None = None,
    parent_tree_path: str | None = None,
) -> ResolvedAgent:
    """Turn a YAML-facing AgentRequest into a fully-resolved ResolvedAgent.

    Raises PlanValidationError on unknown profile, bad runtime, or
    capability mismatch.
    """
    profile_name = request.profile or defaults.profile
    if profile_name not in PROFILE_REGISTRY:
        raise PlanValidationError(
            f"Agent {request.name!r} uses unknown profile {profile_name!r}. "
            f"Known profiles: {sorted(PROFILE_REGISTRY)}"
        )
    profile: AgentProfile = get_profile(profile_name)

    runtime: ValidRuntime
    if request.runtime is not None:
        if request.runtime not in _VALID_RUNTIMES:
            raise PlanValidationError(
                f"Agent {request.name!r} has unknown runtime {request.runtime!r}"
            )
        runtime = request.runtime  # type: ignore[assignment]
    else:
        runtime = resolve_default_runtime(defaults)

    capabilities = request.capabilities or profile.capabilities
    if profile.read_only and capabilities != profile.capabilities:
        allowed = profile.capabilities
        extras = capabilities - allowed
        if extras:
            raise PlanValidationError(
                f"Agent {request.name!r} uses read-only profile {profile.name!r} "
                f"but requests extra capabilities: {sorted(c.value for c in extras)}"
            )

    limits = request.limits or Limits(
        max_iterations=defaults.max_iterations,
        max_cost_usd=defaults.max_cost_usd,
    )

    model = request.model or profile.default_model or defaults.model
    check = request.check or profile.default_check or defaults.check
    on_failure = request.on_failure or defaults.on_failure
    retry_count = (
        request.retry_count if request.retry_count is not None else defaults.retry_count
    )

    tree_path = (
        f"{parent_tree_path}.{request.name}"
        if parent_tree_path
        else (f"{parent}.{request.name}" if parent else f"root.{request.name}")
    )

    return ResolvedAgent(
        name=request.name,
        prompt=request.prompt,
        runtime=runtime,
        model=model,
        profile=profile,
        capabilities=frozenset(capabilities),
        limits=limits,
        check=check,
        env=request.env,
        output_schema=request.output_schema,
        parent=parent or request.parent,
        tree_path=tree_path,
        depends_on=tuple(request.depends_on),
        on_failure=on_failure,
        retry_count=retry_count,
    )


def resolve_plan(plan: PlanSpec) -> list[ResolvedAgent]:
    resolved: list[ResolvedAgent] = []
    seen: set[str] = set()
    for request in plan.agents:
        if request.name in seen:
            raise PlanValidationError(f"Duplicate agent name: {request.name!r}")
        seen.add(request.name)
        resolved.append(resolve_agent(request, defaults=plan.defaults))

    names = {r.name for r in resolved}
    for r in resolved:
        unknown = set(r.depends_on) - names
        if unknown:
            raise PlanValidationError(
                f"Agent {r.name!r} depends on unknown agents: {sorted(unknown)}"
            )
    return resolved


def resolve_child(
    request: AgentRequest,
    *,
    parent_row: Any,
    parent_name: str,
) -> ResolvedAgent:
    """Resolve a child AgentRequest spawned at runtime by an orchestrator.

    Uses the parent's row (a sqlite3.Row from the nodes table) as the source
    of defaults when the request omits fields. Called from
    SqliteCoordinationBackend.spawn.
    """
    parent_tree = parent_row["tree_path"] if parent_row is not None else f"root.{parent_name}"
    parent_runtime = parent_row["runtime"] if parent_row is not None else None
    parent_model = parent_row["model"] if parent_row is not None else "sonnet"
    parent_check = parent_row["check_command"] if parent_row is not None else "true"
    parent_max_iter = parent_row["max_iterations"] if parent_row is not None else 30
    parent_max_cost = parent_row["max_cost_usd"] if parent_row is not None else 5.0

    defaults = PlanDefaults(
        runtime=parent_runtime,
        profile=request.profile or "implementer",
        model=parent_model,
        check=parent_check,
        max_iterations=parent_max_iter,
        max_cost_usd=parent_max_cost,
    )
    return resolve_agent(
        request,
        defaults=defaults,
        parent=parent_name,
        parent_tree_path=parent_tree,
    )
