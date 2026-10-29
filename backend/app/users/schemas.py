import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.users.models import FriendshipStatus

ShortText = Field(default=None, max_length=100)


class PublicInfo(BaseModel):
    """Seen by everyone."""

    bio: str = Field(default="", max_length=500)
    avatar_url: str | None = Field(default=None, max_length=500)


class FriendsInfo(BaseModel):
    """Seen by friends only."""

    first_name: str | None = ShortText
    last_name: str | None = ShortText
    city: str | None = ShortText


class PrivateInfo(BaseModel):
    """Seen by the user only."""

    phone: str | None = Field(default=None, max_length=30)
    birth_date: date | None = None


class MusicPreferences(BaseModel):
    genres: list[str] = Field(default_factory=list, max_length=20)
    favorite_artists: list[str] = Field(default_factory=list, max_length=20)


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str


class ProfileOut(UserSummary):
    """Blocks the viewer may not see are null."""

    relation: str
    public_info: PublicInfo
    music_preferences: MusicPreferences
    friends_info: FriendsInfo | None
    private_info: PrivateInfo | None


class MeOut(ProfileOut):
    email: str
    email_verified: bool
    has_password: bool
    google_linked: bool


class ProfileUpdate(BaseModel):
    """Each block given replaces the stored one entirely."""

    display_name: str | None = Field(default=None, min_length=1, max_length=50)
    public_info: PublicInfo | None = None
    friends_info: FriendsInfo | None = None
    private_info: PrivateInfo | None = None
    music_preferences: MusicPreferences | None = None


class FriendRequestIn(BaseModel):
    user_id: uuid.UUID


class FriendRequestOut(BaseModel):
    id: uuid.UUID
    status: FriendshipStatus
    direction: str = Field(description="'incoming' or 'outgoing'")
    user: UserSummary
    created_at: datetime


class FriendOut(BaseModel):
    user: UserSummary
    since: datetime | None
