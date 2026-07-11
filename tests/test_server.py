"""Tests for the deployed HTTP API boundary."""
from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from spawnd import server
from spawnd.coordination.redis import InMemoryCoordinator
from tests.deployed_helpers import make_repo


AUTH = {'Authorization': 'Bearer test-token'}


def test_health_metrics_are_available_without_auth(monkeypatch):
    monkeypatch.delenv('SPAWND_API_TOKEN', raising=False)
    client = TestClient(server.create_app())

    assert client.get('/healthz').status_code == 200
    assert client.get('/readyz').status_code == 200
    metrics = client.get('/metrics')
    assert metrics.status_code == 200
    assert 'spawnd_backend_configured' in metrics.text


def test_http_api_requires_bearer_token(monkeypatch):
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    client = TestClient(server.create_app())

    assert client.get('/runs/run-1').status_code == 401
    assert client.get('/runs/run-1', headers={'Authorization': 'Bearer wrong'}).status_code == 401


def test_http_api_rejects_unsafe_path_ids(monkeypatch) -> None:
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    client = TestClient(server.create_app())

    response = client.post(
        '/runs',
        headers=AUTH,
        json={
            'run_id': 'unsafe/id',
            'plan': {'name': 'plan', 'agents': [{'name': 'a', 'prompt': 'task'}]},
        },
    )

    assert response.status_code == 422


def test_http_submit_validates_plan(monkeypatch):
    repo = make_repo()
    coordinator = InMemoryCoordinator()
    monkeypatch.setattr(server, '_repository', lambda: repo)
    monkeypatch.setattr(server, '_coordinator', lambda: coordinator)
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    client = TestClient(server.create_app())

    response = client.post(
        '/runs',
        headers=AUTH,
        json={
            'run_id': 'run-1',
            'plan': {
                'name': 'bad-plan',
                'agents': [{'name': 'a', 'prompt': 'task', 'depends_on': ['missing']}],
            },
        },
    )

    assert response.status_code == 422
    assert response.json()['detail'] == ['Agent a depends on unknown agent: missing']
    assert repo.get_run('run-1') is None


def test_http_submit_rejects_server_local_plan_file(monkeypatch):
    repo = make_repo()
    coordinator = InMemoryCoordinator()
    monkeypatch.setattr(server, '_repository', lambda: repo)
    monkeypatch.setattr(server, '_coordinator', lambda: coordinator)
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    client = TestClient(server.create_app())

    response = client.post('/runs', headers=AUTH, json={'plan_file': '/tmp/plan.yaml'})

    assert response.status_code == 422
    assert repo.list_runs() == []


def test_http_submit_accepts_serialized_plan(monkeypatch):
    repo = make_repo()
    coordinator = InMemoryCoordinator()
    monkeypatch.setattr(server, '_repository', lambda: repo)
    monkeypatch.setattr(server, '_coordinator', lambda: coordinator)
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    client = TestClient(server.create_app())

    response = client.post(
        '/runs',
        headers=AUTH,
        json={
            'run_id': 'run-1',
            'source_repo': '/repo',
            'source_ref': 'origin/main',
            'plan': {'name': 'good-plan', 'agents': [{'name': 'a', 'prompt': 'task'}]},
        },
    )

    assert response.status_code == 200
    assert response.json() == {'run_id': 'run-1'}
    assert repo.get_run('run-1')['source_repo'] == '/repo'
    assert [job.agent for job in coordinator.jobs] == ['a']


