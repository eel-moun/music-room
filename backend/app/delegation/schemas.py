import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.music.provider import TrackInfo
from app.music.schemas import TrackRefIn
from app.users.schemas import UserSummary

Permission = Literal["playback", "volume"]
Command = Literal["play", "pause", "next", "previous", "play_track", "play_playlist", "set_volume"]

# Which permission each command needs.
COMMAND_PERMISSION: dict[str, str] = {
    "play": "playback",
    "pause": "playback",
    "next": "playback",
    "previous": "playback",
    "play_track": "playback",
    "play_playlist": "playback",
    "set_volume": "volume",
}


class DeviceIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    platform: str = Field(min_length=1, max_length=20)


class DeviceRename(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class DeviceOut(BaseModel):
    id: uuid.UUID
    name: str
    platform: str
    created_at: datetime
    last_seen_at: datetime | None


class ControllableDeviceOut(DeviceOut):
    owner: UserSummary
    permissions: list[Permission]
    expires_at: datetime | None


class DelegationIn(BaseModel):
    grantee_id: uuid.UUID
    permissions: list[Permission] = Field(min_length=1)
    expires_at: AwareDatetime | None = None


class DelegationOut(BaseModel):
    id: uuid.UUID
    device_id: uuid.UUID
    grantee: UserSummary
    permissions: list[Permission]
    expires_at: datetime | None
    created_at: datetime


class CommandIn(BaseModel):
    command: Command
    track: TrackRefIn | None = None
    playlist_id: uuid.UUID | None = None
    volume: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def _check_args(self) -> "CommandIn":
        needed = {"play_track": "track", "play_playlist": "playlist_id", "set_volume": "volume"}
        arg = needed.get(self.command)
        if arg and getattr(self, arg) is None:
            raise ValueError(f"'{self.command}' needs '{arg}'")
        return self


class DeviceState(BaseModel):
    """Reported by the device itself after each change; relayed to its controllers."""

    is_playing: bool
    track: TrackInfo | None = None
    playlist_id: uuid.UUID | None = None
    position_s: int = Field(default=0, ge=0)
    volume: int = Field(ge=0, le=100)
