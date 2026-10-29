import asyncio
import json
import os
import uuid

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.metrics import WS_CONNECTIONS
from app.core.security import decode_access_token
from app.realtime.access import can_join
from app.realtime.rooms import rooms

router = APIRouter(tags=["realtime"])
log = structlog.get_logger()

AUTH_TIMEOUT_SECONDS = 10
MAX_ROOMS_PER_SOCKET = 20


class Connection:
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.user_id: uuid.UUID | None = None
        self._lock = asyncio.Lock()  # the subscriber task and this handler both send

    async def send_text(self, data: str) -> None:
        async with self._lock:
            await self.websocket.send_text(data)

    async def send(self, type_: str, room: str | None = None, **payload: object) -> None:
        await self.send_text(json.dumps({"type": type_, "room": room, "payload": payload}))


@router.websocket("/ws")
async def realtime(websocket: WebSocket) -> None:
    """Protocol (JSON messages):

    client → {"type": "auth", "token": "<access token>"}   first message, within 10 s
    server → {"type": "ready", "payload": {"user_id", "worker"}}
    client → {"type": "subscribe", "room": "event:<id>"}   also playlist:, device:, user:
    server → {"type": "subscribed", "room", "payload": {"seq"}}  or "error"
    server → {"type", "room", "seq", "payload"}             events, seq per room
    client → {"type": "unsubscribe", "room"} / {"type": "ping"}

    Commands never go through the socket: it only pushes. Writes use REST.
    """
    await websocket.accept()
    conn = Connection(websocket)
    headers = websocket.headers
    log_ctx = log.bind(
        platform=headers.get("x-platform"),
        device=headers.get("x-device"),
        app_version=headers.get("x-app-version"),
    )
    WS_CONNECTIONS.inc()
    try:
        conn.user_id = await _authenticate(websocket)
        if conn.user_id is None:
            await websocket.close(code=4401, reason="authentication required")
            return
        log_ctx = log_ctx.bind(user_id=str(conn.user_id))
        log_ctx.info("ws_connected")
        await conn.send("ready", user_id=str(conn.user_id), worker=os.getpid())

        while True:
            try:
                message = json.loads(await websocket.receive_text())
                kind, room = message.get("type"), message.get("room")
            except (json.JSONDecodeError, AttributeError):
                await conn.send("error", code="bad_message")
                continue
            if kind == "ping":
                await conn.send("pong")
            elif kind == "subscribe" and isinstance(room, str) and len(room) <= 100:
                if rooms.room_count(conn) >= MAX_ROOMS_PER_SOCKET:
                    await conn.send("error", room, code="too_many_rooms")
                elif await can_join(conn.user_id, room):
                    rooms.join(room, conn)
                    log_ctx.info("ws_subscribed", room=room)
                    # The client compares this with the next event's seq to detect gaps.
                    await conn.send("subscribed", room, seq=await rooms.current_seq(room))
                else:
                    await conn.send("error", room, code="forbidden")
            elif kind == "unsubscribe" and isinstance(room, str):
                rooms.leave(room, conn)
            else:
                await conn.send("error", code="unknown_type")
    except WebSocketDisconnect:
        pass
    finally:
        rooms.leave_all(conn)
        WS_CONNECTIONS.dec()
        log_ctx.info("ws_disconnected")


async def _authenticate(websocket: WebSocket) -> uuid.UUID | None:
    """The token comes in the first message, not the URL: URLs end up in access logs."""
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), AUTH_TIMEOUT_SECONDS)
        message = json.loads(raw)
    except (TimeoutError, json.JSONDecodeError):
        return None
    if not isinstance(message, dict) or message.get("type") != "auth":
        return None
    return decode_access_token(str(message.get("token", "")))
