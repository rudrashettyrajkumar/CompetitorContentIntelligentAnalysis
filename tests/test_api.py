import httpx
import pytest

from app.api.main import create_app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/api.db")
    monkeypatch.setenv("LLM_FAKE_MODE", "true")
    from app.config.settings import get_settings

    get_settings.cache_clear()
    app = create_app()
    async with httpx.ASGITransport(app=app) as transport:
        # lifespan needs to run for DB setup
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                yield client
    get_settings.cache_clear()


async def test_health(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
