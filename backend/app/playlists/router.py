import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import delete, exists, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser
from app.core.db import SessionDep
from app.core.errors import api_error, not_found
from app.core.types import Visibility
from app.music.router import ProviderDep
from app.playlists.models import Playlist, PlaylistMember, PlaylistTrack
from app.playlists.schemas import (
    AddTrackIn,
    MemberIn,
    MoveTrackIn,
    PlaylistDetail,
    PlaylistOut,
    PlaylistSettings,
    PlaylistTrackOut,
    PlaylistUpdate,
)
from app.playlists.service import (
    PlaylistAccess,
    claim_version,
    end_position,
    load_playlist,
    ordered_tracks,
    position_after,
)
from app.realtime.rooms import rooms
from app.users.models import User
from app.users.schemas import UserSummary

router = APIRouter(prefix="/playlists", tags=["playlist editor"])


async def _playlist_out(session: AsyncSession, access: PlaylistAccess) -> PlaylistOut:
    p = access.playlist
    owner = await session.get(User, p.owner_id)
    return PlaylistOut(
        id=p.id,
        name=p.name,
        description=p.description,
        visibility=p.visibility,
        license=p.license,
        owner=UserSummary.model_validate(owner),
        version=p.version,
        created_at=p.created_at,
        updated_at=p.updated_at,
        is_owner=access.is_owner,
        is_invited=access.is_invited,
        can_edit=access.edit.allowed,
    )


async def _detail(session: AsyncSession, access: PlaylistAccess) -> PlaylistDetail:
    await session.refresh(access.playlist)
    tracks = await ordered_tracks(session, access.playlist.id)
    return PlaylistDetail(
        **(await _playlist_out(session, access)).model_dump(),
        tracks=[
            PlaylistTrackOut(
                id=t.id,
                provider=t.provider,
                external_id=t.external_id,
                title=t.title,
                artist=t.artist,
                duration=t.duration,
                artwork_url=t.artwork_url,
                added_by=t.added_by,
                added_at=t.added_at,
            )
            for t in tracks
        ],
    )


async def _publish(session: AsyncSession, access: PlaylistAccess) -> PlaylistDetail:
    """Push the new state (with its version) to everyone editing this playlist."""
    detail = await _detail(session, access)
    payload = detail.model_dump(mode="json", exclude={"is_owner", "is_invited", "can_edit"})
    await rooms.publish(f"playlist:{access.playlist.id}", "playlist.updated", payload)
    return detail


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_playlist(
    body: PlaylistSettings, user: CurrentUser, session: SessionDep
) -> PlaylistDetail:
    playlist = Playlist(owner_id=user.id, **body.model_dump())
    session.add(playlist)
    await session.commit()
    return await _detail(session, PlaylistAccess(playlist, user.id, False))


@router.get("")
async def list_playlists(
    user: CurrentUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    mine: bool = False,
) -> list[PlaylistOut]:
    invited = exists().where(
        PlaylistMember.playlist_id == Playlist.id, PlaylistMember.user_id == user.id
    )
    query = select(Playlist).where(
        or_(Playlist.visibility == Visibility.public, Playlist.owner_id == user.id, invited)
    )
    if mine:
        query = query.where(or_(Playlist.owner_id == user.id, invited))
    if q:
        pattern = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Playlist.name.ilike(f"%{pattern}%", escape="\\"))
    playlists = list(await session.scalars(query.order_by(Playlist.updated_at.desc()).limit(50)))
    member_of = set(
        await session.scalars(
            select(PlaylistMember.playlist_id).where(
                PlaylistMember.user_id == user.id,
                PlaylistMember.playlist_id.in_([p.id for p in playlists]),
            )
        )
    )
    return [
        await _playlist_out(session, PlaylistAccess(p, user.id, p.id in member_of))
        for p in playlists
    ]


