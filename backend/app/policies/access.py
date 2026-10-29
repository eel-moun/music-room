from datetime import datetime
from typing import Protocol

from app.core.types import Visibility
from app.playlists.models import PlaylistLicense
from app.policies import ALLOW, Decision, deny
from app.policies.geo import distance_m
from app.votes.models import EventLicense


def can_view(visibility: Visibility, *, is_owner: bool, is_invited: bool) -> bool:
    """Events and playlists: public for everyone, private for the owner and invited users."""
    return visibility is Visibility.public or is_owner or is_invited


class EventRules(Protocol):
    visibility: Visibility
    license: EventLicense
    latitude: float | None
    longitude: float | None
    radius_m: int | None
    starts_at: datetime | None
    ends_at: datetime | None


def can_vote(
    event: EventRules,
    *,
    is_owner: bool,
    is_invited: bool,
    now: datetime,
    position: tuple[float, float] | None,
) -> Decision:
    """Also used for suggesting tracks. `now` is server time; `position` comes from the
    client's GPS and can be spoofed (documented hazard, ADR-006)."""
    if not can_view(event.visibility, is_owner=is_owner, is_invited=is_invited):
        return deny("not_found", "Event not found")
    if is_owner:
        return ALLOW
    match event.license:
        case EventLicense.everyone:
            return ALLOW
        case EventLicense.invited:
            if is_invited:
                return ALLOW
            return deny("license_invited_only", "Only invited users can vote in this event")
        case EventLicense.location_time:
            assert event.starts_at and event.ends_at  # guaranteed by a DB check constraint
            if not event.starts_at <= now <= event.ends_at:
                return deny("license_outside_time", "Voting is closed at this time")
            if position is None:
                return deny("license_location_required", "Share your location to vote here")
            assert event.latitude is not None and event.longitude is not None
            assert event.radius_m is not None
            if distance_m(*position, event.latitude, event.longitude) > event.radius_m:
                return deny("license_outside_area", "You must be at the event to vote")
            return ALLOW


def can_edit_playlist(
    visibility: Visibility, license: PlaylistLicense, *, is_owner: bool, is_invited: bool
) -> Decision:
    if not can_view(visibility, is_owner=is_owner, is_invited=is_invited):
        return deny("not_found", "Playlist not found")
    if is_owner or license is PlaylistLicense.everyone or is_invited:
        return ALLOW
    return deny("license_invited_only", "Only invited users can edit this playlist")


class DelegationRules(Protocol):
    permissions: list[str]
    expires_at: datetime | None
    revoked_at: datetime | None


def can_control_device(
    *,
    is_owner: bool,
    delegation: DelegationRules | None,
    are_friends: bool,
    permission: str | None,
    now: datetime,
) -> Decision:
    """`permission` None means "watch only" (subscribe to the device's state)."""
    if is_owner:
        return ALLOW
    if delegation is None or delegation.revoked_at is not None:
        return deny("not_found", "Device not found")
    if delegation.expires_at is not None and now >= delegation.expires_at:
        return deny("delegation_expired", "Your control of this device has expired")
    if not are_friends:
        # Unfriending ends delegations immediately, without waiting for a revoke.
        return deny("not_friends", "Control is only delegated to friends")
    if permission is not None and permission not in delegation.permissions:
        return deny("permission_missing", f"You don't have the '{permission}' permission")
    return ALLOW
