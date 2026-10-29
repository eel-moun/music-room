import asyncio
import re

import pytest

from app.auth.google import GoogleIdentity
from tests.conftest import PASSWORD


def token_from(outbox, kind: str) -> str:
    """Pull the token out of the last verification link or reset email."""
    body = outbox[-1].get_content()
    if kind == "verify":
        return re.search(r"token=([\w-]+)", body).group(1)
    return re.search(r"\n\n([\w-]{30,})\n\n", body).group(1)


async def register(client, email="alice@example.com", password=PASSWORD, name="Alice"):
    return await client.post(
        "/auth/register", json={"email": email, "password": password, "display_name": name}
    )


async def login(client, email="alice@example.com", password=PASSWORD):
    return await client.post("/auth/login", json={"email": email, "password": password})


# --- Email / password ------------------------------------------------------------


async def test_register_verify_login(client, outbox):
    assert (await register(client)).status_code == 202
    assert outbox[-1]["To"] == "alice@example.com"

    response = await login(client)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "email_not_verified"

    # The emailed link is a plain GET opened in a browser (no device headers).
    link = await client.get(
        "/auth/verify-email", params={"token": token_from(outbox, "verify")}, headers={}
    )
    assert link.status_code == 200

    response = await login(client)
    assert response.status_code == 200
    tokens = response.json()
    me = await client.get(
        "/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.json()["email"] == "alice@example.com"
    assert me.json()["email_verified"] is True


async def test_verification_token_works_once(client, outbox):
    await register(client)
    token = token_from(outbox, "verify")
    assert (await client.post("/auth/verify-email", json={"token": token})).status_code == 200
    assert (await client.post("/auth/verify-email", json={"token": token})).status_code == 400


async def test_register_existing_email_does_not_reveal_it(client, outbox):
    await register(client)
    second = await register(client, password="another-password")
    assert second.status_code == 202  # same answer as a new account
    assert "already have one" in outbox[-1].get_content()


async def test_wrong_password_and_unknown_email_look_the_same(client, make_user):
    user = await make_user("bob")
    wrong = await login(client, user.email, "wrong-password")
    unknown = await login(client, "nobody@example.com", "wrong-password")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


@pytest.mark.parametrize("password", ["short", "x" * 129])
async def test_password_length_is_enforced(client, password):
    assert (await register(client, password=password)).status_code == 422


# --- Refresh rotation ------------------------------------------------------------


async def test_refresh_rotates_tokens(client, make_user):
    user = await make_user()
    first = await client.post("/auth/refresh", json={"refresh_token": user.refresh_token})
    assert first.status_code == 200
    assert first.json()["refresh_token"] != user.refresh_token

    second = await client.post(
        "/auth/refresh", json={"refresh_token": first.json()["refresh_token"]}
    )
    assert second.status_code == 200


async def test_reused_refresh_token_revokes_the_whole_family(client, make_user):
    user = await make_user()
    rotated = (
        await client.post("/auth/refresh", json={"refresh_token": user.refresh_token})
    ).json()

    # An attacker replays the old token...
    replay = await client.post("/auth/refresh", json={"refresh_token": user.refresh_token})
    assert replay.status_code == 401
    # ...so the legitimate newer token stops working too: everyone logs in again.
    after = await client.post("/auth/refresh", json={"refresh_token": rotated["refresh_token"]})
    assert after.status_code == 401


async def test_concurrent_refresh_with_same_token_succeeds_once(client, make_user):
    user = await make_user()
    responses = await asyncio.gather(
        *(
            client.post("/auth/refresh", json={"refresh_token": user.refresh_token})
            for _ in range(5)
        )
    )
    assert sorted(r.status_code for r in responses).count(200) == 1


async def test_logout_revokes_refresh_token(client, make_user):
    user = await make_user()
    assert (
        await client.post("/auth/logout", json={"refresh_token": user.refresh_token})
    ).status_code == 204
    response = await client.post("/auth/refresh", json={"refresh_token": user.refresh_token})
    assert response.status_code == 401


async def test_invalid_access_token_is_rejected(client):
    response = await client.get("/users/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


# --- Password reset ----------------------------------------------------------------


async def test_forgot_and_reset_password(client, outbox, make_user):
    user = await make_user("carol")
    assert (
        await client.post("/auth/forgot-password", json={"email": user.email})
    ).status_code == 202
    token = token_from(outbox, "reset")

    response = await client.post(
        "/auth/reset-password", json={"token": token, "new_password": "brand-new-password"}
    )
    assert response.status_code == 200
    assert (await login(client, user.email, PASSWORD)).status_code == 401
    assert (await login(client, user.email, "brand-new-password")).status_code == 200
    # Existing sessions were ended by the reset.
    refreshed = await client.post("/auth/refresh", json={"refresh_token": user.refresh_token})
    assert refreshed.status_code == 401
    # And the code can't be used twice.
    again = await client.post(
        "/auth/reset-password", json={"token": token, "new_password": "yet-another-pass"}
    )
    assert again.status_code == 400


async def test_forgot_password_unknown_email_looks_the_same(client, outbox):
    response = await client.post("/auth/forgot-password", json={"email": "ghost@example.com"})
    assert response.status_code == 202
    assert outbox == []


async def test_change_password(client, make_user):
    user = await make_user()
    bad = await client.post(
        "/auth/change-password",
        json={"current_password": "wrong", "new_password": "new-password-1"},
        headers=user.headers,
    )
    assert bad.status_code == 401
    ok = await client.post(
        "/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "new-password-1"},
        headers=user.headers,
    )
    assert ok.status_code == 200
    assert (await login(client, user.email, "new-password-1")).status_code == 200


# --- Rate limiting -------------------------------------------------------------------


async def test_login_is_rate_limited_per_account(client, make_user):
    user = await make_user()
    statuses = [(await login(client, user.email, "wrong")).status_code for _ in range(11)]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
    blocked = await login(client, user.email, PASSWORD)  # even the right password
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


async def test_forgot_password_is_rate_limited(client, outbox):
    statuses = [
        (await client.post("/auth/forgot-password", json={"email": "x@example.com"})).status_code
        for _ in range(4)
    ]
    assert statuses == [202, 202, 202, 429]


# --- Google ----------------------------------------------------------------------------


def google(sub="g-1", email="gina@gmail.com", verified=True, name="Gina"):
    return GoogleIdentity(subject=sub, email=email, email_verified=verified, name=name)


async def test_google_sign_up_then_login(client, google_accounts):
    google_accounts["tok"] = google()
    first = await client.post("/auth/google", json={"id_token": "tok"})
    assert first.status_code == 200
    second = await client.post("/auth/google", json={"id_token": "tok"})
    assert second.status_code == 200
    me = await client.get(
        "/users/me", headers={"Authorization": f"Bearer {second.json()['access_token']}"}
    )
    assert me.json()["google_linked"] is True
    assert me.json()["has_password"] is False


async def test_google_invalid_token(client, google_accounts):
    assert (await client.post("/auth/google", json={"id_token": "forged"})).status_code == 401


async def test_google_never_takes_over_an_existing_email(client, google_accounts, make_user):
    user = await make_user("dave")
    google_accounts["tok"] = google(email=user.email)
    response = await client.post("/auth/google", json={"id_token": "tok"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "account_exists"


async def test_link_google_then_log_in_with_it(client, google_accounts, make_user):
    user = await make_user("erin")
    google_accounts["tok"] = google(email="erin.other@gmail.com")
    linked = await client.post("/auth/google/link", json={"id_token": "tok"}, headers=user.headers)
    assert linked.status_code == 200

    response = await client.post("/auth/google", json={"id_token": "tok"})
    me = await client.get(
        "/users/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"}
    )
    assert me.json()["id"] == str(user.id)


async def test_google_account_cannot_be_linked_twice(client, google_accounts, make_user):
    a, b = await make_user(), await make_user()
    google_accounts["tok"] = google()
    await client.post("/auth/google/link", json={"id_token": "tok"}, headers=a.headers)
    response = await client.post("/auth/google/link", json={"id_token": "tok"}, headers=b.headers)
    assert response.status_code == 409


async def test_unlink_requires_another_login_method(client, google_accounts, make_user):
    google_accounts["tok"] = google()
    tokens = (await client.post("/auth/google", json={"id_token": "tok"})).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert (await client.delete("/auth/google/link", headers=headers)).status_code == 409

    user = await make_user()
    google_accounts["tok2"] = google(sub="g-2", email="f@gmail.com")
    await client.post("/auth/google/link", json={"id_token": "tok2"}, headers=user.headers)
    assert (await client.delete("/auth/google/link", headers=user.headers)).status_code == 200
