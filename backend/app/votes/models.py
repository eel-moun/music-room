import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, UUIDPk, utcnow
from app.core.types import Visibility, str_enum
from app.music.models import TrackRefColumns


class EventLicense(StrEnum):
    everyone = "everyone"  # any user who can see the event votes
    invited = "invited"  # only invited users (and the owner) vote
    location_time = "location_time"  # only users in the area during the time window vote


class Event(UUIDPk, CreatedAt, Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "license <> 'location_time' OR (latitude IS NOT NULL AND longitude IS NOT NULL"
            " AND radius_m IS NOT NULL AND starts_at IS NOT NULL AND ends_at IS NOT NULL)",
            name="location_time_complete",
        ),
        CheckConstraint("ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at", "window"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    visibility: Mapped[Visibility] = mapped_column(
        str_enum(Visibility, "event_visibility"), default=Visibility.public
    )
    license: Mapped[EventLicense] = mapped_column(
        str_enum(EventLicense, "event_license"), default=EventLicense.everyone
    )
    latitude: Mapped[float | None]
    longitude: Mapped[float | None]
    radius_m: Mapped[int | None]
    starts_at: Mapped[datetime | None]
    ends_at: Mapped[datetime | None]
    now_playing_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("event_tracks.id", ondelete="SET NULL", use_alter=True)
    )


class EventInvite(CreatedAt, Base):
    __tablename__ = "event_invites"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class EventTrack(UUIDPk, TrackRefColumns, Base):
    __tablename__ = "event_tracks"
    __table_args__ = (
        # A track can be in the queue once; after it's played it may be suggested again.
        Index(
            "uq_event_tracks_queued",
            "event_id",
            "provider",
            "external_id",
            unique=True,
            postgresql_where=text("played_at IS NULL"),
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    suggested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    suggested_at: Mapped[datetime] = mapped_column(default=utcnow)
    played_at: Mapped[datetime | None]


class Vote(UUIDPk, CreatedAt, Base):
    __tablename__ = "votes"
    # The database, not the app, guarantees one vote per user per track,
    # even when the same user sends two votes at the same time.
    __table_args__ = (UniqueConstraint("event_id", "track_id", "user_id"),)

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("event_tracks.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