def test_http_submission_queue_enqueue_and_drain(monkeypatch):
    repo = make_repo()
    coordinator = InMemoryCoordinator()
    monkeypatch.setattr(server, '_repository', lambda: repo)
    monkeypatch.setattr(server, '_coordinator', lambda: coordinator)
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    client = TestClient(server.create_app())

    response = client.post(
        '/submissions',
        headers=AUTH,
        json={
            'kind': 'plan',
            'run_id': 'queued-run',
            'source_repo': '/repo',
            'plan': {'name': 'queued', 'agents': [{'name': 'a', 'prompt': 'task'}]},
        },
    )

    assert response.status_code == 200
    assert response.json() == {'status': 'queued'}
    assert coordinator.submission_queue_depth() == 1

    response = client.post('/submissions/drain', headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {'status': 'submitted', 'run_id': 'queued-run'}
    assert repo.get_run('queued-run')['source_repo'] == '/repo'


def test_http_template_submit_and_due_schedule_use_deployed_submission(monkeypatch):
    repo = make_repo()
    coordinator = InMemoryCoordinator()
    monkeypatch.setattr(server, '_repository', lambda: repo)
    monkeypatch.setattr(server, '_coordinator', lambda: coordinator)
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    client = TestClient(server.create_app())
    plan_template = """
name: "{name}"
agents:
  - name: contributor
    prompt: "Improve {repo}"
"""

    assert client.post(
        '/templates',
        headers=AUTH,
        json={
            'id': 'contributor',
            'name': 'Contributor',
            'plan_template': plan_template,
            'source_repo_template': '{clone_url}',
            'source_ref_template': '{ref}',
        },
    ).status_code == 200

    response = client.post(
        '/templates/contributor/runs',
        headers=AUTH,
        json={
            'run_id': 'run-template-1',
            'parameters': {
                'name': 'templated',
                'repo': 'acme/app',
                'clone_url': 'https://github.com/acme/app.git',
                'ref': 'main',
            },
        },
    )
    assert response.status_code == 200
    assert repo.get_run('run-template-1')['source_repo'] == 'https://github.com/acme/app.git'
    assert [job.agent for job in coordinator.jobs] == ['contributor']

    response = client.post(
        '/schedules',
        headers=AUTH,
        json={
            'id': 'schedule-1',
            'template_id': 'contributor',
            'name': 'Nightly contributor',
            'interval_seconds': 60,
            'status': 'paused',
            'parameters': {
                'name': 'scheduled',
                'repo': 'acme/app',
                'clone_url': 'https://github.com/acme/app.git',
                'ref': 'main',
            },
        },
    )
    assert response.status_code == 200

    response = client.post('/schedules/run-due', headers=AUTH)
    assert response.status_code == 200
    assert response.json() == []

    response = client.patch('/schedules/schedule-1/status', headers=AUTH, json={'status': 'active'})
    assert response.status_code == 200
    assert response.json() == {'schedule_id': 'schedule-1', 'status': 'active'}

    response = client.post('/schedules/run-due', headers=AUTH)
    assert response.status_code == 200
    assert response.json()[0]['schedule_id'] == 'schedule-1'


def test_github_webhook_requires_valid_signature_and_submits_template(monkeypatch):
    repo = make_repo()
    coordinator = InMemoryCoordinator()
    monkeypatch.setattr(server, '_repository', lambda: repo)
    monkeypatch.setattr(server, '_coordinator', lambda: coordinator)
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    monkeypatch.setenv('SPAWND_GITHUB_WEBHOOK_SECRET', 'webhook-secret')
    client = TestClient(server.create_app())
    plan_template = """
name: "github-{event}"
agents:
  - name: contributor
    prompt: "Review {repo} ({repo_slug}) at {after}; pr {pr_number}; head {head_ref} {head_sha}; base {base_ref} {base_sha}"
"""
    client.post(
        '/templates',
        headers=AUTH,
        json={
            'id': 'github-contributor',
            'name': 'GitHub Contributor',
            'plan_template': plan_template,
            'source_repo_template': '{clone_url}',
            'source_ref_template': '{after}',
        },
    )
    payload = {
        'ref': 'refs/heads/main',
        'after': 'abc123',
        'before': 'def456',
        'repository': {
            'full_name': 'acme/app',
            'clone_url': 'https://github.com/acme/app.git',
            'ssh_url': 'git@github.com:acme/app.git',
            'default_branch': 'main',
        },
    }
    body = json.dumps(payload).encode('utf-8')
    signature = 'sha256=' + hmac.new(b'webhook-secret', body, hashlib.sha256).hexdigest()

    rejected = client.post(
        '/webhooks/github/github-contributor',
        content=body,
        headers={'X-GitHub-Event': 'push', 'X-Hub-Signature-256': 'sha256=bad'},
    )
    assert rejected.status_code == 401

    accepted = client.post(
        '/webhooks/github/github-contributor',
        content=body,
        headers={'X-GitHub-Event': 'push', 'X-Hub-Signature-256': signature, 'Content-Type': 'application/json'},
    )
    assert accepted.status_code == 200
    run = repo.get_run(accepted.json()['run_id'])
    assert run is not None
    assert run['source_repo'] == 'https://github.com/acme/app.git'
    assert run['source_ref'] == 'abc123'


def test_github_webhook_ping_does_not_submit_run(monkeypatch):
    repo = make_repo()
    coordinator = InMemoryCoordinator()
    monkeypatch.setattr(server, '_repository', lambda: repo)
    monkeypatch.setattr(server, '_coordinator', lambda: coordinator)
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    monkeypatch.setenv('SPAWND_GITHUB_WEBHOOK_SECRET', 'webhook-secret')
    client = TestClient(server.create_app())
    payload = {'zen': 'test', 'repository': {'full_name': 'acme/app'}}
    body = json.dumps(payload).encode('utf-8')
    signature = 'sha256=' + hmac.new(b'webhook-secret', body, hashlib.sha256).hexdigest()

    response = client.post(
        '/webhooks/github/github-contributor',
        content=body,
        headers={'X-GitHub-Event': 'ping', 'X-Hub-Signature-256': signature, 'Content-Type': 'application/json'},
    )

    assert response.status_code == 200
    assert response.json() == {'status': 'pong'}
    assert repo.list_runs() == []


def test_http_list_runs_excludes_plan_spec(monkeypatch):
    repo = make_repo()
    coordinator = InMemoryCoordinator()
    monkeypatch.setattr(server, '_repository', lambda: repo)
    monkeypatch.setattr(server, '_coordinator', lambda: coordinator)
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    client = TestClient(server.create_app())

    assert client.get('/runs').status_code == 401

    submitted = client.post(
        '/runs',
        headers=AUTH,
        json={'run_id': 'run-1', 'plan': {'name': 'good-plan', 'agents': [{'name': 'a', 'prompt': 'task'}]}},
    )
    assert submitted.status_code == 200

    response = client.get('/runs', headers=AUTH)

    assert response.status_code == 200
    rows = response.json()
    assert [row['run_id'] for row in rows] == ['run-1']
    assert rows[0]['status'] == 'queued'
    assert 'spec' not in rows[0]


def test_http_list_runs_filters_and_paginates(monkeypatch):
    repo = make_repo()
    coordinator = InMemoryCoordinator()
    monkeypatch.setattr(server, '_repository', lambda: repo)
    monkeypatch.setattr(server, '_coordinator', lambda: coordinator)
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    client = TestClient(server.create_app())

    for index in (1, 2):
        submitted = client.post(
            '/runs',
            headers=AUTH,
            json={'run_id': f'run-{index}', 'plan': {'name': f'plan-{index}', 'agents': [{'name': 'a', 'prompt': 'task'}]}},
        )
        assert submitted.status_code == 200

    page = client.get('/runs', headers=AUTH, params={'limit': 1, 'offset': 1})
    assert page.status_code == 200
    assert [row['run_id'] for row in page.json()] == ['run-1']

    queued = client.get('/runs', headers=AUTH, params={'status': 'queued'})
    assert {row['run_id'] for row in queued.json()} == {'run-1', 'run-2'}

    running = client.get('/runs', headers=AUTH, params={'status': 'running'})
    assert running.json() == []


def test_http_list_schedules(monkeypatch):
    repo = make_repo()
    coordinator = InMemoryCoordinator()
    monkeypatch.setattr(server, '_repository', lambda: repo)
    monkeypatch.setattr(server, '_coordinator', lambda: coordinator)
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    client = TestClient(server.create_app())

    assert client.get('/schedules').status_code == 401

    template = client.post(
        '/templates',
        headers=AUTH,
        json={'id': 'tpl-1', 'name': 'tpl', 'plan_template': 'name: {name}\nagents:\n  - name: a\n    prompt: task\n'},
    )
    assert template.status_code == 200
    schedule = client.post(
        '/schedules',
        headers=AUTH,
        json={'id': 'sched-1', 'template_id': 'tpl-1', 'name': 'nightly', 'interval_seconds': 3600, 'status': 'paused'},
    )
    assert schedule.status_code == 200

    response = client.get('/schedules', headers=AUTH)

    assert response.status_code == 200
    rows = response.json()
    assert [row['id'] for row in rows] == ['sched-1']
    assert rows[0]['template_id'] == 'tpl-1'
    assert rows[0]['status'] == 'paused'


def test_http_run_usage_rollup(monkeypatch):
    repo = make_repo()
    coordinator = InMemoryCoordinator()
    monkeypatch.setattr(server, '_repository', lambda: repo)
    monkeypatch.setattr(server, '_coordinator', lambda: coordinator)
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    client = TestClient(server.create_app())

    submitted = client.post(
        '/runs',
        headers=AUTH,
        json={'run_id': 'run-1', 'plan': {'name': 'plan', 'agents': [{'name': 'a', 'prompt': 'task'}]}},
    )
    assert submitted.status_code == 200
    repo.record_token_usage(run_id='run-1', agent='a', provider='anthropic', scope='invocation', input_tokens=100, output_tokens=40)
    repo.record_token_usage(run_id='run-1', agent='a', provider='anthropic', scope='invocation', input_tokens=10, output_tokens=5, cached_input_tokens=7)
    repo.record_cost_usage(run_id='run-1', agent='a', provider='anthropic', amount_usd=0.25, source='anthropic')

    response = client.get('/runs/run-1/usage', headers=AUTH)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload['token_usage']) == 2
    assert len(payload['cost_usage']) == 1
    rollup = {entry['agent']: entry for entry in payload['by_agent']}
    assert rollup['a']['input_tokens'] == 110
    assert rollup['a']['output_tokens'] == 45
    assert rollup['a']['cached_input_tokens'] == 7
    assert rollup['a']['total_tokens'] == 162
    assert rollup['a']['amount_usd'] == 0.25


