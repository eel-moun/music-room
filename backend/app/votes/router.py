import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import ValidationError
from sqlalchemy import delete, exists, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser
from app.core.db import SessionDep
from app.core.errors import api_error, not_found
from app.core.types import Visibility
from app.music.router import ProviderDep
from app.realtime.rooms import rooms
from app.users.models import User
from app.users.schemas import UserSummary
from app.votes.models import Event, EventInvite, EventTrack, Vote
from app.votes.schemas import (
    EventOut,
    EventSettings,
    EventUpdate,
    InviteIn,
    Position,
    QueueOut,
    SuggestIn,
)
from app.votes.service import EventAccess, get_queue, load_event, publish_queue, ranking_query

router = APIRouter(prefix="/events", tags=["track vote"])

SETTINGS_FIELDS = list(EventSettings.model_fields)


async def _event_out(session: AsyncSession, access: EventAccess) -> EventOut:
    owner = await session.get(User, access.event.owner_id)
    return EventOut(
        **{f: getattr(access.event, f) for f in SETTINGS_FIELDS},
        id=access.event.id,
        owner=UserSummary.model_validate(owner),
        created_at=access.event.created_at,
        is_owner=access.is_owner,
        is_invited=access.is_invited,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_event(body: EventSettings, user: CurrentUser, session: SessionDep) -> EventOut:
    event = Event(owner_id=user.id, **body.model_dump())
    session.add(event)
    await session.commit()
    return await _event_out(session, EventAccess(event, user.id, False))


@router.get("")
async def list_events(
    user: CurrentUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    mine: bool = False,
) -> list[EventOut]:
    """Events the caller can see: public ones, their own, and private ones they're invited to."""
    invited = exists().where(EventInvite.event_id == Event.id, EventInvite.user_id == user.id)
    query = select(Event).where(
        or_(Event.visibility == Visibility.public, Event.owner_id == user.id, invited)
    )
    if mine:
        query = query.where(or_(Event.owner_id == user.id, invited))
    if q:
        pattern = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Event.name.ilike(f"%{pattern}%", escape="\\"))
    events = list(await session.scalars(query.order_by(Event.created_at.desc()).limit(50)))
    invited_ids = set(
        await session.scalars(
            select(EventInvite.event_id).where(
                EventInvite.user_id == user.id, EventInvite.event_id.in_([e.id for e in events])
            )
        )
    )
    return [await _event_out(session, EventAccess(e, user.id, e.id in invited_ids)) for e in events]


