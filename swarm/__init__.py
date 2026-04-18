"""Claude Swarm - Multi-agent orchestration framework."""

from swarm.api import agent, handoff, pipeline, run
from swarm.models.specs import AgentSpec, Defaults, PlanSpec
from swarm.runtime.scheduler import SchedulerResult

__version__ = "0.1.0"

__all__ = [
    "AgentSpec",
    "Defaults",
    "PlanSpec",
    "SchedulerResult",
    "agent",
    "handoff",
    "pipeline",
    "run",
]
