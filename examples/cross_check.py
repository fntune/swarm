"""cross_check: Claude generator -> OpenAI reviewer.

The "hello world" of live mode. A Claude agent proposes a small change,
then an OpenAI agent reviews the diff with a structured Pydantic output.
Run with ANTHROPIC_API_KEY and OPENAI_API_KEY set.

Usage:
    python examples/cross_check.py

This script requires both the Claude Agent SDK and openai-agents to be
installed (pip install -e '.[sdk,openai]').
"""

import asyncio

# Adapters self-register at import time.
import swarm.adapters.claude  # noqa: F401
import swarm.adapters.openai  # noqa: F401
from swarm.core.agent import AgentRequest
from swarm.live.pipeline import pipeline


async def main() -> None:
    generator = AgentRequest(
        name="generator",
        profile="implementer",
        runtime="claude",
        prompt=(
            "Write a 10-line Python function `fibonacci(n: int) -> list[int]` "
            "that returns the first n Fibonacci numbers. Print the function "
            "source to stdout in your response. Do not create any files."
        ),
    )
    reviewer = AgentRequest(
        name="reviewer",
        profile="reviewer",
        runtime="openai",
        prompt=(
            "Review the Fibonacci function proposed in the context above. "
            "Identify any bugs, edge cases, or style issues. If the function "
            "is correct, say so. Keep your review to 5 bullet points."
        ),
    )

    results = await pipeline([generator, reviewer], workspace="cwd")
    for step in results:
        print("=" * 60)
        print(f"{step.status}: {step.final_text[:1000]}")


if __name__ == "__main__":
    asyncio.run(main())
