from pathlib import Path

import httpx
import pandas as pd
import pytest

from app.api.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = PROJECT_ROOT / "data" / "input" / "sample_competitors.xlsx"


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/api.db")
    monkeypatch.setenv("LLM_FAKE_MODE", "true")
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


def _xlsx_bytes(rows):
    import io

    buf = io.BytesIO()
    pd.DataFrame(
        rows, columns=["Competitor", "LinkedIn URL", "Industry", "Country/Market", "Priority"]
    ).to_excel(buf, index=False)
    return buf.getvalue()


async def _upload(client, payload, filename="in.xlsx"):
    return await client.post(
        "/api/competitors/upload",
        files={"file": (filename, payload, "application/vnd.ms-excel")},
    )


async def test_upload_sample_returns_five_accepted(client):
    resp = await _upload(client, SAMPLE.read_bytes(), "sample_competitors.xlsx")
    assert resp.status_code == 200
    body = resp.json()
    assert body["accepted"] == 5
    assert body["rejected"] == []
    assert len(body["stored_competitor_ids"]) == 5

    listing = await client.get("/api/competitors")
    assert listing.status_code == 200
    assert len(listing.json()) == 5


async def test_upload_corrupt_rows_reported_without_failing(client):
    payload = _xlsx_bytes(
        [
            ["Good", "https://www.linkedin.com/company/good", "IT", "USA", "High"],
            ["Person", "https://www.linkedin.com/in/jane", "IT", "USA", "Low"],
            ["Bad prio", "https://www.linkedin.com/company/badp", "IT", "USA", "Later"],
        ]
    )
    resp = await _upload(client, payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["accepted"] == 1
    rows = {e["row"]: e["reason"] for e in body["rejected"]}
    assert set(rows) == {3, 4}


async def test_upload_missing_columns_is_400(client):
    payload = pd.DataFrame([["Acme"]], columns=["Competitor"])
    import io

    buf = io.BytesIO()
    payload.to_excel(buf, index=False)
    resp = await _upload(client, buf.getvalue())
    assert resp.status_code == 400
    assert "LinkedIn URL" in resp.json()["detail"]


async def test_collect_run_persists_and_dedupes(client):
    await _upload(client, SAMPLE.read_bytes())

    first = await client.post("/api/runs", json={"period_days": 90})
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "completed"
    assert body["adapter"] == "mock"
    assert body["profiles_collected"] == 5
    assert body["posts_inserted"] > 0
    assert all(c["ok"] for c in body["competitors"])

    second = await client.post("/api/runs", json={"period_days": 90})
    assert second.json()["posts_inserted"] == 0


async def test_run_rejects_bad_period(client):
    await _upload(client, SAMPLE.read_bytes())
    resp = await client.post("/api/runs", json={"period_days": 42})
    assert resp.status_code == 422


async def test_run_with_no_competitors_is_400(client):
    resp = await client.post("/api/runs", json={})
    assert resp.status_code == 400
