import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, UUIDPk


class Device(UUIDPk, CreatedAt, Base):
    """One app install. Registered on first launch; its id lives in secure storage."""

    __tablename__ = "devices"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    platform: Mapped[str] = mapped_column(String(20))
    last_seen_at: Mapped[datetime | None]


class Delegation(UUIDPk, CreatedAt, Base):
    """A license letting a friend control one specific device."""

    __tablename__ = "delegations"
    __table_args__ = (
        Index(
            "uq_delegations_active",
            "device_id",
            "grantee_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    grantee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    permissions: Mapped[list[str]] = mapped_column(ARRAY(String(20)))  # "playback", "volume"
    expires_at: Mapped[datetime | None]  # None: until revoked
    revoked_at: Mapped[datetime | None]
