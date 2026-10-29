import asyncio

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.playlists.models import PlaylistTrack


@pytest.fixture
async def owner(make_user):
    return await make_user("owner")


@pytest.fixture
def create_playlist(client, owner):
    async def create(**settings):
        body = {"name": "Road trip"} | settings
        response = await client.post("/playlists", json=body, headers=owner.headers)
        assert response.status_code == 201, response.text
        return response.json()

    return create


async def add(client, playlist, user, external_id, version=None):
    return await client.post(
        f"/playlists/{playlist['id']}/tracks",
        json={"external_id": external_id, "version": version or playlist["version"]},
        headers=user.headers,
    )


async def move(client, playlist, user, track_id, after_id, version):
    return await client.post(
        f"/playlists/{playlist['id']}/tracks/{track_id}/move",
        json={"after_track_id": after_id, "version": version},
        headers=user.headers,
    )


async def filled(client, playlist, user, names=("aaa", "bbb", "ccc", "ddd")):
    for name in names:
        playlist = (await add(client, playlist, user, name)).json()
    return playlist


async def positions() -> dict[str, float]:
    async with SessionLocal() as session:
        return {t.external_id: t.position for t in await session.scalars(select(PlaylistTrack))}


def order(playlist):
    return [t["external_id"] for t in playlist["tracks"]]


def track_id(playlist, name):
    return next(t["id"] for t in playlist["tracks"] if t["external_id"] == name)


# --- Editing ------------------------------------------------------------------------


async def test_add_move_remove(client, create_playlist, owner):
    playlist = await filled(client, await create_playlist(), owner)
    assert order(playlist) == ["aaa", "bbb", "ccc", "ddd"]
    assert playlist["version"] == 5

    playlist = (
        await move(client, playlist, owner, track_id(playlist, "ddd"), None, playlist["version"])
    ).json()
    assert order(playlist) == ["ddd", "aaa", "bbb", "ccc"]

    playlist = (
        await move(
            client,
            playlist,
            owner,
            track_id(playlist, "ddd"),
            track_id(playlist, "bbb"),
            playlist["version"],
        )
    ).json()
    assert order(playlist) == ["aaa", "bbb", "ddd", "ccc"]

    response = await client.delete(
        f"/playlists/{playlist['id']}/tracks/{track_id(playlist, 'aaa')}",
        params={"version": playlist["version"]},
        headers=owner.headers,
    )
    assert order(response.json()) == ["bbb", "ddd", "ccc"]


async def test_moving_only_rewrites_the_moved_row(client, create_playlist, owner):
    playlist = await filled(client, await create_playlist(), owner)
    before = {t["external_id"]: t for t in playlist["tracks"]}
    positions_before = await positions()
    await move(
        client, playlist, owner, before["ddd"]["id"], before["aaa"]["id"], playlist["version"]
    )
    positions_after = await positions()
    changed = {k for k in positions_before if positions_before[k] != positions_after[k]}
    assert changed == {"ddd"}
    assert positions_after["aaa"] < positions_after["ddd"] < positions_after["bbb"]


async def test_repeated_midpoint_moves_rebalance(client, create_playlist, owner):
    """Floats run out of precision after ~50 halvings: the gap check renumbers."""
    playlist = await filled(client, await create_playlist(), owner, ("aaa", "bbb", "ccc"))
    for i in range(70):
        # Alternate ccc and bbb just after aaa: the gap after aaa keeps halving.
        name = "ccc" if i % 2 == 0 else "bbb"
        response = await move(
            client,
            playlist,
            owner,
            track_id(playlist, name),
            track_id(playlist, "aaa"),
            playlist["version"],
        )
        assert response.status_code == 200, response.text
        playlist = response.json()
        assert order(playlist)[:2] == ["aaa", name]


async def test_cannot_place_after_itself(client, create_playlist, owner):
    playlist = await filled(client, await create_playlist(), owner, ("aaa",))
    tid = track_id(playlist, "aaa")
    assert (await move(client, playlist, owner, tid, tid, playlist["version"])).status_code == 400


async def test_duplicate_track_rejected(client, create_playlist, owner):
    playlist = await filled(client, await create_playlist(), owner, ("aaa",))
    assert (await add(client, playlist, owner, "aaa")).status_code == 409


# --- Optimistic locking ------------------------------------------------------------------


