import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, UUIDPk, utcnow
from app.core.types import Visibility, str_enum
from app.music.models import TrackRefColumns


class PlaylistLicense(StrEnum):
    everyone = "everyone"  # anyone who can see the playlist edits it
    invited = "invited"  # only invited users (and the owner) edit


class Playlist(UUIDPk, CreatedAt, Base):
    __tablename__ = "playlists"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    visibility: Mapped[Visibility] = mapped_column(
        str_enum(Visibility, "playlist_visibility"), default=Visibility.public
    )
    license: Mapped[PlaylistLicense] = mapped_column(
        str_enum(PlaylistLicense, "playlist_license"), default=PlaylistLicense.everyone
    )
    # Bumped by every track change. Writers send the version they saw: a mismatch is a 409.
    version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class PlaylistMember(CreatedAt, Base):
    """An invited user."""

    __tablename__ = "playlist_members"

    playlist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class PlaylistTrack(UUIDPk, TrackRefColumns, Base):
    __tablename__ = "playlist_tracks"
    __table_args__ = (
        UniqueConstraint("playlist_id", "provider", "external_id"),
        Index("ix_playlist_tracks_order", "playlist_id", "position"),
    )

    playlist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("playlists.id", ondelete="CASCADE"))
    # Fractional index: moving a track only rewrites this one value (the midpoint
    # of its new neighbours), not the position of every track in between.
    position: Mapped[float]
    added_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    added_at: Mapped[datetime] = mapped_column(default=utcnow)
