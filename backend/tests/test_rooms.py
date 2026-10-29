"""RoomManager against a real Redis: two managers sharing it behave like two workers."""

import asyncio
import json
import uuid

import pytest

from app.core.redis import redis_client
from app.realtime.rooms import RoomManager


class FakeSocket:
    def __init__(self, user_id: uuid.UUID | None = None, broken: bool = False) -> None:
        self.user_id = user_id or uuid.uuid4()
        self.broken = broken
        self.received: list[dict] = []

    async def send_text(self, data: str) -> None:
        if self.broken:
            raise ConnectionError("client gone")
        self.received.append(json.loads(data))


@pytest.fixture
async def two_workers():
    workers = [RoomManager(redis_client), RoomManager(redis_client)]
    tasks = [asyncio.create_task(w.run_subscriber()) for w in workers]
    await asyncio.wait_for(asyncio.gather(*(w.ready.wait() for w in workers)), timeout=5)
    yield workers
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def until(condition) -> None:
    """Wait (max 2s) for the subscriber tasks to deliver."""
    async with asyncio.timeout(2):
        while not condition():  # noqa: ASYNC110 - polling test state, no event to wait on
            await asyncio.sleep(0.01)


async def test_event_reaches_sockets_on_every_worker(two_workers):
    worker_a, worker_b = two_workers
    alice, bob = FakeSocket(), FakeSocket()
    worker_a.join("event:1", alice)
    worker_b.join("event:1", bob)

    seq = await worker_a.publish("event:1", "vote", {"track": "t1"})

    await until(lambda: alice.received and bob.received)
    expected = {"type": "vote", "room": "event:1", "seq": seq, "payload": {"track": "t1"}}
    assert alice.received == [expected]
    assert bob.received == [expected]


async def test_other_rooms_receive_nothing(two_workers):
    worker_a, worker_b = two_workers
    inside, outside = FakeSocket(), FakeSocket()
    worker_a.join("event:1", inside)
    worker_b.join("event:2", outside)

    await worker_b.publish("event:1", "vote", {})

    await until(lambda: inside.received)
    await asyncio.sleep(0.1)
    assert outside.received == []


async def test_seq_increases_per_room(two_workers):
    worker_a, worker_b = two_workers
    first = await worker_a.publish("event:1", "x", {})
    second = await worker_b.publish("event:1", "x", {})
    assert second == first + 1
    assert await worker_a.current_seq("event:1") == second


async def test_dead_socket_is_dropped(two_workers):
    worker_a, _ = two_workers
    alive, dead = FakeSocket(), FakeSocket(broken=True)
    worker_a.join("event:1", alive)
    worker_a.join("event:1", dead)

    await worker_a.publish("event:1", "x", {})
    await until(lambda: alive.received)

    assert worker_a._rooms["event:1"] == {alive}


async def test_kick_removes_user_on_every_worker(two_workers):
    worker_a, worker_b = two_workers
    friend = uuid.uuid4()
    on_a, on_b, other = FakeSocket(friend), FakeSocket(friend), FakeSocket()
    worker_a.join("device:1", on_a)
    worker_b.join("device:1", on_b)
    worker_b.join("device:1", other)

    await worker_a.kick("device:1", friend)

    await until(lambda: on_a.received and on_b.received)
    assert on_a.received[0]["type"] == "unsubscribed"
    assert worker_a.room_count(on_a) == 0
    assert worker_b.room_count(on_b) == 0
    assert worker_b.room_count(other) == 1
