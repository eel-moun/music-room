import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.types import Visibility
from app.music.schemas import TrackOut, TrackRefIn
from app.playlists.models import PlaylistLicense
from app.users.schemas import UserSummary

ExpectedVersion = Field(ge=1, description="The playlist version the client last saw")


class PlaylistSettings(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    visibility: Visibility = Visibility.public
    license: PlaylistLicense = PlaylistLicense.everyone


class PlaylistUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    visibility: Visibility | None = None
    license: PlaylistLicense | None = None


class PlaylistTrackOut(TrackOut):
    id: uuid.UUID
    added_by: uuid.UUID | None
    added_at: datetime


class PlaylistOut(PlaylistSettings):
    id: uuid.UUID
    owner: UserSummary
    version: int
    created_at: datetime
    updated_at: datetime
    is_owner: bool
    is_invited: bool
    can_edit: bool


class PlaylistDetail(PlaylistOut):
    tracks: list[PlaylistTrackOut]


class AddTrackIn(TrackRefIn):
    version: int = ExpectedVersion


class MoveTrackIn(BaseModel):
    after_track_id: uuid.UUID | None = Field(
        description="Place the track right after this one; null moves it to the top"
    )
    version: int = ExpectedVersion


class MemberIn(BaseModel):
    user_id: uuid.UUID
