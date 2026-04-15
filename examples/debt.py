"""debt: a minimal port of the `debt` skill to live mode.

A Claude reviewer looks at the last git commit for technical debt, then an
OpenAI cross-reference agent sanity-checks the findings. This is a
simplified port of the full `debt` skill; a richer version (parallel
reviewers, structured TechnicalDebtReport output, automatic fix dispatch)
lives as follow-up work once the base primitives ship.

Usage:
    python examples/debt.py

Requires ANTHROPIC_API_KEY and OPENAI_API_KEY.
"""

import asyncio

import swarm.adapters.claude  # noqa: F401
import swarm.adapters.openai  # noqa: F401
from swarm.core.agent import AgentRequest
from swarm.live.pipeline import pipeline


async def main() -> None:
    audit = AgentRequest(
        name="audit",
        profile="reviewer",
        runtime="claude",
        prompt=(
            "Run `git diff HEAD~1` and review the changes for technical "
            "debt: unused imports, TODO markers, long functions, missing "
            "error handling, magic numbers. List up to 10 findings with "
            "file:line references. Do not modify any files."
        ),
    )
    cross_ref = AgentRequest(
        name="cross_ref",
        profile="reviewer",
        runtime="openai",
        prompt=(
            "Look at the audit findings in the context. For each finding, "
            "rate severity (high / medium / low) and whether it's a real "
            "issue or a false positive. Output as a numbered list."
        ),
    )

    results = await pipeline([audit, cross_ref], workspace="cwd")
    for step in results:
        print("=" * 60)
        print(f"{step.status}: {step.final_text[:1500]}")


if __name__ == "__main__":
    asyncio.run(main())
