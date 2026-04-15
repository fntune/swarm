"""YAML parsing, inline plan building, and plan validation.

Absorbs the old swarm/io/parser.py + plan_builder.py + validation.py into
one file. Pydantic is used only here (at the YAML boundary) to produce
pure-dataclass PlanSpec / AgentRequest values that the rest of the code
consumes.
"""

import re
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field

from swarm.core.agent import AgentRequest, Limits, OnFailure
from swarm.core.capabilities import Capability
from swarm.core.errors import PlanValidationError
from swarm.batch.dag import DependencyGraph
from swarm.batch.plan import (
    CircuitBreakerConfig,
    CostBudget,
    DependencyContext,
    MergeConfig,
    Orchestration,
    PlanDefaults,
    PlanSpec,
)


# ---------------------------------------------------------------------------
# Pydantic boundary models (YAML -> plain Python)
# ---------------------------------------------------------------------------


class _RawDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runtime: Literal["claude", "openai", "mock"] | None = None
    profile: str = "implementer"
    model: str = "sonnet"
    check: str = "true"
    on_failure: Literal["continue", "stop", "retry"] = "continue"
    retry_count: int = 3
    max_iterations: int = 30
    max_cost_usd: float = 5.0


class _RawCostBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_usd: float = 25.0
    on_exceed: Literal["pause", "cancel", "warn"] = "pause"


class _RawCircuitBreaker(BaseModel):
    model_config = ConfigDict(extra="forbid")
    threshold: int = 3
    action: Literal["cancel_all", "pause", "notify_only"] = "cancel_all"


class _RawDependencyContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["full", "diff_only", "paths"] = "full"
    include_paths: list[str] = Field(default_factory=list)
    exclude_paths: list[str] = Field(default_factory=list)


class _RawMerge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_branch: str | None = None
    strategy: Literal["bottom_up", "root_only"] = "bottom_up"
    on_conflict: Literal["fail", "manual"] = "manual"
    auto_cleanup: bool = True


class _RawOrchestration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    circuit_breaker: _RawCircuitBreaker | None = None
    dependency_context: _RawDependencyContext | None = None
    merge: _RawMerge | None = None
    stuck_threshold: int | None = None


class _RawAgent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    prompt: str
    profile: str | None = None
    runtime: Literal["claude", "openai", "mock"] | None = None
    model: str | None = None
    capabilities: list[str] | None = None
    max_iterations: int | None = None
    max_cost_usd: float | None = None
    check: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    on_failure: Literal["continue", "stop", "retry"] | None = None
    retry_count: int | None = None


class _RawPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str = ""
    defaults: _RawDefaults = Field(default_factory=_RawDefaults)
    cost_budget: _RawCostBudget | None = None
    orchestration: _RawOrchestration | None = None
    shared_context: list[str] = Field(default_factory=list)
    agents: list[_RawAgent] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Raw -> typed conversion
# ---------------------------------------------------------------------------


def _coerce_capabilities(raw: list[str] | None) -> frozenset[Capability] | None:
    if raw is None:
        return None
    out: set[Capability] = set()
    for item in raw:
        try:
            out.add(Capability(item))
        except ValueError as exc:
            raise PlanValidationError(f"Unknown capability: {item!r}") from exc
    return frozenset(out)


def _agent_from_raw(raw: _RawAgent) -> AgentRequest:
    limits: Limits | None = None
    if raw.max_iterations is not None or raw.max_cost_usd is not None:
        limits = Limits(
            max_iterations=raw.max_iterations if raw.max_iterations is not None else 30,
            max_cost_usd=raw.max_cost_usd if raw.max_cost_usd is not None else 5.0,
        )
    return AgentRequest(
        name=raw.name,
        prompt=raw.prompt,
        profile=raw.profile,
        runtime=raw.runtime,
        model=raw.model,
        capabilities=_coerce_capabilities(raw.capabilities),
        limits=limits,
        check=raw.check,
        depends_on=tuple(raw.depends_on),
        env=tuple(raw.env.items()),
        output_schema=raw.output_schema,
        on_failure=raw.on_failure,
        retry_count=raw.retry_count,
    )


def _defaults_from_raw(raw: _RawDefaults) -> PlanDefaults:
    return PlanDefaults(
        runtime=raw.runtime,
        profile=raw.profile,
        model=raw.model,
        check=raw.check,
        on_failure=raw.on_failure,
        retry_count=raw.retry_count,
        max_iterations=raw.max_iterations,
        max_cost_usd=raw.max_cost_usd,
    )


