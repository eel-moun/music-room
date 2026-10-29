import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, UUIDPk
from app.core.types import str_enum


class RefreshToken(UUIDPk, CreatedAt, Base):
    """One row per issued refresh token. A login starts a family; each refresh
    rotates to a new token in the same family. Presenting a used token again
    means it was stolen: the whole family is revoked."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]  # set when rotated, logged out or family revoked


class EmailTokenPurpose(StrEnum):
    verify_email = "verify_email"
    reset_password = "reset_password"


class EmailToken(UUIDPk, CreatedAt, Base):
    __tablename__ = "email_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[EmailTokenPurpose] = mapped_column(
        str_enum(EmailTokenPurpose, "email_token_purpose")
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
