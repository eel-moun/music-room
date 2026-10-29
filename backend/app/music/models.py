from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.music.provider import TrackInfo


class TrackRefColumns:
    """A reference to a provider track. We store metadata, never audio."""

    provider: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(300))
    artist: Mapped[str] = mapped_column(String(300))
    duration: Mapped[int]
    artwork_url: Mapped[str | None] = mapped_column(String(1000))

    def set_track(self, track: TrackInfo) -> None:
        for field, value in track.model_dump().items():
            setattr(self, field, value)
