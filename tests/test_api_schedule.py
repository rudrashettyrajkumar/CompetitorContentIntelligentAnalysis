"""EPIC-08 schedule API: create / list / delete, invalid cron rejected."""

from pathlib import Path

import httpx
import pytest

from app.api.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = PROJECT_ROOT / "data" / "input" / "sample_competitors.xlsx"


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/api.db")
    monkeypatch.setenv("LLM_FAKE_MODE", "true")
    # keep the background APScheduler quiet in this test module
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    from app.config.settings import get_app_config, get_settings

    get_settings.cache_clear()
    get_app_config.cache_clear()
    app = create_app()
    async with httpx.ASGITransport(app=app) as transport:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                yield c
    get_settings.cache_clear()
    get_app_config.cache_clear()


async def test_schedule_crud(client):
    empty = await client.get("/api/schedule")
    assert empty.status_code == 200 and empty.json() == []

    created = await client.post(
        "/api/schedule",
        json={"cron": "0 6 * * 1", "period_days": 30, "adapter": "mock", "enabled": True},
    )
    assert created.status_code == 201
    sid = created.json()["id"]
    assert created.json()["cron"] == "0 6 * * 1"

    listing = await client.get("/api/schedule")
    assert [s["id"] for s in listing.json()] == [sid]

    deleted = await client.delete(f"/api/schedule/{sid}")
    assert deleted.status_code == 204
    assert (await client.get("/api/schedule")).json() == []
    assert (await client.delete(f"/api/schedule/{sid}")).status_code == 404


async def test_invalid_cron_is_422(client):
    resp = await client.post(
        "/api/schedule", json={"cron": "every monday please", "period_days": 30, "adapter": "mock"}
    )
    assert resp.status_code == 422


async def test_default_cron_when_omitted(client):
    resp = await client.post("/api/schedule", json={"period_days": 7, "adapter": "mock"})
    assert resp.status_code == 201
    assert resp.json()["cron"]  # filled from config: loop.default_cron
    assert resp.json()["period_days"] == 7