async def test_stale_version_is_a_conflict(client, create_playlist, owner):
    playlist = await filled(client, await create_playlist(), owner, ("aaa", "bbb"))
    stale = playlist["version"] - 1
    response = await move(client, playlist, owner, track_id(playlist, "bbb"), None, stale)
    assert response.status_code == 409
    assert response.json()["detail"]["current_version"] == playlist["version"]


async def test_two_users_move_different_tracks_at_once(client, create_playlist, owner, make_user):
    playlist = await filled(client, await create_playlist(), owner)
    other = await make_user()
    v = playlist["version"]

    first, second = await asyncio.gather(
        move(client, playlist, owner, track_id(playlist, "ddd"), None, v),
        move(client, playlist, other, track_id(playlist, "aaa"), track_id(playlist, "ccc"), v),
    )

    # Exactly one wins; the other is told to refetch instead of silently overwriting.
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    final = (await client.get(f"/playlists/{playlist['id']}", headers=owner.headers)).json()
    assert final["version"] == v + 1
    assert sorted(order(final)) == ["aaa", "bbb", "ccc", "ddd"]  # nothing lost or duplicated


async def test_two_users_move_the_same_track_at_once(client, create_playlist, owner, make_user):
    playlist = await filled(client, await create_playlist(), owner)
    other = await make_user()
    v, ddd = playlist["version"], track_id(playlist, "ddd")

    responses = await asyncio.gather(
        move(client, playlist, owner, ddd, None, v),
        move(client, playlist, other, ddd, track_id(playlist, "aaa"), v),
    )

    assert sorted(r.status_code for r in responses) == [200, 409]
    winner = next(r for r in responses if r.status_code == 200).json()
    final = (await client.get(f"/playlists/{playlist['id']}", headers=owner.headers)).json()
    assert order(final) == order(winner)


async def test_many_parallel_adds_with_same_version(client, create_playlist, make_user):
    playlist = await create_playlist()
    editors = await asyncio.gather(*(make_user() for _ in range(10)))

    responses = await asyncio.gather(
        *(add(client, playlist, e, f"t{i}") for i, e in enumerate(editors))
    )

    assert sorted(r.status_code for r in responses) == [201] + [409] * 9
    final = (await client.get(f"/playlists/{playlist['id']}", headers=editors[0].headers)).json()
    assert len(final["tracks"]) == 1
    assert final["version"] == 2


# --- Visibility & licenses ------------------------------------------------------------------


async def test_private_playlist_needs_an_invite(client, create_playlist, owner, make_user):
    playlist = await create_playlist(visibility="private")
    friend = await make_user()
    path = f"/playlists/{playlist['id']}"
    assert (await client.get(path, headers=friend.headers)).status_code == 404

    await client.post(f"{path}/members", json={"user_id": str(friend.id)}, headers=owner.headers)
    seen = await client.get(path, headers=friend.headers)
    assert seen.status_code == 200
    assert seen.json()["can_edit"] is True
    assert (await add(client, playlist, friend, "aaa")).status_code == 201

    await client.delete(f"{path}/members/{friend.id}", headers=owner.headers)
    assert (await client.get(path, headers=friend.headers)).status_code == 404


async def test_invited_license_public_playlist(client, create_playlist, owner, make_user):
    playlist = await create_playlist(license="invited")
    stranger = await make_user()
    seen = await client.get(f"/playlists/{playlist['id']}", headers=stranger.headers)
    assert seen.json()["can_edit"] is False
    response = await add(client, playlist, stranger, "aaa")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "license_invited_only"


async def test_only_owner_changes_settings(client, create_playlist, owner, make_user):
    playlist = await create_playlist()
    other = await make_user()
    path = f"/playlists/{playlist['id']}"
    assert (await client.patch(path, json={"name": "x"}, headers=other.headers)).status_code == 403
    assert (await client.delete(path, headers=other.headers)).status_code == 403
    assert (await client.delete(path, headers=owner.headers)).status_code == 204


async def test_listing_shows_only_visible_playlists(client, create_playlist, make_user):
    public = await create_playlist(name="public one")
    private = await create_playlist(name="secret", visibility="private")
    stranger = await make_user()
    listed = [p["id"] for p in (await client.get("/playlists", headers=stranger.headers)).json()]
    assert public["id"] in listed
    assert private["id"] not in listed
