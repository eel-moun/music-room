import asyncio
from datetime import UTC, datetime, timedelta

import pytest

PARIS = {"latitude": 48.8566, "longitude": 2.3522}


@pytest.fixture
async def host(make_user):
    return await make_user("host")


@pytest.fixture
def create_event(client, host):
    async def create(**settings):
        body = {"name": "Party"} | settings
        response = await client.post("/events", json=body, headers=host.headers)
        assert response.status_code == 201, response.text
        return response.json()

    return create


async def suggest(client, event_id, user, external_id, **position):
    return await client.post(
        f"/events/{event_id}/tracks",
        json={"external_id": external_id} | position,
        headers=user.headers,
    )


async def vote(client, event_id, track_id, user, **position):
    return await client.post(
        f"/events/{event_id}/tracks/{track_id}/vote", json=position, headers=user.headers
    )


def ids(queue):
    return [t["external_id"] for t in queue["queue"]]


# --- Basics ------------------------------------------------------------------------


async def test_suggest_and_vote_ranks_the_queue(client, create_event, host, make_user):
    event = await create_event()
    guest = await make_user()
    for track in ("aaa", "bbb", "ccc"):
        await suggest(client, event["id"], guest, track)
    queue = (await client.get(f"/events/{event['id']}/queue", headers=guest.headers)).json()
    assert ids(queue) == ["aaa", "bbb", "ccc"]  # no votes: oldest suggestion first

    ccc = queue["queue"][2]["id"]
    queue = (await vote(client, event["id"], ccc, guest)).json()
    assert ids(queue) == ["ccc", "aaa", "bbb"]
    assert queue["queue"][0]["votes"] == 1
    assert queue["queue"][0]["voted_by_me"] is True

    queue = (
        await client.delete(f"/events/{event['id']}/tracks/{ccc}/vote", headers=guest.headers)
    ).json()
    assert ids(queue) == ["aaa", "bbb", "ccc"]


async def test_metadata_comes_from_the_provider(client, create_event, host):
    event = await create_event()
    queue = (await suggest(client, event["id"], host, "abc123")).json()
    assert queue["queue"][0]["title"] == "Title abc123"
    missing = await suggest(client, event["id"], host, "missing1")
    assert missing.status_code == 404


async def test_track_already_queued(client, create_event, host):
    event = await create_event()
    await suggest(client, event["id"], host, "aaa")
    response = await suggest(client, event["id"], host, "aaa")
    assert response.status_code == 409


async def test_next_plays_top_track_and_locks_it(client, create_event, host, make_user):
    event = await create_event()
    guest = await make_user()
    await suggest(client, event["id"], host, "aaa")
    queue = (await suggest(client, event["id"], host, "bbb")).json()
    bbb = queue["queue"][1]["id"]
    await vote(client, event["id"], bbb, guest)

    queue = (await client.post(f"/events/{event['id']}/next", headers=host.headers)).json()
    assert queue["now_playing"]["external_id"] == "bbb"
    assert ids(queue) == ["aaa"]
    # The playing track is out of the vote.
    assert (await vote(client, event["id"], bbb, guest)).status_code == 409

    queue = (await client.post(f"/events/{event['id']}/next", headers=host.headers)).json()
    assert queue["now_playing"]["external_id"] == "aaa"
    # A played track can be suggested again.
    assert (await suggest(client, event["id"], guest, "bbb")).status_code == 201


async def test_only_owner_controls_playback(client, create_event, make_user):
    event = await create_event()
    guest = await make_user()
    response = await client.post(f"/events/{event['id']}/next", headers=guest.headers)
    assert response.status_code == 403


# --- Visibility & licenses -----------------------------------------------------------


async def test_private_event_is_invisible_until_invited(client, create_event, host, make_user):
    event = await create_event(visibility="private")
    guest = await make_user()

    assert (await client.get(f"/events/{event['id']}", headers=guest.headers)).status_code == 404
    listed = (await client.get("/events", headers=guest.headers)).json()
    assert event["id"] not in [e["id"] for e in listed]
    assert (await suggest(client, event["id"], guest, "aaa")).status_code == 404

    await client.post(
        f"/events/{event['id']}/invites", json={"user_id": str(guest.id)}, headers=host.headers
    )
    listed = (await client.get("/events", headers=guest.headers)).json()
    assert event["id"] in [e["id"] for e in listed]
    assert (await suggest(client, event["id"], guest, "aaa")).status_code == 201

    await client.delete(f"/events/{event['id']}/invites/{guest.id}", headers=host.headers)
    assert (await client.get(f"/events/{event['id']}", headers=guest.headers)).status_code == 404


