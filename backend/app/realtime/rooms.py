import asyncio
import json
import uuid
from collections import defaultdict
from typing import Any, Protocol

import structlog
from redis.asyncio import Redis

from app.core.metrics import WS_EVENTS
from app.core.redis import redis_client

log = structlog.get_logger()

CHANNEL_PREFIX = "room:"
KICK_CHANNEL = "control:kick"
SEND_TIMEOUT_SECONDS = 2.0


class Socket(Protocol):
    """What the rooms module needs from a connection (lets tests pass fakes)."""

    user_id: uuid.UUID | None

    async def send_text(self, data: str) -> None: ...


class RoomManager:
    """Fans events out to every socket in a room, across all workers.

    Each worker keeps its own sockets in memory. Events go through Redis pub/sub,
    so every worker receives them and forwards them to its local sockets.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._rooms: dict[str, set[Socket]] = defaultdict(set)
        self.ready = asyncio.Event()  # set once the Redis subscription is active

    def join(self, room: str, socket: Socket) -> None:
        self._rooms[room].add(socket)

    def leave(self, room: str, socket: Socket) -> None:
        sockets = self._rooms.get(room)
        if sockets is None:
            return
        sockets.discard(socket)
        if not sockets:
            del self._rooms[room]

    def room_count(self, socket: Socket) -> int:
        return sum(socket in sockets for sockets in self._rooms.values())

    def leave_all(self, socket: Socket) -> None:
        for room in [r for r, sockets in self._rooms.items() if socket in sockets]:
            self.leave(room, socket)

    async def current_seq(self, room: str) -> int:
        return int(await self._redis.get(f"{CHANNEL_PREFIX}{room}:seq") or 0)

    async def publish(self, room: str, type_: str, payload: dict[str, Any]) -> int:
        """Send an event to the room on every worker. Returns its sequence number."""
        # One counter per room, shared by all workers: clients can spot gaps.
        seq = await self._redis.incr(f"{CHANNEL_PREFIX}{room}:seq")
        envelope = {"type": type_, "room": room, "seq": seq, "payload": payload}
        await self._redis.publish(f"{CHANNEL_PREFIX}{room}", json.dumps(envelope))
        return seq

    async def kick(self, room: str, user_id: uuid.UUID) -> None:
        """Remove a user's sockets from a room on every worker (access was revoked)."""
        await self._redis.publish(KICK_CHANNEL, json.dumps({"room": room, "user_id": str(user_id)}))

    async def run_subscriber(self) -> None:
        """Listen to every room channel and forward to local sockets. Runs until cancelled."""
        while True:
            pubsub = self._redis.pubsub()
            try:
                await pubsub.psubscribe(f"{CHANNEL_PREFIX}*")
                await pubsub.subscribe(KICK_CHANNEL)
                self.ready.set()
                async for message in pubsub.listen():
                    if message["type"] == "pmessage":
                        room = message["channel"].removeprefix(CHANNEL_PREFIX)
                        await self._broadcast_local(room, message["data"])
                    elif message["type"] == "message" and message["channel"] == KICK_CHANNEL:
                        data = json.loads(message["data"])
                        await self._kick_local(data["room"], uuid.UUID(data["user_id"]))
            except asyncio.CancelledError:
                raise
            except Exception:
                # Pub/sub keeps nothing: events published while we're down are lost.
                # Clients refetch state on reconnect, so we only log and retry.
                self.ready.clear()
                log.exception("realtime_subscriber_failed")
                await asyncio.sleep(1)
            finally:
                await pubsub.aclose()

    async def _send(self, socket: Socket, data: str) -> None:
        # A client whose network stalls would otherwise block every room on this worker.
        await asyncio.wait_for(socket.send_text(data), SEND_TIMEOUT_SECONDS)

    async def _broadcast_local(self, room: str, data: str) -> None:
        sockets = list(self._rooms.get(room, ()))
        # gather: one slow client doesn't delay the others.
        results = await asyncio.gather(
            *(self._send(socket, data) for socket in sockets), return_exceptions=True
        )
        for socket, result in zip(sockets, results, strict=True):
            if isinstance(result, BaseException):
                self.leave_all(socket)
            else:
                WS_EVENTS.inc()

    async def _kick_local(self, room: str, user_id: uuid.UUID) -> None:
        for socket in [s for s in self._rooms.get(room, ()) if s.user_id == user_id]:
            self.leave(room, socket)
            notice = {"type": "unsubscribed", "room": room, "payload": {"reason": "access_revoked"}}
            try:
                await self._send(socket, json.dumps(notice))
            except Exception:
                self.leave_all(socket)


rooms = RoomManager(redis_client)
