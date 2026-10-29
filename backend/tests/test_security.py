"""IDOR sweep: user B tries every owner-only action on user A's resources.

Subject V.6: "An authenticated user must have access to their data, but not to
other users' data." Private resources answer 404 (they don't exist for B);
public ones B can see answer 403 when B tries to administer them.
"""

import pytest


@pytest.fixture
async def world(client, make_user, befriend):
    a, b = await make_user("alice"), await make_user("mallory")
    h = a.headers
    private_event = (
        await client.post("/events", json={"name": "e", "visibility": "private"}, headers=h)
    ).json()
    public_event = (await client.post("/events", json={"name": "p"}, headers=h)).json()
    private_pl = (
        await client.post("/playlists", json={"name": "s", "visibility": "private"}, headers=h)
    ).json()
    public_pl = (await client.post("/playlists", json={"name": "p"}, headers=h)).json()
    device = (
        await client.post("/devices", json={"name": "d", "platform": "ios"}, headers=h)
    ).json()
    friend = await make_user()
    await befriend(a, friend)
    delegation = (
        await client.post(
            f"/devices/{device['id']}/delegations",
            json={"grantee_id": str(friend.id), "permissions": ["playback"]},
            headers=h,
        )
    ).json()
    return {
        "attacker": b,
        "pe": private_event["id"],
        "ue": public_event["id"],
        "pp": private_pl["id"],
        "up": public_pl["id"],
        "dev": device["id"],
        "del": delegation["id"],
        "victim": a.id,
        "friend": friend.id,
    }


ATTACKS = [
    # (method, path, json body, expected status)
    ("GET", "/events/{pe}", None, 404),
    ("GET", "/events/{pe}/queue", None, 404),
    ("PATCH", "/events/{pe}", {"name": "x"}, 404),
    ("DELETE", "/events/{pe}", None, 404),
    ("POST", "/events/{pe}/tracks", {"external_id": "abc"}, 404),
    ("PATCH", "/events/{ue}", {"name": "x"}, 403),
    ("DELETE", "/events/{ue}", None, 403),
    ("POST", "/events/{ue}/next", None, 403),
    ("GET", "/events/{ue}/invites", None, 403),
    ("POST", "/events/{ue}/invites", {"user_id": "{attacker_id}"}, 403),
    ("GET", "/playlists/{pp}", None, 404),
    ("POST", "/playlists/{pp}/tracks", {"external_id": "abc", "version": 1}, 404),
    ("PATCH", "/playlists/{up}", {"visibility": "private"}, 403),
    ("DELETE", "/playlists/{up}", None, 403),
    ("POST", "/playlists/{up}/members", {"user_id": "{attacker_id}"}, 403),
    ("PATCH", "/devices/{dev}", {"name": "mine now"}, 404),
    ("DELETE", "/devices/{dev}", None, 404),
    ("GET", "/devices/{dev}/delegations", None, 404),
    (
        "POST",
        "/devices/{dev}/delegations",
        {"grantee_id": "{attacker_id}", "permissions": ["volume"]},
        404,
    ),
    ("DELETE", "/devices/{dev}/delegations/{del}", None, 404),
    ("POST", "/devices/{dev}/commands", {"command": "pause"}, 404),
    ("PUT", "/devices/{dev}/state", {"is_playing": False, "volume": 0}, 404),
    ("GET", "/devices/{dev}/state", None, 404),
    ("DELETE", "/friends/{friend}", None, 404),
]


@pytest.mark.parametrize(("method", "path", "body", "expected"), ATTACKS)
async def test_cannot_touch_other_users_resources(client, world, method, path, body, expected):
    attacker = world["attacker"]
    fill = {k: v for k, v in world.items() if k != "attacker"} | {"attacker_id": attacker.id}
    url = path.format(**fill)
    if body is not None:
        body = {k: v.format(**fill) if isinstance(v, str) else v for k, v in body.items()}
    response = await client.request(method, url, json=body, headers=attacker.headers)
    assert response.status_code == expected, (method, url, response.text)


async def test_private_profile_fields_stay_private(client, world):
    response = await client.get(f"/users/{world['victim']}", headers=world["attacker"].headers)
    profile = response.json()
    assert profile["friends_info"] is None
    assert profile["private_info"] is None
    assert "email" not in profile
