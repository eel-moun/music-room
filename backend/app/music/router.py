from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel

from app.core.config import get_settings
from app.music.audius import AudiusProvider, audius_client
from app.music.provider import MusicProvider, TrackInfo

router = APIRouter(prefix="/music", tags=["music"])


def get_music_provider() -> MusicProvider:
    """Pick the provider from settings. Tests override this dependency."""
    name = get_settings().music_provider
    if name == "audius":
        return AudiusProvider(audius_client)
    raise RuntimeError(f"Unknown MUSIC_PROVIDER: {name!r}")


ProviderDep = Annotated[MusicProvider, Depends(get_music_provider)]

# Audius ids are short alphanumeric hashes. Validating them stops values like
# "../users" from being forwarded into the provider's URL path.
TrackId = Annotated[str, Path(pattern=r"^[A-Za-z0-9]{1,32}$")]


class StreamUrl(BaseModel):
    url: str


@router.get("/search")
async def search(
    provider: ProviderDep,
    q: Annotated[str, Query(min_length=1, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[TrackInfo]:
    return await provider.search(q, limit)


@router.get("/tracks/{track_id}/stream")
async def stream_url(provider: ProviderDep, track_id: TrackId) -> StreamUrl:
    # JSON instead of a 302: the mobile player needs the URL itself.
    # It is signed and short-lived, so clients fetch it right before playing.
    return StreamUrl(url=await provider.get_stream_url(track_id))
