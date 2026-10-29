"""Password hashing, JWT access tokens and opaque random tokens."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi.concurrency import run_in_threadpool

from app.core.config import get_settings

_hasher = PasswordHasher()  # argon2id with the library's recommended parameters
JWT_ALGORITHM = "HS256"

# Verifying against this when the user doesn't exist keeps login timing constant,
# so response time doesn't reveal which emails are registered.
_DUMMY_HASH = _hasher.hash("timing-equalizer")


async def hash_password(password: str) -> str:
    # argon2 is CPU-bound on purpose (~50 ms): run it off the event loop.
    return await run_in_threadpool(_hasher.hash, password)


async def verify_password(password: str, password_hash: str | None) -> bool:
    def check() -> bool:
        try:
            return _hasher.verify(password_hash or _DUMMY_HASH, password) and bool(password_hash)
        except (VerificationError, InvalidHashError):
            return False

    return await run_in_threadpool(check)


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=settings.access_token_ttl_seconds),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID | None:
    """Returns the user id, or None if the token is invalid or expired."""
    try:
        claims = jwt.decode(token, get_settings().jwt_secret, algorithms=[JWT_ALGORITHM])
        if claims.get("type") != "access":
            return None
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def new_opaque_token() -> str:
    """Random token for refresh / email links. Only its hash is stored."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    # SHA-256 is enough here: the token is 256 random bits, not a guessable password.
    return hashlib.sha256(token.encode()).hexdigest()
