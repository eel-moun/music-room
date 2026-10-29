"""Who may subscribe to which WebSocket room (same policies as REST)."""

from app.realtime.access import can_join


async def test_user_room_is_private(make_user):
    a, b = await make_user(), await make_user()
    assert await can_join(a.id, f"user:{a.id}")
    assert not await can_join(b.id, f"user:{a.id}")


async def test_event_room_follows_event_visibility(client, make_user):
    host, guest = await make_user(), await make_user()
    public = (await client.post("/events", json={"name": "p"}, headers=host.headers)).json()
    private = (
        await client.post(
            "/events", json={"name": "s", "visibility": "private"}, headers=host.headers
        )
    ).json()
    assert await can_join(guest.id, f"event:{public['id']}")
    assert not await can_join(guest.id, f"event:{private['id']}")
    assert await can_join(host.id, f"event:{private['id']}")


async def test_device_room_needs_ownership_or_delegation(client, make_user, befriend):
    owner, friend = await make_user(), await make_user()
    await befriend(owner, friend)
    device = (
        await client.post("/devices", json={"name": "d", "platform": "ios"}, headers=owner.headers)
    ).json()
    room = f"device:{device['id']}"
    assert await can_join(owner.id, room)
    assert not await can_join(friend.id, room)
    await client.post(
        f"/devices/{device['id']}/delegations",
        json={"grantee_id": str(friend.id), "permissions": ["volume"]},
        headers=owner.headers,
    )
    assert await can_join(friend.id, room)


async def test_unknown_or_malformed_rooms(make_user):
    user = await make_user()
    for room in ("lobby", "event:not-a-uuid", "admin:1", f"playlist:{user.id}"):
        assert not await can_join(user.id, room)
