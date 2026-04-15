"""Swarm error hierarchy.

All swarm exceptions inherit from SwarmError so callers can catch the family
with one except clause when they need to.
"""


class SwarmError(Exception):
    """Base class for all swarm-raised errors."""


class SwarmExecutorError(SwarmError):
    """Raised by an executor when a run fails in a known way.

    `retryable` tells the scheduler whether the failure is worth a retry.
    `cost_so_far` lets the caller record what the partial run cost before dying.
    """

    def __init__(self, message: str, retryable: bool = False, cost_so_far: float = 0.0):
        super().__init__(message)
        self.retryable = retryable
        self.cost_so_far = cost_so_far


class CoordinationNotSupported(SwarmError):
    """Raised when a CoordinationBackend doesn't support an op.

    Live mode's InMemoryBackend raises this for CoordOp.SPAWN in v1.
    """

    def __init__(self, backend: str, op: str):
        super().__init__(f"{backend} does not support coord op {op!r}")
        self.backend = backend
        self.op = op


class PlanValidationError(SwarmError):
    """Raised at plan-load time for unresolvable specs (unknown profile,
    bad runtime, depends_on cycle, capability/profile mismatch)."""


class WorkspaceError(SwarmError):
    """Raised when a WorkspaceProvider fails to allocate or release."""


class MergeConflictError(SwarmError):
    """Raised by batch/merge.py when `auto` strategy hits a conflict.

    `swarm merge --strategy auto` no longer spawns a resolver agent; it surfaces
    this error and tells the user to rerun with `--strategy manual`.
    """
