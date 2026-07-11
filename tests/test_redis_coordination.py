from __future__ import annotations

from collections.abc import Iterator

import fakeredis
import pytest
import redis.asyncio

from spawnd.coordination.redis import AgentJob, aiter_live_events, RedisCoordinator, RunSubmissionJob


def test_read_agent_recovers_after_redis_state_is_lost() -> None:
    redis = fakeredis.FakeRedis(decode_responses=True)
    coordinator = RedisCoordinator(redis)

    redis.flushdb()
    assert coordinator.read_agent('worker-1', block_ms=1) is None

    coordinator.enqueue_agent('run-1', 'agent-1')
    job = coordinator.read_agent('worker-1', block_ms=1)

    assert job is not None
    assert job == AgentJob(run_id='run-1', agent='agent-1', message_id=job.message_id)


def test_read_submission_recovers_after_redis_state_is_lost() -> None:
    redis = fakeredis.FakeRedis(decode_responses=True)
    coordinator = RedisCoordinator(redis)

    redis.flushdb()
    assert coordinator.read_submission('submitter-1', block_ms=1) is None

    coordinator.enqueue_submission({'kind': 'plan', 'run_id': 'run-1'})
    job = coordinator.read_submission('submitter-1', block_ms=1)

    assert job is not None
    assert job == RunSubmissionJob(payload={'kind': 'plan', 'run_id': 'run-1'}, message_id=job.message_id)


def test_ack_ignores_missing_redis_group_after_state_is_lost() -> None:
    redis = fakeredis.FakeRedis(decode_responses=True)
    coordinator = RedisCoordinator(redis)
    coordinator.enqueue_agent('run-1', 'agent-1')
    agent_job = coordinator.read_agent('worker-1', block_ms=1)
    coordinator.enqueue_submission({'kind': 'plan', 'run_id': 'run-1'})
    submission_job = coordinator.read_submission('submitter-1', block_ms=1)
    assert agent_job is not None
    assert submission_job is not None

    redis.flushdb()

    coordinator.ack_agent(agent_job)
    coordinator.ack_submission(submission_job)


def test_queue_depth_uses_consumer_group_backlog_not_stream_history() -> None:
    redis = fakeredis.FakeRedis(decode_responses=True)
    coordinator = RedisCoordinator(redis)
    coordinator.enqueue_agent('run-1', 'agent-1')

    assert coordinator.queue_depth() == 1
    job = coordinator.read_agent('worker-1', block_ms=1)
    assert job is not None
    assert coordinator.queue_depth() == 1

    coordinator.ack_agent(job)

    assert redis.xlen('spawnd:agents:ready') == 1
    assert coordinator.queue_depth() == 0


def test_submission_queue_depth_uses_consumer_group_backlog_not_stream_history() -> None:
    redis = fakeredis.FakeRedis(decode_responses=True)
    coordinator = RedisCoordinator(redis)
    coordinator.enqueue_submission({'kind': 'plan', 'run_id': 'run-1'})

    assert coordinator.submission_queue_depth() == 1
    job = coordinator.read_submission('submitter-1', block_ms=1)
    assert job is not None
    assert coordinator.submission_queue_depth() == 1

    coordinator.ack_submission(job)

    assert redis.xlen('spawnd:runs:submit') == 1
    assert coordinator.submission_queue_depth() == 0


def test_subscribe_events_skips_malformed_payloads() -> None:
    class FakePubSub:
        def __init__(self) -> None:
            self.closed = False

        def subscribe(self, channel: str) -> None:
            assert channel == "spawnd:runs:run-1:events"

        def listen(self) -> Iterator[dict[str, object]]:
            messages: list[dict[str, object]] = [
                {"type": "subscribe", "data": 1},
                {"type": "message", "data": None},
                {"type": "message", "data": b"\xff"},
                {"type": "message", "data": "[]"},
                {"type": "message", "data": "not-json"},
                {"type": "message", "data": '{"type": "started"}'},
            ]
            return iter(messages)

        def close(self) -> None:
            self.closed = True

    class FakeRedis:
        def __init__(self, pubsub: FakePubSub) -> None:
            self._pubsub = pubsub

        def xgroup_create(self, stream: str, group: str, *, id: str, mkstream: bool) -> None:
            return None

        def pubsub(self) -> FakePubSub:
            return self._pubsub

    pubsub = FakePubSub()
    coordinator = RedisCoordinator(FakeRedis(pubsub))

    assert list(coordinator.subscribe_events("run-1")) == [{"type": "started"}]
    assert pubsub.closed is True


