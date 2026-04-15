"""OpenAI Agents SDK adapter.

Importing this module registers OpenAIExecutor under runtime='openai' only
if the `openai-agents` package is installed (it's in the `openai` extra).
Failing silently keeps the base install working without the optional dep;
`runtime: openai` plans on a base install will fail with a clear
"No executor registered" KeyError from get_executor.
"""

import logging

logger = logging.getLogger("swarm.adapters.openai")

try:
    from swarm.adapters.openai.executor import OpenAIExecutor
    from swarm.core.execution import register

    register(OpenAIExecutor())
except ImportError as exc:
    logger.debug("OpenAI adapter not available: %s", exc)