def test_http_runtime_drilldown_routes(monkeypatch):
    repo = make_repo()
    coordinator = InMemoryCoordinator()
    monkeypatch.setattr(server, '_repository', lambda: repo)
    monkeypatch.setattr(server, '_coordinator', lambda: coordinator)
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    client = TestClient(server.create_app())

    submitted = client.post(
        '/runs',
        headers=AUTH,
        json={'run_id': 'run-1', 'plan': {'name': 'plan', 'agents': [{'name': 'a', 'prompt': 'task'}]}},
    )
    assert submitted.status_code == 200
    claim = repo.claim_agent('run-1', 'a', worker_id='worker-1')
    assert claim is not None
    session_id = repo.record_runtime_session(
        attempt_id=claim.attempt_id, run_id='run-1', agent='a', provider='anthropic', runtime='claude', model='claude-fable-5'
    )
    invocation_id = repo.start_runtime_invocation(attempt_id=claim.attempt_id, run_id='run-1', agent='a', kind='agent', session_id=session_id)
    repo.record_runtime_error(run_id='run-1', agent='a', attempt_id=claim.attempt_id, source='runtime', code='boom', message='exploded')

    sessions = client.get('/runs/run-1/sessions', headers=AUTH)
    assert sessions.status_code == 200
    assert [row['id'] for row in sessions.json()] == [session_id]

    invocations = client.get('/runs/run-1/invocations', headers=AUTH, params={'agent': 'a'})
    assert invocations.status_code == 200
    assert [row['id'] for row in invocations.json()] == [invocation_id]

    errors = client.get('/runs/run-1/errors', headers=AUTH)
    assert errors.status_code == 200
    assert [row['code'] for row in errors.json()] == ['boom']


