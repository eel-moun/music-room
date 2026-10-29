from typing import Literal, Protocol

from pydantic import BaseModel, Field

ProviderName = Literal["audius"]


class TrackInfo(BaseModel):
    """A track in our own format, independent of any music provider."""

    provider: ProviderName
    external_id: str
    title: str
    artist: str
    duration: int = Field(ge=0, description="Duration in seconds")
    artwork_url: str | None = None


class MusicProvider(Protocol):
    """What any music provider must be able to do."""

    name: ProviderName

    async def search(self, query: str, limit: int = 20) -> list[TrackInfo]: ...

    async def get_track(self, external_id: str) -> TrackInfo: ...

    async def get_stream_url(self, external_id: str) -> str: ...


class MusicProviderError(Exception):
    """The provider is unreachable or answered with an error (maps to 502)."""


class TrackNotFoundError(MusicProviderError):
    """The provider doesn't know this track id (maps to 404)."""