async def test_invited_license_public_event(client, create_event, host, make_user):
    event = await create_event(license="invited")
    guest = await make_user()
    # Public: the guest can see the event and the queue...
    assert (
        await client.get(f"/events/{event['id']}/queue", headers=guest.headers)
    ).status_code == 200
    # ...but not vote.
    response = await suggest(client, event["id"], guest, "aaa")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "license_invited_only"


async def test_location_time_license(client, create_event, host, make_user):
    now = datetime.now(UTC)
    event = await create_event(
        license="location_time",
        radius_m=300,
        starts_at=(now - timedelta(hours=1)).isoformat(),
        ends_at=(now + timedelta(hours=1)).isoformat(),
        **PARIS,
    )
    guest = await make_user()
    far = {"latitude": 45.764, "longitude": 4.8357}  # Lyon
    assert (await suggest(client, event["id"], guest, "aaa", **far)).status_code == 403
    assert (await suggest(client, event["id"], guest, "aaa")).status_code == 403
    assert (await suggest(client, event["id"], guest, "aaa", **PARIS)).status_code == 201


async def test_location_time_needs_complete_settings(client, host):
    response = await client.post(
        "/events", json={"name": "x", "license": "location_time"}, headers=host.headers
    )
    assert response.status_code == 422


async def test_only_owner_edits_event(client, create_event, host, make_user):
    event = await create_event()
    guest = await make_user()
    path = f"/events/{event['id']}"
    assert (await client.patch(path, json={"name": "x"}, headers=guest.headers)).status_code == 403
    updated = await client.patch(path, json={"visibility": "private"}, headers=host.headers)
    assert updated.json()["visibility"] == "private"
    broken = await client.patch(path, json={"license": "location_time"}, headers=host.headers)
    assert broken.status_code == 422


# --- Concurrency (subject: "several people vote for different tracks or the same one") ---


async def test_many_users_vote_for_the_same_track_at_once(client, create_event, host, make_user):
    event = await create_event()
    track = (await suggest(client, event["id"], host, "aaa")).json()["queue"][0]["id"]
    voters = await asyncio.gather(*(make_user() for _ in range(50)))

    responses = await asyncio.gather(*(vote(client, event["id"], track, v) for v in voters))

    assert all(r.status_code == 200 for r in responses)
    queue = (await client.get(f"/events/{event['id']}/queue", headers=host.headers)).json()
    assert queue["queue"][0]["votes"] == 50


async def test_one_user_spamming_votes_counts_once(client, create_event, host):
    event = await create_event()
    track = (await suggest(client, event["id"], host, "aaa")).json()["queue"][0]["id"]

    await asyncio.gather(*(vote(client, event["id"], track, host) for _ in range(20)))

    queue = (await client.get(f"/events/{event['id']}/queue", headers=host.headers)).json()
    assert queue["queue"][0]["votes"] == 1


async def test_parallel_votes_on_different_tracks(client, create_event, host, make_user):
    event = await create_event()
    for external_id in ("aaa", "bbb", "ccc"):
        await suggest(client, event["id"], host, external_id)
    queue = (await client.get(f"/events/{event['id']}/queue", headers=host.headers)).json()
    tracks = {t["external_id"]: t["id"] for t in queue["queue"]}
    voters = await asyncio.gather(*(make_user() for _ in range(30)))
    plan = {"aaa": voters[:5], "bbb": voters[5:30], "ccc": voters[:20]}  # overlapping voters

    await asyncio.gather(
        *(vote(client, event["id"], tracks[t], v) for t, vs in plan.items() for v in vs)
    )

    queue = (await client.get(f"/events/{event['id']}/queue", headers=host.headers)).json()
    assert [(t["external_id"], t["votes"]) for t in queue["queue"]] == [
        ("bbb", 25),
        ("ccc", 20),
        ("aaa", 5),
    ]


async def test_same_track_suggested_at_once_is_queued_once(client, create_event, make_user):
    event = await create_event()
    guests = await asyncio.gather(*(make_user() for _ in range(10)))

    responses = await asyncio.gather(*(suggest(client, event["id"], g, "aaa") for g in guests))

    assert sorted(r.status_code for r in responses) == [201] + [409] * 9


async def test_double_next_does_not_skip_a_track(client, create_event, host):
    event = await create_event()
    for external_id in ("aaa", "bbb", "ccc"):
        await suggest(client, event["id"], host, external_id)

    await asyncio.gather(
        *(client.post(f"/events/{event['id']}/next", headers=host.headers) for _ in range(2))
    )

    queue = (await client.get(f"/events/{event['id']}/queue", headers=host.headers)).json()
    # Serialized by the row lock: exactly two advances, in order.
    assert queue["now_playing"]["external_id"] == "bbb"
    assert ids(queue) == ["ccc"]
