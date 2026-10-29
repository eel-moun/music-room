from app.core.redis import get_redis
from app.main import app


class BrokenRedis:
    async def ping(self):
        raise ConnectionError("redis down")


async def test_health_reports_each_dependency(client):
    response = await client.get("/health")
    assert response.json() == {"api": "ok", "postgres": "ok", "redis": "ok"}

    app.dependency_overrides[get_redis] = lambda: BrokenRedis()
    try:
        response = await client.get("/health")
    finally:
        app.dependency_overrides.pop(get_redis)
    assert response.status_code == 200
    assert response.json() == {"api": "ok", "postgres": "ok", "redis": "error"}
