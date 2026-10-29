"""Imports every model so Alembic autogenerate and relationships see all tables."""

from app.auth.models import EmailToken, RefreshToken
from app.delegation.models import Delegation, Device
from app.playlists.models import Playlist, PlaylistMember, PlaylistTrack
from app.users.models import AuthIdentity, Friendship, User
from app.votes.models import Event, EventInvite, EventTrack, Vote

__all__ = [
    "AuthIdentity",
    "Delegation",
    "Device",
    "EmailToken",
    "Event",
    "EventInvite",
    "EventTrack",
    "Friendship",
    "Playlist",
    "PlaylistMember",
    "PlaylistTrack",
    "RefreshToken",
    "User",
    "Vote",
]