def test_http_artifact_content(monkeypatch):
    from spawnd.artifacts.store import InMemoryArtifactStore

    repo = make_repo()
    coordinator = InMemoryCoordinator()
    store = InMemoryArtifactStore()
    monkeypatch.setattr(server, '_repository', lambda: repo)
    monkeypatch.setattr(server, '_coordinator', lambda: coordinator)
    monkeypatch.setattr(server, '_artifact_store', lambda: store)
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    client = TestClient(server.create_app())

    submitted = client.post(
        '/runs',
        headers=AUTH,
        json={'run_id': 'run-1', 'plan': {'name': 'plan', 'agents': [{'name': 'a', 'prompt': 'task'}]}},
    )
    assert submitted.status_code == 200
    blob = store.put_text('runs/run-1/a/output.txt', 'check output line\n')
    artifact_id = repo.record_artifact(
        run_id='run-1',
        agent='a',
        kind='output',
        uri=blob.uri,
        sha256=blob.sha256,
        size_bytes=blob.size_bytes,
        redaction_policy=blob.redaction_policy,
        content_type=blob.content_type,
    )

    response = client.get(f'/runs/run-1/artifacts/{artifact_id}/content', headers=AUTH)
    assert response.status_code == 200
    assert response.text == 'check output line\n'
    assert response.headers['x-spawnd-redaction-policy'] == 'redacted'
    assert response.headers['etag'] == f'"{blob.sha256}"'

    wrong_run = client.get(f'/runs/run-2/artifacts/{artifact_id}/content', headers=AUTH)
    assert wrong_run.status_code == 404

    oversized_blob = store.put_text(
        'runs/run-1/a/huge.txt',
        'x' * (server.MAX_ARTIFACT_CONTENT_BYTES + 1),
    )
    oversized_id = repo.record_artifact(
        run_id='run-1',
        agent='a',
        kind='output',
        uri=oversized_blob.uri,
        sha256=oversized_blob.sha256,
        size_bytes=oversized_blob.size_bytes,
        redaction_policy='redacted',
        content_type='text/plain',
    )
    oversized = client.get(f'/runs/run-1/artifacts/{oversized_id}/content', headers=AUTH)
    assert oversized.status_code == 413

    download = client.get(f'/runs/run-1/artifacts/{oversized_id}/download', headers=AUTH)
    assert download.status_code == 200
    assert len(download.content) == server.MAX_ARTIFACT_CONTENT_BYTES + 1
    assert download.headers['content-disposition'] == f'attachment; filename="{oversized_id}.txt"'

    del store.objects['runs/run-1/a/output.txt']
    missing = client.get(f'/runs/run-1/artifacts/{artifact_id}/content', headers=AUTH)
    assert missing.status_code == 404


