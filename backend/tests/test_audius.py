import httpx
import pytest

from app.music.audius import AUDIUS_API_URL, AudiusProvider
from app.music.provider import MusicProviderError, TrackNotFoundError

# Trimmed-down copy of a real /tracks/search response (Audius sends ~90 fields per track).
PLAYABLE = {
    "id": "bVrd2zW",
    "title": "One More Time (Remix)",
    "duration": 332,
    "is_streamable": True,
    "is_stream_gated": False,
    "user": {"name": "Sury Have Dubz"},
    "artwork": {"150x150": "https://img/150.jpg", "480x480": "https://img/480.jpg"},
}
NOT_STREAMABLE = {**PLAYABLE, "id": "x1", "is_streamable": False}
GATED = {**PLAYABLE, "id": "x2", "is_stream_gated": True}
NO_ARTWORK = {**PLAYABLE, "id": "x3", "artwork": None}


def provider_returning(handler) -> AudiusProvider:
    """An AudiusProvider whose HTTP calls never leave the process."""
    client = httpx.AsyncClient(base_url=AUDIUS_API_URL, transport=httpx.MockTransport(handler))
    return AudiusProvider(client)


async def test_search_maps_to_track_info_and_filters_unplayable():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [PLAYABLE, NOT_STREAMABLE, GATED, NO_ARTWORK]})

    tracks = await provider_returning(handler).search("daft", limit=5)

    assert [t.external_id for t in tracks] == ["bVrd2zW", "x3"]
    first = tracks[0]
    assert (first.provider, first.title, first.artist, first.duration) == (
        "audius",
        "One More Time (Remix)",
        "Sury Have Dubz",
        332,
    )
    assert first.artwork_url == "https://img/480.jpg"
    assert tracks[1].artwork_url is None
    assert seen["params"] == {"query": "daft", "limit": "5", "app_name": "musicroom"}


async def test_get_stream_url_asks_for_json_instead_of_redirect():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/tracks/bVrd2zW/stream"
        assert request.url.params["no_redirect"] == "true"
        return httpx.Response(200, json={"data": "https://node/stream?signature=abc"})

    url = await provider_returning(handler).get_stream_url("bVrd2zW")

    assert url == "https://node/stream?signature=abc"


async def test_unknown_track_raises_not_found():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": 400, "error": "invalid trackId"})

    with pytest.raises(TrackNotFoundError):
        await provider_returning(handler).get_stream_url("zzzzzzz")


async def test_server_error_raises_provider_error():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(MusicProviderError) as exc_info:
        await provider_returning(handler).search("daft")
    assert not isinstance(exc_info.value, TrackNotFoundError)


async def test_network_failure_raises_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(MusicProviderError):
        await provider_returning(handler).search("daft")
