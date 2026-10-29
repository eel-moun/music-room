"""Test setup: a separate database (<db>_test) and Redis db 15, wiped before each test.

Environment variables are set before any `app` import so the app's engine and
Redis client point at the test stores.
"""

import os

os.environ["APP_ENV"] = "test"
os.environ.pop("PROMETHEUS_MULTIPROC_DIR", None)

from app.core.config import Settings  # noqa: E402

_base = Settings()
os.environ["POSTGRES_DB"] = f"{_base.postgres_db}_test"
os.environ["REDIS_URL"] = _base.redis_url.rsplit("/", 1)[0] + "/15"

import asyncio  # noqa: E402
import uuid  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402

import asyncpg  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

import app.models  # noqa: E402, F401
from app.auth.google import GoogleIdentity, get_google_verifier  # noqa: E402
from app.auth.service import issue_tokens  # noqa: E402
from app.core import email as email_module  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import Base, SessionLocal  # noqa: E402
from app.core.errors import api_error  # noqa: E402
from app.core.redis import redis_client  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.music.provider import TrackInfo, TrackNotFoundError  # noqa: E402
from app.music.router import get_music_provider  # noqa: E402
from app.users.models import User  # noqa: E402

DEVICE_HEADERS = {"X-Platform": "android", "X-Device": "pytest", "X-App-Version": "test"}
PASSWORD = "correct-horse-battery"


async def _create_test_database() -> None:
    s = get_settings()
    admin = await asyncpg.connect(
        user=s.postgres_user,
        password=s.postgres_password,
        host=s.postgres_host,
        port=s.postgres_port,
        database="postgres",
    )
    await admin.execute(f'DROP DATABASE IF EXISTS "{s.postgres_db}" WITH (FORCE)')
    await admin.execute(f'CREATE DATABASE "{s.postgres_db}"')
    await admin.close()
    engine = create_async_engine(s.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _database():
    asyncio.run(_create_test_database())


@pytest.fixture(autouse=True)
async def _clean_state():
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with SessionLocal() as session:
        await session.execute(text(f"TRUNCATE {tables} CASCADE"))
        await session.commit()
    await redis_client.flushdb()


# --- Fakes -----------------------------------------------------------------------


class FakeProvider:
    """Any alphanumeric id is a track, except ids starting with 'missing'."""

    name = "audius"

    async def search(self, query: str, limit: int = 20) -> list[TrackInfo]:
        return [await self.get_track(f"{query}{i}") for i in range(min(limit, 3))]

    async def get_track(self, external_id: str) -> TrackInfo:
        if external_id.startswith("missing"):
            raise TrackNotFoundError(external_id)
        return TrackInfo(
            provider="audius",
            external_id=external_id,
            title=f"Title {external_id}",
            artist="Artist",
            duration=180,
        )

    async def get_stream_url(self, external_id: str) -> str:
        return f"https://stream/{external_id}"


@pytest.fixture(autouse=True)
def _fake_provider():
    app.dependency_overrides[get_music_provider] = FakeProvider
    yield
    app.dependency_overrides.pop(get_music_provider, None)


@pytest.fixture
def outbox(monkeypatch) -> list:
    """Emails the app would have sent."""
    sent: list = []
    monkeypatch.setattr(email_module, "_deliver", sent.append)
    return sent


@pytest.fixture
def google_accounts():
    """Register fake Google tokens: google_accounts["tok"] = GoogleIdentity(...)."""
    accounts: dict[str, GoogleIdentity] = {}

    async def verify(token: str) -> GoogleIdentity:
        if token not in accounts:
            raise api_error(401, "invalid_google_token", "Invalid Google token")
        return accounts[token]

    app.dependency_overrides[get_google_verifier] = lambda: verify
    yield accounts
    app.dependency_overrides.pop(get_google_verifier, None)


# --- Clients and users -------------------------------------------------------------


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers=DEVICE_HEADERS
    ) as c:
        yield c


@dataclass
class AppUser:
    id: uuid.UUID
    email: str
    name: str
    access_token: str
    refresh_token: str
    headers: dict = field(default_factory=dict)


@pytest.fixture
def make_user():
    """Creates a verified user straight in the database and logs them in."""
    hashed: list[str] = []

    async def make(name: str | None = None) -> AppUser:
        name = name or f"user-{uuid.uuid4().hex[:6]}"
        if not hashed:
            hashed.append(await hash_password(PASSWORD))  # argon2 once per test, not per user
        async with SessionLocal() as session:
            user = User(
                email=f"{name.lower()}@example.com",
                password_hash=hashed[0],
                email_verified=True,
                display_name=name,
            )
            session.add(user)
            await session.commit()
            tokens = await issue_tokens(session, user.id)
        return AppUser(
            id=user.id,
            email=user.email,
            name=name,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )

    return make


@pytest.fixture
def befriend(client):
    async def make_friends(a: AppUser, b: AppUser) -> None:
        r = await client.post("/friends/requests", json={"user_id": str(b.id)}, headers=a.headers)
        assert r.status_code == 201, r.text
        r = await client.post(f"/friends/requests/{r.json()['id']}/accept", headers=b.headers)
        assert r.status_code == 200, r.text

    return make_friends
