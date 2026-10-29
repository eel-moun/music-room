import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import row_exists
from app.core.errors import api_error, forbidden, not_found
from app.playlists.models import Playlist, PlaylistMember, PlaylistTrack
from app.policies.access import can_edit_playlist, can_view

# Below this gap, two float positions are too close to split again: renumber everything.
MIN_GAP = 1e-9


class PlaylistAccess:
    def __init__(self, playlist: Playlist, user_id: uuid.UUID, is_invited: bool) -> None:
        self.playlist = playlist
        self.is_owner = playlist.owner_id == user_id
        self.is_invited = is_invited
        self.edit = can_edit_playlist(
            playlist.visibility, playlist.license, is_owner=self.is_owner, is_invited=is_invited
        )

    def require_owner(self) -> None:
        if not self.is_owner:
            raise forbidden("owner_only", "Only the playlist owner can do this")

    def require_edit(self) -> None:
        if not self.edit.allowed:
            raise forbidden(self.edit.code, self.edit.message)


async def load_playlist(
    session: AsyncSession, playlist_id: uuid.UUID, user_id: uuid.UUID
) -> PlaylistAccess:
    playlist = await session.get(Playlist, playlist_id)
    if playlist is None:
        raise not_found("Playlist")
    invited = await row_exists(session, PlaylistMember, playlist_id=playlist_id, user_id=user_id)
    access = PlaylistAccess(playlist, user_id, invited)
    if not can_view(playlist.visibility, is_owner=access.is_owner, is_invited=invited):
        raise not_found("Playlist")
    return access


async def claim_version(session: AsyncSession, playlist_id: uuid.UUID, expected: int) -> int:
    """Optimistic lock. Bumps the version only if it still equals what the client saw.

    The UPDATE also row-locks the playlist until commit, so concurrent writers queue
    up; when the first commits, Postgres re-checks the WHERE for the next one, which
    now fails: that writer gets a 409 and must refetch.
    """
    new_version = await session.scalar(
        update(Playlist)
        .where(Playlist.id == playlist_id, Playlist.version == expected)
        .values(version=Playlist.version + 1)
        .returning(Playlist.version)
    )
    if new_version is None:
        await session.rollback()
        current = await session.scalar(select(Playlist.version).where(Playlist.id == playlist_id))
        raise api_error(
            409,
            "version_conflict",
            "Someone else changed this playlist. Refresh and try again.",
            current_version=current,
        )
    return new_version


async def ordered_tracks(session: AsyncSession, playlist_id: uuid.UUID) -> list[PlaylistTrack]:
    rows = await session.scalars(
        select(PlaylistTrack)
        .where(PlaylistTrack.playlist_id == playlist_id)
        .order_by(PlaylistTrack.position, PlaylistTrack.id)
    )
    return list(rows)


async def end_position(session: AsyncSession, playlist_id: uuid.UUID) -> float:
    last = await session.scalar(
        select(func.max(PlaylistTrack.position)).where(PlaylistTrack.playlist_id == playlist_id)
    )
    return (last or 0.0) + 1.0


async def position_after(
    session: AsyncSession, playlist_id: uuid.UUID, moving: PlaylistTrack, after_id: uuid.UUID | None
) -> float:
    """Position for `moving` placed right after `after_id` (None: first). Only this
    one row changes, unless the gap is exhausted and the playlist is renumbered."""
    tracks = [t for t in await ordered_tracks(session, playlist_id) if t.id != moving.id]
    if after_id is None:
        index = 0
    else:
        ids = [t.id for t in tracks]
        if after_id not in ids:
            raise not_found("Track to place after")
        index = ids.index(after_id) + 1

    before = tracks[index - 1].position if index > 0 else None
    after = tracks[index].position if index < len(tracks) else None
    if before is not None and after is not None and after - before < MIN_GAP:
        for i, track in enumerate(tracks, start=1):  # rebalance: 1.0, 2.0, 3.0, ...
            track.position = float(i)
        before = float(index) if index > 0 else None
        after = float(index + 1) if index < len(tracks) else None

    if before is None and after is None:
        return 1.0
    if before is None:
        return after - 1.0
    if after is None:
        return before + 1.0
    return (before + after) / 2
