"""Claude Agent SDK adapter.

Importing this module registers ClaudeExecutor with the executor registry,
making `runtime: claude` available in batch plans and live pipelines.
"""

from swarm.adapters.claude.executor import ClaudeExecutor
from swarm.core.execution import register

register(ClaudeExecutor())