@router.get("/{playlist_id}")
async def get_playlist(
    playlist_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> PlaylistDetail:
    return await _detail(session, await load_playlist(session, playlist_id, user.id))


@router.patch("/{playlist_id}")
async def update_playlist(
    playlist_id: uuid.UUID, body: PlaylistUpdate, user: CurrentUser, session: SessionDep
) -> PlaylistDetail:
    access = await load_playlist(session, playlist_id, user.id)
    access.require_owner()
    for field, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(access.playlist, field, value)
    await session.commit()
    access = await load_playlist(session, playlist_id, user.id)  # recompute can_edit
    return await _publish(session, access)


@router.delete("/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playlist(playlist_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    access = await load_playlist(session, playlist_id, user.id)
    access.require_owner()
    await session.delete(access.playlist)
    await session.commit()
    await rooms.publish(f"playlist:{playlist_id}", "playlist.deleted", {"id": str(playlist_id)})


# --- Members (invited users) ---------------------------------------------------


@router.get("/{playlist_id}/members")
async def list_members(
    playlist_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[UserSummary]:
    await load_playlist(session, playlist_id, user.id)
    users = await session.scalars(
        select(User)
        .join(PlaylistMember, PlaylistMember.user_id == User.id)
        .where(PlaylistMember.playlist_id == playlist_id)
    )
    return [UserSummary.model_validate(u) for u in users]


@router.post("/{playlist_id}/members", status_code=status.HTTP_204_NO_CONTENT)
async def add_member(
    playlist_id: uuid.UUID, body: MemberIn, user: CurrentUser, session: SessionDep
) -> None:
    access = await load_playlist(session, playlist_id, user.id)
    access.require_owner()
    if await session.get(User, body.user_id) is None:
        raise not_found("User")
    await session.execute(
        insert(PlaylistMember)
        .values(playlist_id=playlist_id, user_id=body.user_id)
        .on_conflict_do_nothing()
    )
    await session.commit()
    await rooms.publish(
        f"user:{body.user_id}",
        "playlist.invited",
        {"playlist_id": str(playlist_id), "name": access.playlist.name},
    )


@router.delete("/{playlist_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    playlist_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    (await load_playlist(session, playlist_id, user.id)).require_owner()
    await session.execute(
        delete(PlaylistMember).where(
            PlaylistMember.playlist_id == playlist_id, PlaylistMember.user_id == user_id
        )
    )
    await session.commit()
    await rooms.kick(f"playlist:{playlist_id}", user_id)


# --- Tracks: every change carries the expected version -------------------------


@router.post("/{playlist_id}/tracks", status_code=status.HTTP_201_CREATED)
async def add_track(
    playlist_id: uuid.UUID,
    body: AddTrackIn,
    user: CurrentUser,
    session: SessionDep,
    provider: ProviderDep,
) -> PlaylistDetail:
    access = await load_playlist(session, playlist_id, user.id)
    access.require_edit()
    info = await provider.get_track(body.external_id)  # before locking: network call
    await claim_version(session, playlist_id, body.version)
    track = PlaylistTrack(
        playlist_id=playlist_id,
        position=await end_position(session, playlist_id),
        added_by=user.id,
    )
    track.set_track(info)
    session.add(track)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise api_error(
            409, "already_in_playlist", "This track is already in the playlist"
        ) from None
    return await _publish(session, access)


@router.post("/{playlist_id}/tracks/{track_id}/move")
async def move_track(
    playlist_id: uuid.UUID,
    track_id: uuid.UUID,
    body: MoveTrackIn,
    user: CurrentUser,
    session: SessionDep,
) -> PlaylistDetail:
    access = await load_playlist(session, playlist_id, user.id)
    access.require_edit()
    await claim_version(session, playlist_id, body.version)
    track = await session.get(PlaylistTrack, track_id)
    if track is None or track.playlist_id != playlist_id:
        await session.rollback()
        raise not_found("Track")
    if body.after_track_id == track_id:
        await session.rollback()
        raise api_error(400, "invalid_move", "A track can't be placed after itself")
    track.position = await position_after(session, playlist_id, track, body.after_track_id)
    await session.commit()
    return await _publish(session, access)


@router.delete("/{playlist_id}/tracks/{track_id}")
async def remove_track(
    playlist_id: uuid.UUID,
    track_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    version: Annotated[int, Query(ge=1)],
) -> PlaylistDetail:
    access = await load_playlist(session, playlist_id, user.id)
    access.require_edit()
    await claim_version(session, playlist_id, version)
    track = await session.get(PlaylistTrack, track_id)
    if track is None or track.playlist_id != playlist_id:
        await session.rollback()
        raise not_found("Track")
    await session.delete(track)
    await session.commit()
    return await _publish(session, access)
