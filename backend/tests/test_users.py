import asyncio


async def test_profile_visibility_by_relation(client, make_user, befriend):
    alice, friend, stranger = await make_user("alice"), await make_user(), await make_user()
    await befriend(alice, friend)
    await client.patch(
        "/users/me",
        json={
            "public_info": {"bio": "DJ"},
            "friends_info": {"city": "Lyon"},
            "private_info": {"phone": "+33600000000"},
            "music_preferences": {"genres": ["house"]},
        },
        headers=alice.headers,
    )

    as_stranger = (await client.get(f"/users/{alice.id}", headers=stranger.headers)).json()
    assert as_stranger["public_info"]["bio"] == "DJ"
    assert as_stranger["music_preferences"]["genres"] == ["house"]
    assert as_stranger["friends_info"] is None
    assert as_stranger["private_info"] is None
    assert "email" not in as_stranger

    as_friend = (await client.get(f"/users/{alice.id}", headers=friend.headers)).json()
    assert as_friend["relation"] == "friend"
    assert as_friend["friends_info"]["city"] == "Lyon"
    assert as_friend["private_info"] is None

    me = (await client.get("/users/me", headers=alice.headers)).json()
    assert me["private_info"]["phone"] == "+33600000000"


async def test_profile_fields_are_validated(client, make_user):
    user = await make_user()
    response = await client.patch(
        "/users/me", json={"public_info": {"bio": "x" * 501}}, headers=user.headers
    )
    assert response.status_code == 422


async def test_search_users(client, make_user):
    me = await make_user("searcher")
    await make_user("Zoe_DJ")
    await make_user("Other")
    found = (await client.get("/users", params={"q": "zoe"}, headers=me.headers)).json()
    assert [u["display_name"] for u in found] == ["Zoe_DJ"]
    # "_" is a LIKE wildcard: it must be matched literally.
    assert (await client.get("/users", params={"q": "e_d"}, headers=me.headers)).json()


async def test_friend_request_lifecycle(client, make_user):
    a, b = await make_user(), await make_user()
    sent = await client.post("/friends/requests", json={"user_id": str(b.id)}, headers=a.headers)
    assert sent.status_code == 201

    incoming = (await client.get("/friends/requests", headers=b.headers)).json()
    assert incoming[0]["direction"] == "incoming"
    # Only the addressee can accept.
    assert (
        await client.post(f"/friends/requests/{sent.json()['id']}/accept", headers=a.headers)
    ).status_code == 404
    await client.post(f"/friends/requests/{sent.json()['id']}/accept", headers=b.headers)

    assert [f["user"]["id"] for f in (await client.get("/friends", headers=a.headers)).json()] == [
        str(b.id)
    ]
    assert (await client.delete(f"/friends/{b.id}", headers=a.headers)).status_code == 204
    assert (await client.get("/friends", headers=b.headers)).json() == []


async def test_decline_friend_request(client, make_user):
    a, b = await make_user(), await make_user()
    sent = await client.post("/friends/requests", json={"user_id": str(b.id)}, headers=a.headers)
    response = await client.delete(f"/friends/requests/{sent.json()['id']}", headers=b.headers)
    assert response.status_code == 204
    assert (await client.get("/friends/requests", headers=a.headers)).json() == []


async def test_requests_in_both_directions_become_a_friendship(client, make_user):
    a, b = await make_user(), await make_user()
    await client.post("/friends/requests", json={"user_id": str(b.id)}, headers=a.headers)
    back = await client.post("/friends/requests", json={"user_id": str(a.id)}, headers=b.headers)
    assert back.json()["status"] == "accepted"


async def test_simultaneous_requests_create_one_row(client, make_user):
    a, b = await make_user(), await make_user()
    responses = await asyncio.gather(
        client.post("/friends/requests", json={"user_id": str(b.id)}, headers=a.headers),
        client.post("/friends/requests", json={"user_id": str(a.id)}, headers=b.headers),
    )
    assert sorted(r.status_code for r in responses) in ([201, 201], [201, 409])
    pending = (await client.get("/friends/requests", headers=a.headers)).json()
    friends = (await client.get("/friends", headers=a.headers)).json()
    assert len(pending) + len(friends) == 1


async def test_cannot_befriend_self(client, make_user):
    a = await make_user()
    response = await client.post(
        "/friends/requests", json={"user_id": str(a.id)}, headers=a.headers
    )
    assert response.status_code == 400
