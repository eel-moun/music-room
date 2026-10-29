from typing import Any

import httpx
import structlog

from app.music.provider import MusicProviderError, ProviderName, TrackInfo, TrackNotFoundError

AUDIUS_API_URL = "https://api.audius.co/v1"
APP_NAME = "musicroom"

log = structlog.get_logger()

# One shared client per worker (connection pooling), closed in the app lifespan.
audius_client = httpx.AsyncClient(base_url=AUDIUS_API_URL, timeout=5.0)


class AudiusProvider:
    name: ProviderName = "audius"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def search(self, query: str, limit: int = 20) -> list[TrackInfo]:
        tracks = await self._get("/tracks/search", {"query": query, "limit": limit})
        # Filtering happens after the limit, so a page can hold fewer than `limit` tracks.
        return [_to_track_info(t) for t in tracks if _is_playable(t)]

    async def get_track(self, external_id: str) -> TrackInfo:
        track = await self._get(f"/tracks/{external_id}", {})
        if not _is_playable(track):
            raise TrackNotFoundError(f"Audius: track {external_id} is not playable")
        return _to_track_info(track)

    async def get_stream_url(self, external_id: str) -> str:
        # no_redirect=true returns the signed URL as JSON instead of a 302.
        # The URL is signed with a timestamp: fetch it on demand, never store it.
        return await self._get(f"/tracks/{external_id}/stream", {"no_redirect": "true"})

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        try:
            response = await self._client.get(path, params={**params, "app_name": APP_NAME})
        except httpx.HTTPError as exc:
            log.warning("audius_unreachable", path=path, error=repr(exc))
            raise MusicProviderError("Audius is unreachable") from exc

        # Audius answers 400 "invalid trackId" for unknown ids.
        if response.status_code in (400, 404):
            raise TrackNotFoundError(f"Audius: {path} not found")
        if response.is_error:
            log.warning("audius_error", path=path, status=response.status_code)
            raise MusicProviderError(f"Audius answered {response.status_code}")

        return response.json()["data"]


def _is_playable(track: dict[str, Any]) -> bool:
    return track.get("is_streamable", False) and not track.get("is_stream_gated", False)


def _to_track_info(track: dict[str, Any]) -> TrackInfo:
    return TrackInfo(
        provider="audius",
        external_id=track["id"],
        title=track["title"],
        artist=track["user"]["name"],
        duration=track["duration"],
        artwork_url=(track.get("artwork") or {}).get("480x480"),
    )
