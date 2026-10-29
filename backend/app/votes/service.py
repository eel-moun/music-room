import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import row_exists
from app.core.errors import forbidden, not_found
from app.policies.access import can_view, can_vote
from app.realtime.rooms import rooms
from app.votes.models import Event, EventInvite, EventTrack, Vote
from app.votes.schemas import QueueOut, QueueTrackOut


class EventAccess:
    def __init__(self, event: Event, user_id: uuid.UUID, is_invited: bool) -> None:
        self.event = event
        self.is_owner = event.owner_id == user_id
        self.is_invited = is_invited

    def require_owner(self) -> None:
        if not self.is_owner:
            raise forbidden("owner_only", "Only the event owner can do this")

    def require_vote(self, position: tuple[float, float] | None) -> None:
        decision = can_vote(
            self.event,
            is_owner=self.is_owner,
            is_invited=self.is_invited,
            now=datetime.now(UTC),  # server time, never the client's clock
            position=position,
        )
        if not decision.allowed:
            raise forbidden(decision.code, decision.message)


async def load_event(
    session: AsyncSession, event_id: uuid.UUID, user_id: uuid.UUID, *, for_update: bool = False
) -> EventAccess:
    """Loads an event the user may see; 404 otherwise (private events stay invisible)."""
    query = select(Event).where(Event.id == event_id)
    event = await session.scalar(query.with_for_update() if for_update else query)
    if event is None:
        raise not_found("Event")
    invited = await row_exists(session, EventInvite, event_id=event_id, user_id=user_id)
    access = EventAccess(event, user_id, invited)
    if not can_view(event.visibility, is_owner=access.is_owner, is_invited=invited):
        raise not_found("Event")
    return access


def ranking_query(event: Event, user_id: uuid.UUID | None) -> Select:
    """The queue: unplayed tracks except the one playing, by votes then suggestion time.
    Computed by the database on every read, so it can never drift from the votes."""
    votes = func.count(Vote.id).label("votes")
    # Without a viewer (realtime push) the column is computed for a nobody id and ignored.
    viewer = user_id or uuid.UUID(int=0)
    voted_by_me = func.coalesce(func.bool_or(Vote.user_id == viewer), False).label("voted_by_me")
    query = (
        select(EventTrack, votes, voted_by_me)
        .outerjoin(Vote, Vote.track_id == EventTrack.id)
        .where(EventTrack.event_id == event.id, EventTrack.played_at.is_(None))
        .group_by(EventTrack.id)
        .order_by(votes.desc(), EventTrack.suggested_at.asc(), EventTrack.id)
    )
    if event.now_playing_id is not None:
        query = query.where(EventTrack.id != event.now_playing_id)
    return query


def _track_out(track: EventTrack, votes: int, voted: bool | None) -> QueueTrackOut:
    return QueueTrackOut(
        id=track.id,
        provider=track.provider,
        external_id=track.external_id,
        title=track.title,
        artist=track.artist,
        duration=track.duration,
        artwork_url=track.artwork_url,
        votes=votes,
        voted_by_me=bool(voted) if voted is not None else None,
        suggested_by=track.suggested_by,
        suggested_at=track.suggested_at,
    )


async def get_queue(session: AsyncSession, event: Event, user_id: uuid.UUID | None) -> QueueOut:
    rows = (await session.execute(ranking_query(event, user_id))).all()
    now_playing = None
    if event.now_playing_id is not None:
        track = await session.get(EventTrack, event.now_playing_id)
        if track is not None:
            count = await session.scalar(select(func.count()).where(Vote.track_id == track.id))
            now_playing = _track_out(track, count or 0, None)
    return QueueOut(
        event_id=event.id,
        now_playing=now_playing,
        queue=[_track_out(t, v, me if user_id else None) for t, v, me in rows],
    )


async def publish_queue(session: AsyncSession, event: Event) -> None:
    """Pushes the new ranking to everyone in the event room, on every worker."""
    queue = await get_queue(session, event, None)
    await rooms.publish(f"event:{event.id}", "queue.updated", queue.model_dump(mode="json"))
