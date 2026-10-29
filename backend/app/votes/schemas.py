import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.core.types import Visibility
from app.music.schemas import TrackOut, TrackRefIn
from app.users.schemas import UserSummary
from app.votes.models import EventLicense

Latitude = Field(default=None, ge=-90, le=90)
Longitude = Field(default=None, ge=-180, le=180)


class EventSettings(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    visibility: Visibility = Visibility.public
    license: EventLicense = EventLicense.everyone
    latitude: float | None = Latitude
    longitude: float | None = Longitude
    radius_m: int | None = Field(default=None, ge=10, le=50_000)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _check_license(self) -> "EventSettings":
        if self.license is EventLicense.location_time and None in (
            self.latitude,
            self.longitude,
            self.radius_m,
            self.starts_at,
            self.ends_at,
        ):
            raise ValueError(
                "location_time license needs latitude, longitude, radius_m, starts_at, ends_at"
            )
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class EventUpdate(BaseModel):
    """Fields to change; the merged result is validated like a new event."""

    name: str | None = None
    description: str | None = None
    visibility: Visibility | None = None
    license: EventLicense | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_m: int | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None


class EventOut(EventSettings):
    id: uuid.UUID
    owner: UserSummary
    created_at: datetime
    is_owner: bool
    is_invited: bool


class Position(BaseModel):
    """The caller's GPS position, needed for location_time events."""

    latitude: float | None = Latitude
    longitude: float | None = Longitude

    def as_tuple(self) -> tuple[float, float] | None:
        if self.latitude is None or self.longitude is None:
            return None
        return (self.latitude, self.longitude)


class SuggestIn(TrackRefIn, Position):
    pass


class QueueTrackOut(TrackOut):
    id: uuid.UUID
    votes: int
    voted_by_me: bool | None = Field(
        description="null in realtime pushes (they're shared by every viewer)"
    )
    suggested_by: uuid.UUID | None
    suggested_at: datetime


class QueueOut(BaseModel):
    event_id: uuid.UUID
    now_playing: QueueTrackOut | None
    queue: list[QueueTrackOut] = Field(description="Ranked: votes desc, then oldest suggestion")


class InviteIn(BaseModel):
    user_id: uuid.UUID
