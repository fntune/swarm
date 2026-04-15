"""Mock runtime adapter.

Importing this module registers MockExecutor under runtime='mock'. Safe
to import always — has no external SDK dependencies.
"""

from swarm.adapters.mock.executor import MockExecutor
from swarm.core.execution import register

register(MockExecutor())
