import uuid

from fastapi import HTTPException

from app.core.db import SessionLocal
from app.delegation.service import authorize_device
from app.playlists.service import load_playlist
from app.votes.service import load_event


async def can_join(user_id: uuid.UUID, room: str) -> bool:
    """A socket may join a room only if its user may read that resource over REST.
    Same policy functions, so REST and realtime can't disagree."""
    kind, _, ident = room.partition(":")
    if kind == "user":
        return ident == str(user_id)
    try:
        resource_id = uuid.UUID(ident)
    except ValueError:
        return False
    async with SessionLocal() as session:
        try:
            match kind:
                case "event":
                    await load_event(session, resource_id, user_id)
                case "playlist":
                    await load_playlist(session, resource_id, user_id)
                case "device":
                    await authorize_device(session, resource_id, user_id, None)
                case _:
                    return False
        except HTTPException:
            return False
    return True