def test_http_clarification_list_and_answer(monkeypatch):
    repo = make_repo()
    coordinator = InMemoryCoordinator()
    monkeypatch.setattr(server, '_repository', lambda: repo)
    monkeypatch.setattr(server, '_coordinator', lambda: coordinator)
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    client = TestClient(server.create_app())

    submitted = client.post(
        '/runs',
        headers=AUTH,
        json={'run_id': 'run-1', 'plan': {'name': 'plan', 'agents': [{'name': 'a', 'prompt': 'task'}]}},
    )
    assert submitted.status_code == 200
    clarification_id = repo.append_event('run-1', 'a', 'clarification', {'question': 'Which database?'})

    fleet = client.get('/clarifications', headers=AUTH)
    assert fleet.status_code == 200
    assert [row['id'] for row in fleet.json()] == [clarification_id]

    per_run = client.get('/runs/run-1/clarifications', headers=AUTH)
    assert [row['id'] for row in per_run.json()] == [clarification_id]

    answered = client.post(
        f'/runs/run-1/clarifications/{clarification_id}/response',
        headers=AUTH,
        json={'response': 'Use Postgres'},
    )
    assert answered.status_code == 200
    assert answered.json()['status'] == 'answered'
    assert repo.get_response('run-1', clarification_id)['response'] == 'Use Postgres'
    assert client.get('/clarifications', headers=AUTH).json() == []
    assert client.get('/runs/run-1/clarifications', headers=AUTH).json() == []

    again = client.post(
        f'/runs/run-1/clarifications/{clarification_id}/response',
        headers=AUTH,
        json={'response': 'Use Postgres'},
    )
    assert again.status_code == 409

    missing = client.post(
        '/runs/run-1/clarifications/not-an-event/response',
        headers=AUTH,
        json={'response': 'irrelevant'},
    )
    assert missing.status_code == 404


def test_http_event_stream_replays_and_completes(monkeypatch):
    repo = make_repo()
    coordinator = InMemoryCoordinator()
    monkeypatch.setattr(server, '_repository', lambda: repo)
    monkeypatch.setattr(server, '_coordinator', lambda: coordinator)
    monkeypatch.setenv('SPAWND_API_TOKEN', 'test-token')
    monkeypatch.delenv('SPAWND_REDIS_URL', raising=False)
    client = TestClient(server.create_app())

    assert client.get('/runs/run-1/events/stream').status_code == 401
    assert client.get('/runs/missing/events/stream', headers=AUTH).status_code == 404

    submitted = client.post(
        '/runs',
        headers=AUTH,
        json={'run_id': 'run-1', 'plan': {'name': 'plan', 'agents': [{'name': 'a', 'prompt': 'task'}]}},
    )
    assert submitted.status_code == 200
    delivered_id = repo.append_event("run-1", "a", "delivered", {"sequence": 1})
    missed_id = repo.append_event("run-1", "a", "missed", {"sequence": 2})
    cancelled = client.post('/runs/run-1/cancel', headers=AUTH)
    assert cancelled.status_code == 200

    with client.stream('GET', '/runs/run-1/events/stream', headers=AUTH) as response:
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')
        body = ''.join(response.iter_text())

    assert 'event: run-event' in body
    assert '"event_type": "run_created"' in body
    assert 'event: done' in body
    assert '"status": "cancelled"' in body

    with client.stream(
        'GET',
        '/runs/run-1/events/stream?replay=0',
        headers=AUTH,
    ) as response:
        no_replay_body = ''.join(response.iter_text())

    assert 'event: run-event' not in no_replay_body
    assert 'event: done' in no_replay_body

    resumed_headers = {**AUTH, "Last-Event-ID": delivered_id}
    with client.stream(
        "GET",
        "/runs/run-1/events/stream?replay=1",
        headers=resumed_headers,
    ) as response:
        resumed_body = "".join(response.iter_text())

    assert f"id: {delivered_id}" not in resumed_body
    assert f"id: {missed_id}" in resumed_body
    assert '"event_type": "missed"' in resumed_body
