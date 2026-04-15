"""MockExecutor — runs the agent's check command in the workspace.

Replaces the old run_worker_mock. Batch `swarm run ... --mock` selects this
runtime via a plan override, and live mode / tests can register it directly.
"""

import asyncio
import logging
import subprocess
from typing import ClassVar

from swarm.core.agent import ResolvedAgent
from swarm.core.events import CostUpdate, IterationTick, LogText
from swarm.core.execution import Executor, ExecutionResult, RunContext

logger = logging.getLogger("swarm.adapters.mock")


class MockExecutor(Executor):
    runtime: ClassVar[str] = "mock"

    async def run(
        self, agent: ResolvedAgent, ctx: RunContext
    ) -> ExecutionResult:
        ctx.events.emit(
            LogText(
                run_id=ctx.run_id,
                agent=agent.name,
                text=f"[mock] running check: {agent.check}",
            )
        )
        ctx.events.emit(
            IterationTick(run_id=ctx.run_id, agent=agent.name, iteration=1)
        )

        await asyncio.sleep(0.05)
        proc = subprocess.run(
            agent.check,
            shell=True,
            cwd=str(ctx.workspace.path),
            capture_output=True,
            text=True,
        )

        ctx.events.emit(
            CostUpdate(
                run_id=ctx.run_id,
                agent=agent.name,
                cost_usd=0.0,
                source="estimated",
            )
        )

        if proc.returncode == 0:
            return ExecutionResult(
                status="completed",
                final_text=proc.stdout[-2000:],
                cost_usd=0.0,
                cost_source="estimated",
                iterations=1,
            )

        error = (proc.stderr or proc.stdout or "check failed")[-500:]
        return ExecutionResult(
            status="failed",
            final_text=proc.stdout[-2000:],
            cost_usd=0.0,
            cost_source="estimated",
            error=error,
            iterations=1,
        )
