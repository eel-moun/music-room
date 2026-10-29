import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import EmailToken, EmailTokenPurpose, RefreshToken
from app.auth.schemas import TokenPair
from app.core.config import get_settings
from app.core.security import create_access_token, hash_token, new_opaque_token

log = structlog.get_logger()


class InvalidRefreshToken(Exception):
    pass


async def issue_tokens(
    session: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID | None = None
) -> TokenPair:
    """New access token + refresh token. A login starts a new family; a refresh continues one."""
    settings = get_settings()
    refresh = new_opaque_token()
    session.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id or uuid.uuid4(),
            token_hash=hash_token(refresh),
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.refresh_token_ttl_seconds),
        )
    )
    await session.commit()
    return TokenPair(
        access_token=create_access_token(user_id),
        refresh_token=refresh,
        expires_in=settings.access_token_ttl_seconds,
    )


async def rotate_refresh_token(session: AsyncSession, raw_token: str) -> TokenPair:
    """Trade a refresh token for a new pair. Each refresh token works exactly once.

    The single UPDATE ... WHERE revoked_at IS NULL is atomic: if two requests present
    the same token at once, only one gets a row back.
    """
    now = datetime.now(UTC)
    token_hash = hash_token(raw_token)
    used = await session.scalar(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .values(revoked_at=now)
        .returning(RefreshToken)
    )
    if used is not None:
        return await issue_tokens(session, used.user_id, used.family_id)

    known = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if known is not None and known.revoked_at is not None:
        # A token that was already rotated is being replayed: someone else holds a copy.
        # We can't tell the thief from the owner, so we end every session of that family.
        await revoke_family(session, known.family_id)
        log.warning(
            "refresh_token_reuse_detected", user_id=str(known.user_id), family=str(known.family_id)
        )
    raise InvalidRefreshToken


async def revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await session.commit()


async def revoke_all_for_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await session.commit()


async def logout(session: AsyncSession, raw_token: str) -> None:
    family_id = await session.scalar(
        select(RefreshToken.family_id).where(RefreshToken.token_hash == hash_token(raw_token))
    )
    if family_id is not None:
        await revoke_family(session, family_id)


async def create_email_token(
    session: AsyncSession, user_id: uuid.UUID, purpose: EmailTokenPurpose
) -> str:
    """One live token per user and purpose: asking again cancels the previous email."""
    now = datetime.now(UTC)
    await session.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw = new_opaque_token()
    session.add(
        EmailToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(seconds=get_settings().email_token_ttl_seconds),
        )
    )
    await session.commit()
    return raw


async def consume_email_token(
    session: AsyncSession, raw_token: str, purpose: EmailTokenPurpose
) -> uuid.UUID | None:
    """Single use, atomically. Returns the user id, or None if invalid/expired/used."""
    now = datetime.now(UTC)
    user_id = await session.scalar(
        update(EmailToken)
        .where(
            EmailToken.token_hash == hash_token(raw_token),
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
            EmailToken.expires_at > now,
        )
        .values(used_at=now)
        .returning(EmailToken.user_id)
    )
    await session.commit()
    return user_id
