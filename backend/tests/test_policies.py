"""Pure unit tests: no database, no HTTP. Every authorization rule in one place."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from app.core.types import Visibility
from app.playlists.models import PlaylistLicense
from app.policies.access import can_control_device, can_edit_playlist, can_view, can_vote
from app.policies.geo import distance_m
from app.policies.profile import Relation, visible_profile_blocks
from app.votes.models import EventLicense

NOW = datetime(2026, 10, 29, 17, 0, tzinfo=UTC)
PARIS = (48.8566, 2.3522)


@dataclass
class FakeEvent:
    visibility: Visibility = Visibility.public
    license: EventLicense = EventLicense.everyone
    latitude: float | None = None
    longitude: float | None = None
    radius_m: int | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


def located(**kw) -> FakeEvent:
    """Party in Paris, 16:00 to 18:00, 200 m radius."""
    return FakeEvent(
        license=EventLicense.location_time,
        latitude=PARIS[0],
        longitude=PARIS[1],
        radius_m=200,
        starts_at=NOW - timedelta(hours=1),
        ends_at=NOW + timedelta(hours=1),
        **kw,
    )


def vote(event, *, owner=False, invited=False, now=NOW, position=None):
    return can_vote(event, is_owner=owner, is_invited=invited, now=now, position=position)


# --- Visibility -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("visibility", "owner", "invited", "expected"),
    [
        (Visibility.public, False, False, True),
        (Visibility.private, False, False, False),
        (Visibility.private, False, True, True),
        (Visibility.private, True, False, True),
    ],
)
def test_can_view(visibility, owner, invited, expected):
    assert can_view(visibility, is_owner=owner, is_invited=invited) is expected


# --- Track Vote licenses --------------------------------------------------------------


def test_default_event_everyone_votes():
    assert vote(FakeEvent()).allowed


def test_private_event_hides_itself_from_strangers():
    decision = vote(FakeEvent(visibility=Visibility.private))
    assert not decision.allowed
    assert decision.code == "not_found"


def test_invited_license():
    event = FakeEvent(license=EventLicense.invited)
    assert vote(event).code == "license_invited_only"
    assert vote(event, invited=True).allowed
    assert vote(event, owner=True).allowed


def test_location_time_inside_area_and_window():
    a_street_away = (48.8570, 2.3525)  # ~50 m
    assert vote(located(), position=a_street_away).allowed


def test_location_time_outside_area():
    versailles = (48.8049, 2.1204)
    assert vote(located(), position=versailles).code == "license_outside_area"


def test_location_time_needs_a_position():
    assert vote(located()).code == "license_location_required"


@pytest.mark.parametrize("hours", [-2, 2])
def test_location_time_outside_window(hours):
    later = NOW + timedelta(hours=hours)
    assert vote(located(), now=later, position=PARIS).code == "license_outside_time"


def test_location_time_owner_always_votes():
    assert vote(located(), owner=True, now=NOW + timedelta(days=1)).allowed


def test_window_bounds_are_inclusive():
    event = located()
    assert vote(event, now=event.starts_at, position=PARIS).allowed
    assert vote(event, now=event.ends_at, position=PARIS).allowed


# --- Playlist licenses -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("visibility", "license", "owner", "invited", "expected"),
    [
        (Visibility.public, PlaylistLicense.everyone, False, False, True),
        (Visibility.public, PlaylistLicense.invited, False, False, False),
        (Visibility.public, PlaylistLicense.invited, False, True, True),
        (Visibility.private, PlaylistLicense.everyone, False, False, False),
        (Visibility.private, PlaylistLicense.everyone, False, True, True),
        (Visibility.private, PlaylistLicense.invited, True, False, True),
    ],
)
def test_can_edit_playlist(visibility, license, owner, invited, expected):
    decision = can_edit_playlist(visibility, license, is_owner=owner, is_invited=invited)
    assert decision.allowed is expected


# --- Control delegation -------------------------------------------------------------------


@dataclass
class FakeDelegation:
    permissions: list[str]
    expires_at: datetime | None = None
    revoked_at: datetime | None = None


def control(delegation, *, owner=False, friends=True, permission="playback"):
    return can_control_device(
        is_owner=owner, delegation=delegation, are_friends=friends, permission=permission, now=NOW
    )


def test_owner_controls_without_delegation():
    assert control(None, owner=True).allowed


def test_no_delegation_hides_the_device():
    assert control(None).code == "not_found"


def test_valid_delegation():
    assert control(FakeDelegation(["playback"])).allowed


def test_missing_permission():
    assert control(FakeDelegation(["playback"]), permission="volume").code == "permission_missing"


def test_watch_only_needs_no_permission():
    assert control(FakeDelegation(["volume"]), permission=None).allowed


def test_expired_delegation():
    expired = FakeDelegation(["playback"], expires_at=NOW)
    assert control(expired).code == "delegation_expired"


def test_revoked_delegation():
    assert control(FakeDelegation(["playback"], revoked_at=NOW)).code == "not_found"


def test_unfriended_grantee_loses_control():
    assert control(FakeDelegation(["playback"]), friends=False).code == "not_friends"


# --- Profile & geo ------------------------------------------------------------------------------


def test_profile_blocks_by_relation():
    assert visible_profile_blocks(Relation.other) == {"public_info", "music_preferences"}
    assert "friends_info" in visible_profile_blocks(Relation.friend)
    assert "private_info" not in visible_profile_blocks(Relation.friend)
    assert "private_info" in visible_profile_blocks(Relation.self)


def test_distance_paris_to_versailles():
    assert 16_000 < distance_m(*PARIS, 48.8049, 2.1204) < 18_000


def test_distance_zero():
    assert distance_m(*PARIS, *PARIS) == 0