def _orchestration_from_raw(raw: _RawOrchestration | None) -> Orchestration | None:
    if raw is None:
        return None
    return Orchestration(
        circuit_breaker=(
            CircuitBreakerConfig(
                threshold=raw.circuit_breaker.threshold,
                action=raw.circuit_breaker.action,
            )
            if raw.circuit_breaker
            else None
        ),
        dependency_context=(
            DependencyContext(
                mode=raw.dependency_context.mode,
                include_paths=tuple(raw.dependency_context.include_paths),
                exclude_paths=tuple(raw.dependency_context.exclude_paths),
            )
            if raw.dependency_context
            else None
        ),
        merge=(
            MergeConfig(
                target_branch=raw.merge.target_branch,
                strategy=raw.merge.strategy,
                on_conflict=raw.merge.on_conflict,
                auto_cleanup=raw.merge.auto_cleanup,
            )
            if raw.merge
            else None
        ),
        stuck_threshold=raw.stuck_threshold,
    )


def _plan_from_raw(raw: _RawPlan) -> PlanSpec:
    return PlanSpec(
        name=raw.name,
        description=raw.description,
        defaults=_defaults_from_raw(raw.defaults),
        cost_budget=(
            CostBudget(
                total_usd=raw.cost_budget.total_usd,
                on_exceed=raw.cost_budget.on_exceed,
            )
            if raw.cost_budget
            else None
        ),
        orchestration=_orchestration_from_raw(raw.orchestration),
        shared_context=tuple(raw.shared_context),
        agents=tuple(_agent_from_raw(a) for a in raw.agents),
    )


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def parse_plan_file(path: Path | str) -> PlanSpec:
    text = Path(path).read_text()
    return parse_plan_yaml(text)


def parse_plan_yaml(content: str) -> PlanSpec:
    data = yaml.safe_load(content) or {}
    raw = _RawPlan.model_validate(data)
    plan = _plan_from_raw(raw)
    validate_plan(plan)
    return plan


def validate_plan(plan: PlanSpec) -> None:
    names = [a.name for a in plan.agents]
    if len(names) != len(set(names)):
        raise PlanValidationError("Duplicate agent names in plan")
    deps = {a.name: set(a.depends_on) for a in plan.agents}
    errors = DependencyGraph(deps).validate()
    if errors:
        raise PlanValidationError("; ".join(errors))


_NAME_PATTERNS = (
    re.compile(r"(?:implement|add|create|build)\s+(\w+)", re.IGNORECASE),
    re.compile(r"(?:fix|resolve|debug)\s+(\w+)", re.IGNORECASE),
    re.compile(r"(?:refactor|update|improve)\s+(\w+)", re.IGNORECASE),
)


def infer_agent_name(prompt: str) -> str:
    for pattern in _NAME_PATTERNS:
        match = pattern.search(prompt)
        if match:
            return match.group(1).lower()
    words = [w for w in prompt.split() if len(w) > 3]
    return words[0].lower() if words else f"task-{uuid4().hex[:6]}"


def parse_inline_agents(prompts: list[str]) -> list[AgentRequest]:
    out: list[AgentRequest] = []
    for prompt in prompts:
        if ":" in prompt and not prompt.startswith("http"):
            name, rest = prompt.split(":", 1)
            out.append(AgentRequest(name=name.strip(), prompt=rest.strip()))
        else:
            out.append(AgentRequest(name=infer_agent_name(prompt), prompt=prompt))
    return out


def build_inline_plan(
    prompts: list[str],
    *,
    sequential: bool = False,
    defaults: PlanDefaults | None = None,
) -> PlanSpec:
    agents = parse_inline_agents(prompts)
    if sequential and len(agents) > 1:
        chained: list[AgentRequest] = []
        for i, agent in enumerate(agents):
            deps = (agents[i - 1].name,) if i > 0 else ()
            chained.append(
                AgentRequest(
                    name=agent.name,
                    prompt=agent.prompt,
                    depends_on=deps,
                )
            )
        agents = chained
    plan = PlanSpec(
        name=f"inline-{uuid4().hex[:8]}",
        defaults=defaults or PlanDefaults(),
        agents=tuple(agents),
    )
    validate_plan(plan)
    return plan


def load_shared_context(paths: list[str] | tuple[str, ...], base_path: Path | None = None) -> str:
    base = base_path or Path.cwd()
    out: list[str] = []
    for p in paths:
        full = base / p
        if full.exists():
            out.append(f"--- {p} ---\n{full.read_text()}")
    return "\n\n".join(out)


def generate_run_id(plan_name: str) -> str:
    return f"{plan_name}-{uuid4().hex[:8]}"