def test_subscribe_events_closes_pubsub_when_subscription_fails() -> None:
    class FakePubSub:
        def __init__(self) -> None:
            self.closed = False

        def subscribe(self, channel: str) -> None:
            raise RuntimeError(f"cannot subscribe to {channel}")

        def close(self) -> None:
            self.closed = True

    class FakeRedis:
        def __init__(self, pubsub: FakePubSub) -> None:
            self._pubsub = pubsub

        def xgroup_create(self, stream: str, group: str, *, id: str, mkstream: bool) -> None:
            return None

        def pubsub(self) -> FakePubSub:
            return self._pubsub

    pubsub = FakePubSub()
    coordinator = RedisCoordinator(FakeRedis(pubsub))

    with pytest.raises(RuntimeError, match="cannot subscribe"):
        _ = list(coordinator.subscribe_events("run-1"))

    assert pubsub.closed is True


@pytest.mark.asyncio
async def test_aiter_live_events_returns_idle_ticks_for_malformed_payloads(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePubSub:
        def __init__(self) -> None:
            messages: list[dict[str, object]] = [
                {"type": "message", "data": None},
                {"type": "message", "data": b"\xff"},
                {"type": "message", "data": "[]"},
                {"type": "message", "data": '{"type": "started"}'},
            ]
            self.messages: Iterator[dict[str, object]] = iter(messages)
            self.closed = False

        async def subscribe(self, channel: str) -> None:
            assert channel == "spawnd:runs:run-1:events"

        async def get_message(self, *, ignore_subscribe_messages: bool, timeout: float) -> dict[str, object]:
            assert ignore_subscribe_messages is True
            assert timeout == 0.01
            return next(self.messages)

        async def aclose(self) -> None:
            self.closed = True

    class FakeRedis:
        def __init__(self, pubsub: FakePubSub) -> None:
            self._pubsub = pubsub
            self.closed = False

        def pubsub(self) -> FakePubSub:
            return self._pubsub

        async def aclose(self) -> None:
            self.closed = True

    pubsub = FakePubSub()
    client = FakeRedis(pubsub)

    def from_url(*args: object, **kwargs: object) -> FakeRedis:
        return client

    monkeypatch.setattr(redis.asyncio.Redis, "from_url", from_url)
    events = aiter_live_events("redis://example.test/0", "run-1", tick_seconds=0.01)

    assert await anext(events) is None
    assert await anext(events) is None
    assert await anext(events) is None
    assert await anext(events) == {"type": "started"}

    await events.aclose()
    assert pubsub.closed is True
    assert client.closed is True


@pytest.mark.asyncio
async def test_aiter_live_events_closes_resources_when_subscription_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePubSub:
        def __init__(self) -> None:
            self.closed = False

        async def subscribe(self, channel: str) -> None:
            raise RuntimeError(f"cannot subscribe to {channel}")

        async def aclose(self) -> None:
            self.closed = True

    class FakeRedis:
        def __init__(self, pubsub: FakePubSub) -> None:
            self._pubsub = pubsub
            self.closed = False

        def pubsub(self) -> FakePubSub:
            return self._pubsub

        async def aclose(self) -> None:
            self.closed = True

    pubsub = FakePubSub()
    client = FakeRedis(pubsub)

    def from_url(*args: object, **kwargs: object) -> FakeRedis:
        return client

    monkeypatch.setattr(redis.asyncio.Redis, "from_url", from_url)
    events = aiter_live_events("redis://example.test/0", "run-1")

    with pytest.raises(RuntimeError, match="cannot subscribe"):
        _ = await anext(events)

    assert pubsub.closed is True
    assert client.closed is True