@router.get("/{event_id}")
async def get_event(event_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> EventOut:
    return await _event_out(session, await load_event(session, event_id, user.id))


@router.patch("/{event_id}")
async def update_event(
    event_id: uuid.UUID, body: EventUpdate, user: CurrentUser, session: SessionDep
) -> EventOut:
    access = await load_event(session, event_id, user.id)
    access.require_owner()
    merged = {f: getattr(access.event, f) for f in SETTINGS_FIELDS}
    merged.update(body.model_dump(exclude_unset=True))
    try:
        settings = EventSettings.model_validate(merged)
    except ValidationError as exc:
        raise api_error(422, "invalid_settings", str(exc.errors()[0]["msg"])) from None
    for field, value in settings.model_dump().items():
        setattr(access.event, field, value)
    await session.commit()
    await rooms.publish(f"event:{event_id}", "event.updated", {"event_id": str(event_id)})
    return await _event_out(session, access)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    access = await load_event(session, event_id, user.id)
    access.require_owner()
    await session.delete(access.event)
    await session.commit()
    await rooms.publish(f"event:{event_id}", "event.deleted", {"event_id": str(event_id)})


# --- Invites -----------------------------------------------------------------


@router.get("/{event_id}/invites")
async def list_invites(
    event_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[UserSummary]:
    (await load_event(session, event_id, user.id)).require_owner()
    users = await session.scalars(
        select(User)
        .join(EventInvite, EventInvite.user_id == User.id)
        .where(EventInvite.event_id == event_id)
    )
    return [UserSummary.model_validate(u) for u in users]


@router.post("/{event_id}/invites", status_code=status.HTTP_204_NO_CONTENT)
async def invite(
    event_id: uuid.UUID, body: InviteIn, user: CurrentUser, session: SessionDep
) -> None:
    access = await load_event(session, event_id, user.id)
    access.require_owner()
    if await session.get(User, body.user_id) is None:
        raise not_found("User")
    await session.execute(
        insert(EventInvite).values(event_id=event_id, user_id=body.user_id).on_conflict_do_nothing()
    )
    await session.commit()
    await rooms.publish(
        f"user:{body.user_id}",
        "event.invited",
        {"event_id": str(event_id), "name": access.event.name},
    )


@router.delete("/{event_id}/invites/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def uninvite(
    event_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    (await load_event(session, event_id, user.id)).require_owner()
    await session.execute(
        delete(EventInvite).where(EventInvite.event_id == event_id, EventInvite.user_id == user_id)
    )
    await session.commit()
    # Their open sockets lose the room on every worker.
    await rooms.kick(f"event:{event_id}", user_id)


# --- Queue & votes -----------------------------------------------------------


@router.get("/{event_id}/queue")
async def queue(event_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> QueueOut:
    access = await load_event(session, event_id, user.id)
    return await get_queue(session, access.event, user.id)


@router.post("/{event_id}/tracks", status_code=status.HTTP_201_CREATED)
async def suggest_track(
    event_id: uuid.UUID,
    body: SuggestIn,
    user: CurrentUser,
    session: SessionDep,
    provider: ProviderDep,
) -> QueueOut:
    access = await load_event(session, event_id, user.id)
    access.require_vote(body.as_tuple())
    info = await provider.get_track(body.external_id)

    # The partial unique index rejects a track already waiting in the queue,
    # even if two people suggest it at the same instant.
    inserted = await session.scalar(
        insert(EventTrack)
        .values(
            id=uuid.uuid4(),
            event_id=event_id,
            suggested_by=user.id,
            suggested_at=datetime.now(UTC),
            **info.model_dump(),
        )
        .on_conflict_do_nothing(
            index_elements=["event_id", "provider", "external_id"],
            index_where=EventTrack.played_at.is_(None),
        )
        .returning(EventTrack.id)
    )
    await session.commit()
    if inserted is None:
        raise api_error(409, "already_queued", "This track is already in the queue")
    await publish_queue(session, access.event)
    return await get_queue(session, access.event, user.id)


async def _queued_track(
    session: AsyncSession, access: EventAccess, track_id: uuid.UUID
) -> EventTrack:
    track = await session.get(EventTrack, track_id)
    if track is None or track.event_id != access.event.id:
        raise not_found("Track")
    if track.played_at is not None or access.event.now_playing_id == track.id:
        raise api_error(409, "track_locked", "This track is playing or was played: no more votes")
    return track


@router.post("/{event_id}/tracks/{track_id}/vote")
async def vote(
    event_id: uuid.UUID, track_id: uuid.UUID, body: Position, user: CurrentUser, session: SessionDep
) -> QueueOut:
    """Idempotent: voting twice for the same track still counts once (enforced by
    UNIQUE(event_id, track_id, user_id), so it also holds for simultaneous requests)."""
    access = await load_event(session, event_id, user.id)
    access.require_vote(body.as_tuple())
    await _queued_track(session, access, track_id)
    result = await session.execute(
        insert(Vote)
        .values(id=uuid.uuid4(), event_id=event_id, track_id=track_id, user_id=user.id)
        .on_conflict_do_nothing(index_elements=["event_id", "track_id", "user_id"])
    )
    await session.commit()
    if result.rowcount:  # only a real change is broadcast
        await publish_queue(session, access.event)
    return await get_queue(session, access.event, user.id)


@router.delete("/{event_id}/tracks/{track_id}/vote")
async def unvote(
    event_id: uuid.UUID, track_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> QueueOut:
    access = await load_event(session, event_id, user.id)
    # No license check: withdrawing a vote is always allowed to someone who can see the event.
    await _queued_track(session, access, track_id)
    result = await session.execute(
        delete(Vote).where(Vote.track_id == track_id, Vote.user_id == user.id)
    )
    await session.commit()
    if result.rowcount:
        await publish_queue(session, access.event)
    return await get_queue(session, access.event, user.id)


@router.delete("/{event_id}/tracks/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_track(
    event_id: uuid.UUID, track_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """The owner can remove any queued track; a user can remove their own suggestion."""
    access = await load_event(session, event_id, user.id)
    track = await session.get(EventTrack, track_id)
    if track is None or track.event_id != event_id or track.played_at is not None:
        raise not_found("Track")
    if not access.is_owner and track.suggested_by != user.id:
        raise api_error(403, "owner_only", "Only the owner or the person who suggested it")
    if access.event.now_playing_id == track.id:
        access.event.now_playing_id = None
    await session.delete(track)
    await session.commit()
    await publish_queue(session, access.event)


@router.post("/{event_id}/next")
async def play_next(event_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> QueueOut:
    """Owner's player: the current track is marked played and the top-voted one starts.

    The event row is locked (SELECT ... FOR UPDATE) so two "next" at once can't both
    pick the same track or skip one."""
    access = await load_event(session, event_id, user.id, for_update=True)
    access.require_owner()
    event = access.event
    if event.now_playing_id is not None:
        current = await session.get(EventTrack, event.now_playing_id)
        if current is not None:
            current.played_at = datetime.now(UTC)
        event.now_playing_id = None
    top = (await session.execute(ranking_query(event, None).limit(1))).first()
    event.now_playing_id = top[0].id if top else None
    await session.commit()
    await publish_queue(session, event)
    return await get_queue(session, event, user.id)
