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


async def _wait_for_run(client, run_id, timeout=60.0):
    import asyncio

    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        body = (await client.get(f"/api/runs/{run_id}")).json()
        if body["status"] in ("completed", "failed"):
            return body
        await asyncio.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish in {timeout}s")


async def test_pipeline_run_completes_and_dedupes(client):
    # EPIC-07: POST /api/runs is now async — 202 + background pipeline (was collect-only 200).
    await _upload(client, SAMPLE.read_bytes())

    first = await client.post("/api/runs", json={"period_days": 90})
    assert first.status_code == 202
    run_id = first.json()["id"]
    assert first.json()["status"] in ("pending", "running")

    done = await _wait_for_run(client, run_id)
    assert done["status"] == "completed", done["error"]
    assert set(done["stage_timings"]) >= {"collect", "classify", "analyze", "map", "strategy"}

    summary = (await client.get(f"/api/results/{run_id}/summary")).json()
    assert summary["competitors_analyzed"] == 5
    assert summary["total_posts"] > 0

    second = await client.post("/api/runs", json={"period_days": 90})
    second_id = second.json()["id"]
    await _wait_for_run(client, second_id)
    # global URL dedup: the second run collects nothing new
    assert (await client.get(f"/api/results/{second_id}/summary")).json()["total_posts"] == 0


async def test_results_before_completion_is_409(client):
    await _upload(client, SAMPLE.read_bytes())
    run_id = (await client.post("/api/runs", json={"period_days": 30})).json()["id"]
    early = await client.get(f"/api/results/{run_id}/summary")
    # either the pipeline hasn't finished (409) or it already has (200) — both are valid,
    # but a still-processing run must never 500
    assert early.status_code in (200, 409)
    if early.status_code == 409:
        assert early.json()["status"] == 409
    await _wait_for_run(client, run_id)


async def test_run_rejects_bad_period(client):
    await _upload(client, SAMPLE.read_bytes())
    resp = await client.post("/api/runs", json={"period_days": 42})
    assert resp.status_code == 422


async def test_run_with_no_competitors_is_400(client):
    resp = await client.post("/api/runs", json={})
    assert resp.status_code == 400
