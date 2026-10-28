import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.music.provider import MusicProviderError, TrackInfo, TrackNotFoundError
from app.music.router import get_music_provider

TRACK = TrackInfo(provider="audius", external_id="bVrd2zW", title="T", artist="A", duration=60)


class FakeProvider:
    name = "audius"

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple] = []

    async def search(self, query: str, limit: int = 20) -> list[TrackInfo]:
        self.calls.append(("search", query, limit))
        if self.error:
            raise self.error
        return [TRACK]

    async def get_stream_url(self, external_id: str) -> str:
        self.calls.append(("stream", external_id))
        if self.error:
            raise self.error
        return "https://node/stream?signature=abc"


@pytest.fixture
def client_with():
    def make(provider: FakeProvider) -> TestClient:
        app.dependency_overrides[get_music_provider] = lambda: provider
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


def test_search_returns_tracks(client_with):
    provider = FakeProvider()
    response = client_with(provider).get("/music/search", params={"q": "daft", "limit": 5})

    assert response.status_code == 200
    assert response.json()[0]["external_id"] == "bVrd2zW"
    assert provider.calls == [("search", "daft", 5)]


@pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "x", "limit": 0}, {"q": "x", "limit": 51}])
def test_search_rejects_bad_params(client_with, params):
    provider = FakeProvider()
    response = client_with(provider).get("/music/search", params=params)

    assert response.status_code == 422
    assert provider.calls == []


def test_stream_returns_url(client_with):
    response = client_with(FakeProvider()).get("/music/tracks/bVrd2zW/stream")

    assert response.status_code == 200
    assert response.json() == {"url": "https://node/stream?signature=abc"}


def test_stream_rejects_malformed_id(client_with):
    provider = FakeProvider()
    response = client_with(provider).get("/music/tracks/bad-id!/stream")

    assert response.status_code == 422
    assert provider.calls == []


def test_unknown_track_is_404(client_with):
    response = client_with(FakeProvider(TrackNotFoundError())).get("/music/tracks/zzz/stream")

    assert response.status_code == 404


def test_provider_down_is_502(client_with):
    response = client_with(FakeProvider(MusicProviderError())).get(
        "/music/search", params={"q": "daft"}
    )

    assert response.status_code == 502
