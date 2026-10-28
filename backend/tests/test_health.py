from fastapi.testclient import TestClient

from app.core.db import get_session
from app.core.redis import get_redis
from app.main import app


class FakeSession:
    async def execute(self, _):
        return None


class BrokenRedis:
    async def ping(self):
        raise ConnectionError("redis down")


async def fake_session():
    yield FakeSession()


def test_health_reports_each_dependency():
    app.dependency_overrides[get_session] = fake_session
    app.dependency_overrides[get_redis] = lambda: BrokenRedis()
    try:
        response = TestClient(app).get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"api": "ok", "postgres": "ok", "redis": "error"}
