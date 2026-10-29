from pydantic import BaseModel, Field

from app.music.provider import ProviderName


class TrackRefIn(BaseModel):
    """What a client sends to add a track. Title, artist, etc. are fetched by the
    server from the provider: a client can't inject fake metadata."""

    provider: ProviderName = "audius"
    external_id: str = Field(pattern=r"^[A-Za-z0-9]{1,32}$")


class TrackOut(BaseModel):
    provider: ProviderName
    external_id: str
    title: str
    artist: str
    duration: int
    artwork_url: str | None
