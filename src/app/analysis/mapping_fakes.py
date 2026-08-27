"""Deterministic FakeLLM responders for the EPIC-05 mapping prompts.

Keeps ``make test`` and ``make demo`` fully offline: ``positioning_summary`` and
``why_it_worked`` return schema-valid, content-derived text with zero quota spend.
"""

from __future__ import annotations

import re

from app.core.model_router import FakeLLM
from app.schemas.strategy_map import PositioningSummary, WhyItWorkedBatch

_COMPETITOR_RE = re.compile(r"^Competitor:\s*(.+)$", re.MULTILINE)
_THEMES_RE = re.compile(r"^Primary themes:\s*(.*)$", re.MULTILINE)
_BEST_FMT_RE = re.compile(r"^Best-performing format:\s*(.*)$", re.MULTILINE)
_POST_RE = re.compile(
    r"^\[(\d+)\]\s+(?P<competitor>.+?)\s+\|\s+\S+\s+\|\s+format=(?P<format>\S+)\s+\|\s+"
    r"topic=(?P<topic>\S+).*?\n\s+(?P<body>.*)$",
    re.MULTILINE,
)


def _positioning_responder(_system: str, user: str) -> dict:
    competitor = (_COMPETITOR_RE.search(user) or [None, "The competitor"])[1].strip()
    themes = (_THEMES_RE.search(user) or [None, ""])[1].strip() or "a broad content set"
    best_fmt = (_BEST_FMT_RE.search(user) or [None, "n/a"])[1].strip()
    summary = (
        f"{competitor} concentrates on {themes}, aimed at B2B buyers researching those areas. "
        f"They lean on {best_fmt} content and a steady cadence to stay visible. "
        f"Positioning reads as a specialist voice rather than a broad publisher."
    )
    return PositioningSummary(summary=summary).model_dump()


def _why_it_worked_responder(_system: str, user: str) -> dict:
    results = []
    for m in _POST_RE.finditer(user):
        idx = int(m.group(1))
        body = m.group("body").strip()
        fmt = m.group("format")
        topic = m.group("topic")
        hook = body.split(".")[0][:90] or "opens directly on the topic"
        has_number = any(ch.isdigit() for ch in body)
        results.append(
            {
                "index": idx,
                "hook": hook,
                "structure": "short intro, then a scannable body and a closing prompt",
                "emotional_trigger": "curiosity" if "?" in body else None,
                "data_usage": "cites a concrete figure" if has_number else None,
                "visual_format": f"{fmt} carries the message",
                "cta_assessment": "clear, low-friction ask",
                "audience_relevance": f"squarely on {topic} for the target buyer",
                "timing_note": None,
                "length_note": "long enough to add value, short enough to finish",
                "storytelling": (
                    "frames the point around a customer moment"
                    if "customer" in body.lower()
                    else None
                ),
                "summary": f"Strong {fmt} hook on {topic} with a clean CTA",
            }
        )
    return WhyItWorkedBatch.model_validate({"results": results}).model_dump()


def register_mapping_fakes(fake_llm: FakeLLM) -> None:
    fake_llm.register(PositioningSummary, _positioning_responder)
    fake_llm.register(WhyItWorkedBatch, _why_it_worked_responder)
