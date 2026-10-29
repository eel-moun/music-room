from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.core.db import SessionLocal
from app.delegation.models import Delegation

STATE = {"is_playing": True, "volume": 40, "position_s": 12}


@pytest.fixture
async def owner(make_user):
    return await make_user("owner")


@pytest.fixture
async def friend(make_user, owner, befriend):
    friend = await make_user("friend")
    await befriend(owner, friend)
    return friend


@pytest.fixture
async def device(client, owner):
    response = await client.post(
        "/devices", json={"name": "Living room", "platform": "android"}, headers=owner.headers
    )
    assert response.status_code == 201
    return response.json()


async def grant(client, owner, device, grantee, permissions=("playback",), **extra):
    return await client.post(
        f"/devices/{device['id']}/delegations",
        json={"grantee_id": str(grantee.id), "permissions": list(permissions)} | extra,
        headers=owner.headers,
    )


async def command(client, device, user, body):
    return await client.post(f"/devices/{device['id']}/commands", json=body, headers=user.headers)


async def test_friend_controls_device_with_a_delegation(client, owner, friend, device):
    assert (await command(client, device, friend, {"command": "pause"})).status_code == 404
    assert (await grant(client, owner, device, friend)).status_code == 201

    assert (await command(client, device, friend, {"command": "pause"})).status_code == 202
    controllable = (await client.get("/devices/controllable", headers=friend.headers)).json()
    assert [d["id"] for d in controllable] == [device["id"]]


async def test_only_friends_get_delegations(client, owner, device, make_user):
    stranger = await make_user()
    response = await grant(client, owner, device, stranger)
    assert response.status_code == 400


async def test_permissions_are_per_command(client, owner, friend, device):
    await grant(client, owner, device, friend, permissions=["playback"])
    volume = await command(client, device, friend, {"command": "set_volume", "volume": 80})
    assert volume.status_code == 403
    assert volume.json()["detail"]["code"] == "permission_missing"


async def test_revoked_delegation_stops_control(client, owner, friend, device):
    delegation = (await grant(client, owner, device, friend)).json()
    revoke = await client.delete(
        f"/devices/{device['id']}/delegations/{delegation['id']}", headers=owner.headers
    )
    assert revoke.status_code == 204
    assert (await command(client, device, friend, {"command": "play"})).status_code == 404
    assert (await client.get("/devices/controllable", headers=friend.headers)).json() == []


async def test_expired_delegation_stops_control(client, owner, friend, device):
    soon = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    delegation = (await grant(client, owner, device, friend, expires_at=soon)).json()
    async with SessionLocal() as session:  # fast-forward: the delegation expired
        await session.execute(
            update(Delegation)
            .where(Delegation.id == delegation["id"])
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()
    response = await command(client, device, friend, {"command": "play"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "delegation_expired"


async def test_unfriending_stops_control(client, owner, friend, device):
    await grant(client, owner, device, friend)
    await client.delete(f"/friends/{friend.id}", headers=owner.headers)
    response = await command(client, device, friend, {"command": "play"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "not_friends"


async def test_delegation_is_per_device(client, owner, friend, device):
    other = (
        await client.post(
            "/devices", json={"name": "Kitchen", "platform": "ios"}, headers=owner.headers
        )
    ).json()
    await grant(client, owner, device, friend)
    assert (await command(client, other, friend, {"command": "play"})).status_code == 404


async def test_command_arguments_are_validated(client, owner, device):
    missing = await command(client, device, owner, {"command": "play_track"})
    assert missing.status_code == 422
    loud = await command(client, device, owner, {"command": "set_volume", "volume": 101})
    assert loud.status_code == 422
    ok = await command(
        client, device, owner, {"command": "play_track", "track": {"external_id": "abc"}}
    )
    assert ok.status_code == 202


async def test_state_is_reported_by_owner_and_read_by_delegates(client, owner, friend, device):
    path = f"/devices/{device['id']}/state"
    assert (await client.put(path, json=STATE, headers=friend.headers)).status_code == 404
    assert (await client.put(path, json=STATE, headers=owner.headers)).status_code == 204
    assert (await client.get(path, headers=friend.headers)).status_code == 404
    await grant(client, owner, device, friend)
    assert (await client.get(path, headers=friend.headers)).json()["volume"] == 40


async def test_only_owner_manages_device(client, owner, friend, device):
    path = f"/devices/{device['id']}"
    assert (await client.delete(path, headers=friend.headers)).status_code == 404
    assert (await client.get(f"{path}/delegations", headers=friend.headers)).status_code == 404
    assert (await grant(client, friend, device, owner)).status_code == 404
