from prometheus_client import REGISTRY


async def test_requests_are_counted_by_route_template_and_platform(client, make_user):
    user = await make_user()
    labels = {"method": "GET", "route": "/users/{user_id}", "status": "200", "platform": "android"}
    before = REGISTRY.get_sample_value("http_requests_total", labels) or 0

    await client.get(f"/users/{user.id}", headers=user.headers)

    # The template, not /users/<uuid>: one series per route, not one per user.
    assert REGISTRY.get_sample_value("http_requests_total", labels) == before + 1


async def test_oversized_body_rejected(client):
    response = await client.post(
        "/auth/login", content=b"x" * 1_000_001, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
