"""Deterministic FakeLLM responder for the ``campaign_cluster`` prompt.

Only used to exercise the prompt pack itself and the ``DeepCampaignAgent`` fallback path
offline — the normal offline campaign path is ``FakeCampaignAgent`` (no LLM at all). The
responder reads the rendered post lines back out, buckets them by ``topic=`` and emits one
campaign per bucket that has 3+ posts.
"""

from __future__ import annotations

import re

from app.core.model_router import FakeLLM
from app.schemas.analysis import CampaignClustering

_HEADER_RE = re.compile(r"^\[(\d+)\]\s+(\S+)\s+\|\s+(\S+)\s+\|\s+topic=(\S+)", re.MULTILINE)
_URL_RE = re.compile(r"^\s*url:\s*(\S+)", re.MULTILINE)


def _campaign_responder(_system: str, user: str) -> dict:
    headers = _HEADER_RE.findall(user)
    urls = _URL_RE.findall(user)
    rows = list(zip(headers, urls, strict=False))

    buckets: dict[str, list[tuple[str, str, str]]] = {}
    for (_idx, date, fmt, topic), url in rows:
        buckets.setdefault(topic, []).append((date, fmt, url))

    campaigns = []
    for topic, items in buckets.items():
        if len(items) < 3:
            continue
        items.sort()
        campaigns.append(
            {
                "name": f"{topic.replace('_', ' ').title()} campaign",
                "theme": topic.replace("_", " "),
                "post_urls": [url for _d, _f, url in items],
                "start_date": items[0][0],
                "end_date": items[-1][0],
                "formats": sorted({fmt for _d, fmt, _u in items}),
                "keywords": [topic.replace("_", " ")],
                "hashtags": [],
                "dominant_cta": None,
                "performance_summary": f"{len(items)} posts in the {topic} theme",
            }
        )
    return {"campaigns": campaigns}


def register_campaign_fakes(fake_llm: FakeLLM) -> None:
    fake_llm.register(CampaignClustering, _campaign_responder)
