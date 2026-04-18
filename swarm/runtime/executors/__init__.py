"""Pluggable executors — one per vendor runtime.

Adapters self-register at import time. Importing ``swarm.runtime.executors``
triggers the Claude adapter registration; optional ``[openai]`` installs
enable the OpenAI adapter.
"""

from swarm.runtime.executors.base import (
    EXECUTOR_REGISTRY,
    Executor,
    ExecutorNotFound,
    get_executor,
    register,
)

# Side-effect import: ClaudeExecutor registers itself.
from swarm.runtime.executors import claude  # noqa: F401

# OpenAI is optional. Skip registration if the SDK isn't installed.
try:
    from swarm.runtime.executors import openai  # noqa: F401
except ImportError:
    pass


__all__ = [
    "EXECUTOR_REGISTRY",
    "Executor",
    "ExecutorNotFound",
    "get_executor",
    "register",
]
