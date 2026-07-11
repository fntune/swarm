"""HTTP API for deployed spawnd."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from spawnd.api import cancel as cancel_run
from spawnd.api import resume as resume_run
from spawnd.artifacts.store import ArtifactNotFoundError, ArtifactStore, S3ArtifactStore
from spawnd.config import load_backend_config
from spawnd.coordination.redis import RedisCoordinator, aiter_live_events
from spawnd.io.parser import RUN_ID_PATTERN
from spawnd.io.validation import validate_plan
from spawnd.models.specs import PlanSpec
from spawnd.state.repository import DeployedRepository
from spawnd.state.submission import consume_next_submission, enqueue_submission, submit_due_schedules, submit_plan, submit_template
from spawnd.workers.worker import drain_queue_outbox, reconcile_ready_agents


MAX_ARTIFACT_CONTENT_BYTES = 2_000_000
TERMINAL_RUN_STATUSES = {'completed', 'failed', 'cancelled', 'cost_exceeded'}
STREAM_KEEPALIVE_SECONDS = 15.0
STREAM_TICK_SECONDS = 2.0
PathId = Annotated[str, Field(pattern=RUN_ID_PATTERN, max_length=160)]


class SubmitBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

    plan: PlanSpec | None = None
    run_id: PathId | None = None
    source_repo: str | None = None
    source_ref: str | None = None


class TemplateBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: PathId
    name: str
    plan_template: str
    description: str | None = None
    source_repo_template: str | None = None
    source_ref_template: str | None = None


class TemplateRunBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

    parameters: dict[str, Any] = {}
    run_id: PathId | None = None


class ScheduleBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: PathId
    template_id: PathId
    name: str
    interval_seconds: int
    parameters: dict[str, Any] = {}
    status: Literal['active', 'paused'] = 'active'


class ScheduleStatusBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

    status: Literal['active', 'paused']


class SubmissionBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

    kind: str
    plan: dict[str, Any] | None = None
    template_id: PathId | None = None
    parameters: dict[str, Any] = {}
    run_id: PathId | None = None
    source_repo: str | None = None
    source_ref: str | None = None


class ClarificationResponseBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

    response: str


def _repository() -> DeployedRepository:
    config = load_backend_config()
    if not config.database_url:
        raise HTTPException(status_code=500, detail="SPAWND_DATABASE_URL is required")
    return DeployedRepository.from_url(config.database_url)


def _coordinator() -> RedisCoordinator:
    config = load_backend_config()
    if not config.redis_url:
        raise HTTPException(status_code=500, detail="SPAWND_REDIS_URL is required")
    return RedisCoordinator.from_url(config.redis_url)


def _artifact_store() -> ArtifactStore:
    config = load_backend_config()
    if not config.artifacts.configured:
        raise HTTPException(status_code=500, detail="SPAWND_ARTIFACTS_BUCKET is required for artifact content")
    return S3ArtifactStore(config.artifacts)


def _usage_rollup(token_rows: list[dict[str, Any]], cost_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rollup: dict[str, dict[str, Any]] = {}

    def bucket(agent: Any) -> dict[str, Any]:
        key = str(agent) if agent else '_system'
        if key not in rollup:
            rollup[key] = {
                'agent': key,
                'input_tokens': 0,
                'cached_input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
                'amount_usd': 0.0,
            }
        return rollup[key]

    for row in token_rows:
        entry = bucket(row.get('agent'))
        for field in ('input_tokens', 'cached_input_tokens', 'output_tokens', 'total_tokens'):
            entry[field] += int(row.get(field) or 0)
    for row in cost_rows:
        entry = bucket(row.get('agent'))
        entry['amount_usd'] += float(row.get('amount_usd') or 0.0)
    return sorted(rollup.values(), key=lambda entry: entry['agent'])


def _run_status(repo: DeployedRepository, run_id: str) -> dict[str, Any]:
    run_row = repo.get_run(run_id)
    if run_row is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return {
        "run": run_row,
        "agents": repo.get_agents(run_id),
        "attempts": repo.get_attempts(run_id),
        "telemetry": repo.telemetry_summary(run_id),
    }


def _verify_github_signature(secret: str, body: bytes, signature: str | None) -> None:
    if not signature:
        raise HTTPException(status_code=401, detail="Missing GitHub signature")
    prefix, separator, digest = signature.partition("=")
    if prefix != "sha256" or not separator:
        raise HTTPException(status_code=401, detail="Invalid GitHub signature")
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, expected):
        raise HTTPException(status_code=401, detail="Invalid GitHub signature")


def _github_parameters(event: str, payload: dict[str, Any]) -> dict[str, str]:
    repository = payload.get("repository") if isinstance(payload.get("repository"), dict) else {}
    repo = str(repository.get("full_name") or repository.get("name") or "")
    parameters = {
        "event": event,
        "action": str(payload.get("action") or ""),
        "repo": repo,
        "repo_slug": repo.replace("/", "-"),
        "clone_url": str(repository.get("clone_url") or ""),
        "ssh_url": str(repository.get("ssh_url") or ""),
        "default_branch": str(repository.get("default_branch") or ""),
        "ref": str(payload.get("ref") or ""),
        "before": str(payload.get("before") or ""),
        "after": str(payload.get("after") or ""),
        "pr_number": "",
        "head_ref": "",
        "head_sha": "",
        "base_ref": "",
        "base_sha": "",
    }
    pull_request = payload.get("pull_request")
    if isinstance(pull_request, dict):
        head = pull_request.get("head") if isinstance(pull_request.get("head"), dict) else {}
        base = pull_request.get("base") if isinstance(pull_request.get("base"), dict) else {}
        parameters.update(
            {
                "pr_number": str(pull_request.get("number") or payload.get("number") or ""),
                "head_ref": str(head.get("ref") or ""),
                "head_sha": str(head.get("sha") or ""),
                "base_ref": str(base.get("ref") or ""),
                "base_sha": str(base.get("sha") or ""),
            }
        )
    issue = payload.get("issue")
    if isinstance(issue, dict):
        parameters["issue_number"] = str(issue.get("number") or "")
    return parameters


def create_app() -> FastAPI:
    app = FastAPI(title="spawnd", version="0.1.0")

    @app.middleware("http")
    async def require_bearer_token(request: Request, call_next):
        if request.url.path in {"/healthz", "/readyz", "/metrics"}:
            return await call_next(request)
        if request.url.path.startswith("/webhooks/github/"):
            return await call_next(request)
        token = load_backend_config().api_token
        if not token:
            return JSONResponse({"detail": "SPAWND_API_TOKEN is required"}, status_code=500)
        authorization = request.headers.get("authorization") or ""
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(value, token):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, bool]:
        config = load_backend_config()
        return {
            "database_configured": bool(config.database_url),
            "redis_configured": bool(config.redis_url),
            "api_auth_configured": bool(config.api_token),
        }

    @app.get("/metrics")
    def metrics() -> PlainTextResponse:
        config = load_backend_config()
        try:
            queue_depth = _coordinator().queue_depth() if config.redis_url else -1
            submission_queue_depth = _coordinator().submission_queue_depth() if config.redis_url else -1
        except Exception:
            queue_depth = -1
            submission_queue_depth = -1
        try:
            workers = _repository().list_worker_nodes() if config.database_url else []
            worker_count = len(workers)
            stale_worker_count = len([worker for worker in workers if worker.get("stale")])
        except Exception:
            worker_count = -1
            stale_worker_count = -1
        lines = [
            "# HELP spawnd_backend_configured Backend configuration presence.",
            "# TYPE spawnd_backend_configured gauge",
            f"spawnd_backend_configured{{component=\"database\"}} {1 if config.database_url else 0}",
            f"spawnd_backend_configured{{component=\"redis\"}} {1 if config.redis_url else 0}",
            f"spawnd_backend_configured{{component=\"api_auth\"}} {1 if config.api_token else 0}",
            "# HELP spawnd_queue_depth Ready-agent queue depth, or -1 when unavailable.",
            "# TYPE spawnd_queue_depth gauge",
            f"spawnd_queue_depth {queue_depth}",
            "# HELP spawnd_submission_queue_depth Run-submission queue depth, or -1 when unavailable.",
            "# TYPE spawnd_submission_queue_depth gauge",
            f"spawnd_submission_queue_depth {submission_queue_depth}",
            "# HELP spawnd_worker_nodes Worker-node count, or -1 when unavailable.",
            "# TYPE spawnd_worker_nodes gauge",
            f"spawnd_worker_nodes {worker_count}",
            "# HELP spawnd_worker_nodes_stale Stale worker-node count, or -1 when unavailable.",
            "# TYPE spawnd_worker_nodes_stale gauge",
            f"spawnd_worker_nodes_stale {stale_worker_count}",
        ]
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain")

    @app.post("/runs")
    def submit(body: SubmitBody) -> dict[str, str]:
        plan = body.plan
        if plan is None:
            raise HTTPException(status_code=422, detail="plan is required")
        errors = validate_plan(plan)
        if errors:
            raise HTTPException(status_code=422, detail=errors)
        run_id = submit_plan(
            plan,
            repository=_repository(),
            coordinator=_coordinator(),
            run_id=body.run_id,
            source_repo=body.source_repo,
            source_ref=body.source_ref,
        )
        return {"run_id": run_id}

    @app.post("/templates")
    def put_template(body: TemplateBody) -> dict[str, str]:
        _repository().create_run_template(
            body.id,
            name=body.name,
            description=body.description,
            plan_template=body.plan_template,
            source_repo_template=body.source_repo_template,
            source_ref_template=body.source_ref_template,
        )
        return {"template_id": body.id}

    @app.get("/templates")
    def list_templates(limit: int = 100) -> list[dict[str, Any]]:
        return _repository().list_run_templates(limit=limit)

    @app.post("/templates/{template_id}/runs")
    def run_template(template_id: str, body: TemplateRunBody) -> dict[str, str]:
        run_id = submit_template(
            template_id,
            parameters=body.parameters,
            repository=_repository(),
            coordinator=_coordinator(),
            run_id=body.run_id,
        )
        return {"run_id": run_id}

    @app.post("/schedules")
    def put_schedule(body: ScheduleBody) -> dict[str, str]:
        _repository().create_schedule(
            body.id,
            template_id=body.template_id,
            name=body.name,
            interval_seconds=body.interval_seconds,
            parameters=body.parameters,
            status=body.status,
        )
        return {"schedule_id": body.id}

    @app.get("/schedules")
    def list_schedules(limit: int = 100) -> list[dict[str, Any]]:
        return _repository().list_schedules(limit=limit)

    @app.patch("/schedules/{schedule_id}/status")
    def set_schedule_status(schedule_id: str, body: ScheduleStatusBody) -> dict[str, str]:
        try:
            _repository().set_schedule_status(schedule_id, status=body.status)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"schedule_id": schedule_id, "status": body.status}

    @app.post("/schedules/run-due")
    def run_due_schedules(limit: int = 100) -> list[dict[str, Any]]:
        return submit_due_schedules(repository=_repository(), coordinator=_coordinator(), limit=limit)

    @app.post("/submissions")
    def enqueue_submission_request(body: SubmissionBody) -> dict[str, str]:
        payload = body.model_dump(mode="json", exclude_none=True)
        enqueue_submission(_coordinator(), payload)
        return {"status": "queued"}

    @app.post("/submissions/drain")
    def drain_submission_queue(consumer_id: str = "api-submitter", block_ms: int = 0) -> dict[str, Any]:
        result = consume_next_submission(
            repository=_repository(),
            coordinator=_coordinator(),
            consumer_id=consumer_id,
            block_ms=block_ms,
        )
        return result or {"status": "empty"}

    @app.post("/webhooks/github/{template_id}")
    async def github_webhook(template_id: str, request: Request) -> dict[str, str]:
        secret = load_backend_config().github_webhook_secret
        if not secret:
            raise HTTPException(status_code=500, detail="SPAWND_GITHUB_WEBHOOK_SECRET is required")
        body = await request.body()
        _verify_github_signature(secret, body, request.headers.get("X-Hub-Signature-256"))
        event = request.headers.get("X-GitHub-Event") or "unknown"
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="GitHub payload must be a JSON object")
        if event == "ping":
            return {"status": "pong"}
        run_id = submit_template(
            template_id,
            parameters=_github_parameters(event, payload),
            repository=_repository(),
            coordinator=_coordinator(),
        )
        return {"run_id": run_id}

    @app.get("/runs")
    def list_runs(
        limit: int = 50,
        offset: int = 0,
        status: list[str] | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        rows = _repository().list_runs(max(1, min(limit, 200)), status=status, offset=max(0, offset))
        return [{key: value for key, value in row.items() if key != "spec"} for row in rows]

    @app.get("/runs/{run_id}")
    def status(run_id: str) -> dict[str, Any]:
        return _run_status(_repository(), run_id)

    @app.get("/runs/{run_id}/events")
    def events(run_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return _repository().get_events(run_id, limit=limit)

    @app.get("/runs/{run_id}/events/stream")
    async def stream_events(request: Request, run_id: str, replay: int = 100) -> StreamingResponse:
        repo = _repository()
        run_row = await run_in_threadpool(repo.get_run, run_id)
        if run_row is None:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        replay_count = max(0, min(replay, 500))
        redis_url = load_backend_config().redis_url

        def encode(event_name: str, payload: dict[str, Any], event_id: str | None = None) -> str:
            prefix = f"id: {event_id}\n" if event_id else ""
            return f"{prefix}event: {event_name}\ndata: {json.dumps(payload, default=str, sort_keys=True)}\n\n"

        async def live_ticks() -> AsyncIterator[dict[str, Any] | None]:
            if redis_url:
                try:
                    async for notice in aiter_live_events(redis_url, run_id, tick_seconds=STREAM_TICK_SECONDS):
                        yield notice
                    return
                except Exception:
                    pass
            while True:
                await asyncio.sleep(STREAM_TICK_SECONDS)
                yield None

        async def event_stream() -> AsyncIterator[str]:
            seen: set[str] = set()
            cursor: datetime | None = None
            cursor_id: str | None = None
            last_frame = time.monotonic()

            def remember(row: dict[str, Any]) -> str:
                nonlocal cursor, cursor_id
                event_id = str(row["id"])
                seen.add(event_id)
                created = row.get("created_at")
                if created is not None and (
                    cursor is None or (created, event_id) > (cursor, cursor_id or "")
                ):
                    cursor = created
                    cursor_id = event_id
                return event_id

            async def fresh_frames() -> list[str]:
                rows = await run_in_threadpool(
                    lambda: repo.get_events_after(run_id, after=cursor, after_id=cursor_id)
                )
                frames: list[str] = []
                for row in rows:
                    if str(row["id"]) in seen:
                        continue
                    frames.append(encode("run-event", row, remember(row)))
                return frames

            replayed = await run_in_threadpool(repo.get_events, run_id, replay_count or 1)
            if replay_count:
                for row in reversed(replayed):
                    last_frame = time.monotonic()
                    yield encode("run-event", row, remember(row))
            else:
                for row in replayed:
                    _ = remember(row)

            run_state = await run_in_threadpool(repo.get_run, run_id)
            if run_state is not None and run_state.get("status") in TERMINAL_RUN_STATUSES:
                yield encode("done", {"status": run_state.get("status")})
                return

            async for notice in live_ticks():
                if await request.is_disconnected():
                    return
                if notice is not None:
                    last_frame = time.monotonic()
                    yield encode("coordination", notice)
                for frame in await fresh_frames():
                    last_frame = time.monotonic()
                    yield frame
                run_state = await run_in_threadpool(repo.get_run, run_id)
                if run_state is None or run_state.get("status") in TERMINAL_RUN_STATUSES:
                    for frame in await fresh_frames():
                        yield frame
                    yield encode("done", {"status": (run_state or {}).get("status")})
                    return
                if time.monotonic() - last_frame >= STREAM_KEEPALIVE_SECONDS:
                    last_frame = time.monotonic()
                    yield ": keepalive\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/runs/{run_id}/checks")
    def checks(run_id: str, agent: str | None = None) -> list[dict[str, Any]]:
        return _repository().get_checks(run_id, agent)

    @app.get("/runs/{run_id}/artifacts")
    def artifacts(run_id: str, agent: str | None = None) -> list[dict[str, Any]]:
        return _repository().get_artifacts(run_id, agent)

    @app.get("/runs/{run_id}/artifacts/{artifact_id}/content")
    def artifact_content(run_id: str, artifact_id: str) -> Response:
        row = _repository().get_artifact(artifact_id)
        if row is None or row.get("run_id") != run_id:
            raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_id}")
        if int(row.get("size_bytes") or 0) > MAX_ARTIFACT_CONTENT_BYTES:
            raise HTTPException(status_code=413, detail="Artifact exceeds inline content limit")
        try:
            text = _artifact_store().get_text(str(row["uri"]))
        except (ArtifactNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=f"Artifact object missing: {artifact_id}") from exc
        headers = {
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Spawnd-Redaction-Policy": str(row.get("redaction_policy") or "unknown"),
        }
        if row.get("sha256"):
            headers["ETag"] = f'"{row["sha256"]}"'
        return Response(text, media_type=str(row.get("content_type") or "text/plain"), headers=headers)

    @app.get("/runs/{run_id}/artifacts/{artifact_id}/download")
    def artifact_download(run_id: str, artifact_id: str) -> StreamingResponse:
        row = _repository().get_artifact(artifact_id)
        if row is None or row.get("run_id") != run_id:
            raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_id}")
        try:
            chunks = _artifact_store().iter_bytes(str(row["uri"]))
        except (ArtifactNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=f"Artifact object missing: {artifact_id}") from exc
        headers = {
            "Cache-Control": "private, max-age=31536000, immutable",
            "Content-Disposition": f'attachment; filename="{artifact_id}.txt"',
            "Content-Length": str(int(row.get("size_bytes") or 0)),
            "X-Spawnd-Redaction-Policy": str(row.get("redaction_policy") or "unknown"),
        }
        if row.get("sha256"):
            headers["ETag"] = f'"{row["sha256"]}"'
        return StreamingResponse(
            chunks,
            media_type=str(row.get("content_type") or "application/octet-stream"),
            headers=headers,
        )

    @app.get("/runs/{run_id}/traces")
    def traces(run_id: str, agent: str | None = None) -> list[dict[str, Any]]:
        return _repository().fetch_trace_spans(run_id, agent)

    @app.get("/runs/{run_id}/provenance")
    def provenance(run_id: str, agent: str | None = None) -> list[dict[str, Any]]:
        return _repository().get_git_provenance(run_id, agent)

    @app.get("/runs/{run_id}/usage")
    def usage(run_id: str, agent: str | None = None) -> dict[str, Any]:
        repo = _repository()
        tokens = repo.get_token_usage(run_id, agent)
        costs = repo.get_cost_usage(run_id, agent)
        return {"token_usage": tokens, "cost_usage": costs, "by_agent": _usage_rollup(tokens, costs)}

    @app.get("/runs/{run_id}/sessions")
    def sessions(run_id: str, agent: str | None = None) -> list[dict[str, Any]]:
        return _repository().get_runtime_sessions(run_id, agent)

    @app.get("/runs/{run_id}/invocations")
    def invocations(run_id: str, agent: str | None = None) -> list[dict[str, Any]]:
        return _repository().get_runtime_invocations(run_id, agent)

    @app.get("/runs/{run_id}/errors")
    def runtime_errors(run_id: str, agent: str | None = None) -> list[dict[str, Any]]:
        return _repository().get_runtime_errors(run_id, agent)

    @app.post("/runs/{run_id}/cancel")
    def cancel(run_id: str) -> dict[str, int]:
        return {"cancelled": cancel_run(run_id, repository=_repository(), coordinator=_coordinator())}

    @app.post("/runs/{run_id}/resume")
    def resume(run_id: str) -> list[dict[str, Any]]:
        return resume_run(run_id, repository=_repository(), coordinator=_coordinator())

    @app.get("/clarifications")
    def pending_clarifications(limit: int = 100) -> list[dict[str, Any]]:
        return _repository().list_pending_clarifications(limit=limit)

    @app.get("/runs/{run_id}/clarifications")
    def run_clarifications(run_id: str) -> list[dict[str, Any]]:
        return _repository().get_pending_clarifications(run_id)

    @app.post("/runs/{run_id}/clarifications/{clarification_id}/response")
    def answer_clarification(run_id: str, clarification_id: str, body: ClarificationResponseBody) -> dict[str, str]:
        repo = _repository()
        event = repo.get_event(run_id, clarification_id)
        if event is None or event.get("event_type") not in {"clarification", "blocker"}:
            raise HTTPException(status_code=404, detail=f"Clarification not found: {clarification_id}")
        recorded = repo.record_response(run_id, clarification_id, body.response, agent="api")
        if not recorded:
            raise HTTPException(status_code=409, detail=f"Clarification already answered: {clarification_id}")
        return {"clarification_id": clarification_id, "status": "answered"}

    @app.post("/workers/reconcile")
    def reconcile() -> list[dict[str, str]]:
        return reconcile_ready_agents(_repository(), _coordinator())

    @app.post("/workers/outbox/drain")
    def drain_outbox(limit: int = 100) -> list[dict[str, str]]:
        return drain_queue_outbox(_repository(), _coordinator(), limit=limit)

    @app.get("/workers")
    def workers() -> dict[str, Any]:
        coordinator = _coordinator()
        return {
            "queue_depth": coordinator.queue_depth(),
            "submission_queue_depth": coordinator.submission_queue_depth(),
            "workers": _repository().list_worker_nodes(),
        }

    return app
