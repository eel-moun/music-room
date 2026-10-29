import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, column, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, UUIDPk
from app.core.types import str_enum


class User(UUIDPk, CreatedAt, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True)  # stored lowercased
    password_hash: Mapped[str | None] = mapped_column(String(200))  # None: Google-only account
    email_verified: Mapped[bool] = mapped_column(default=False)
    display_name: Mapped[str] = mapped_column(String(50), index=True)

    # One JSONB block per visibility level; shapes are enforced by Pydantic schemas.
    public_info: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    friends_info: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    private_info: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    music_preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class AuthIdentity(UUIDPk, CreatedAt, Base):
    """A social account (Google) linked to a user."""

    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject"),  # a Google account belongs to one user
        UniqueConstraint("user_id", "provider"),  # a user links at most one Google account
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(255))  # Google's stable "sub" claim
    email: Mapped[str | None] = mapped_column(String(320))


class FriendshipStatus(StrEnum):
    pending = "pending"
    accepted = "accepted"


class Friendship(UUIDPk, CreatedAt, Base):
    __tablename__ = "friendships"
    __table_args__ = (
        CheckConstraint("requester_id <> addressee_id", name="not_self"),
        # One row per pair, whatever the direction: A→B and B→A can't both exist.
        Index(
            "uq_friendships_pair",
            # column() and not a plain string: a string would index a constant.
            func.least(column("requester_id"), column("addressee_id")),
            func.greatest(column("requester_id"), column("addressee_id")),
            unique=True,
        ),
    )

    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    addressee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[FriendshipStatus] = mapped_column(
        str_enum(FriendshipStatus, "friendship_status"), default=FriendshipStatus.pending
    )
    accepted_at: Mapped[datetime | None]
