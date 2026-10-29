import pytest

from app.main import app
from app.music.provider import MusicProviderError, TrackNotFoundError
from app.music.router import get_music_provider
from tests.conftest import DEVICE_HEADERS, FakeProvider


class FailingProvider(FakeProvider):
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def search(self, query, limit=20):
        raise self.error

    async def get_stream_url(self, external_id):
        raise self.error


@pytest.fixture
async def user(make_user):
    return await make_user()


async def test_search_returns_tracks(client, user):
    response = await client.get(
        "/music/search", params={"q": "daft", "limit": 2}, headers=user.headers
    )
    assert response.status_code == 200
    assert [t["external_id"] for t in response.json()] == ["daft0", "daft1"]


@pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "x", "limit": 0}, {"q": "x", "limit": 51}])
async def test_search_rejects_bad_params(client, user, params):
    response = await client.get("/music/search", params=params, headers=user.headers)
    assert response.status_code == 422


async def test_stream_returns_url(client, user):
    response = await client.get("/music/tracks/bVrd2zW/stream", headers=user.headers)
    assert response.json() == {"url": "https://stream/bVrd2zW"}


async def test_stream_rejects_malformed_id(client, user):
    response = await client.get("/music/tracks/bad-id!/stream", headers=user.headers)
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("error", "status"), [(TrackNotFoundError(), 404), (MusicProviderError(), 502)]
)
async def test_provider_errors_map_to_http(client, user, error, status):
    app.dependency_overrides[get_music_provider] = lambda: FailingProvider(error)
    response = await client.get("/music/tracks/zzz/stream", headers=user.headers)
    assert response.status_code == status


async def test_requires_device_headers(client, user):
    """Subject V.6: every app action is logged with platform, device and app version."""
    missing = {k: "" for k in DEVICE_HEADERS} | user.headers
    response = await client.get("/music/search", params={"q": "x"}, headers=missing)
    assert response.status_code == 422


async def test_requires_authentication(client):
    response = await client.get("/music/search", params={"q": "x"})
    assert response.status_code == 401
