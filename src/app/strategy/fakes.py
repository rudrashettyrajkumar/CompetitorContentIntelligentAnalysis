"""Deterministic FakeLLM responders for the EPIC-06 strategy prompts.

The normal offline strategy path is ``FakeStrategyAgent`` (no LLM at all). These
responders exist so (a) the originality guard's LLM layer still runs offline, and (b) the
prompt packs and the ``DeepStrategyAgent`` fallback have a scripted backend under
``make test``.
"""

from __future__ import annotations

import re

from app.core.model_router import FakeLLM
from app.schemas.strategy import (
    ContentCalendar,
    ContentOpportunityList,
    ContentStrategy,
    OriginalityVerdict,
    RegeneratedField,
)

_CAND_RE = re.compile(r"^\[(\d+)\]\s+(.*)$", re.MULTILINE)
_EXCERPT_RE = re.compile(r"^-\s+(.*)$", re.MULTILINE)
_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _norm(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower()).split()


def _shares_run(a: list[str], b: list[str], k: int = 4) -> bool:
    if len(a) < k:
        return False
    b_grams = {tuple(b[i : i + k]) for i in range(len(b) - k + 1)}
    return any(tuple(a[i : i + k]) in b_grams for i in range(len(a) - k + 1))


def _originality_responder(_system: str, user: str) -> dict:
    body = user.split("Candidates:", 1)
    excerpt_block = body[0]
    cand_block = body[1] if len(body) > 1 else ""
    excerpts = [_norm(e) for e in _EXCERPT_RE.findall(excerpt_block)]
    results = []
    for idx, text in _CAND_RE.findall(cand_block):
        toks = _norm(text)
        rewrite = any(_shares_run(toks, ex) for ex in excerpts)
        results.append(
            {
                "index": int(idx),
                "is_rewrite": rewrite,
                "reason": "shares a 4+ word run with a competitor excerpt" if rewrite else "",
            }
        )
    return OriginalityVerdict.model_validate({"results": results}).model_dump()


def _regenerated_field_responder(system: str, user: str) -> dict:
    topic_match = re.search(r'about\s+"([^"]+)"', system)
    topic = topic_match.group(1) if topic_match else "the subject"
    rejected = re.search(r"Rejected \w+: (.+)", user)
    seed = (rejected.group(1)[:20] if rejected else "x").strip()
    return RegeneratedField(
        text=f"A distinct, first-person operator angle on {topic} (rev {abs(hash(seed)) % 997})."
    ).model_dump()


def _content_strategy_responder(_system: str, _user: str) -> dict:
    names = ["Operator Proof", "Category White Space", "Measurable Automation", "Contrarian Takes"]
    return ContentStrategy(
        pillars=[
            {
                "name": n,
                "description": f"Content built around {n.lower()}.",
                "rationale": "cites a competitor white space / signal from the cross insights",
            }
            for n in names
        ],
        content_mix={n: 25.0 for n in names},
        recommended_formats=[
            {"format": "thought_leadership", "share": 40.0, "rationale": "our voice"},
            {"format": "carousel", "share": 35.0, "rationale": "under-served, high engagement"},
            {"format": "case_study", "share": 25.0, "rationale": "proof"},
        ],
        posting_cadence="3 posts per week on Tue, Wed and Thu",
        engagement_windows=["Tue", "Wed", "Thu"],
    ).model_dump()


def _opportunities_responder(_system: str, _user: str) -> dict:
    opps = []
    for i in range(8):
        opps.append(
            {
                "topic": ["automation", "data_analytics", "digital_transformation"][i % 3],
                "pillar": "Operator Proof",
                "competitor_signal": "medium",
                "competition_level": "medium",
                "engagement_potential": "medium",
                "recommended_format": "thought_leadership",
                "target_audience": "RevOps leaders at mid-market B2B companies",
                "hook": f"Original hook number {i} that resembles no competitor post at all",
                "angle": f"A first-person operator angle number {i}",
                "key_message": f"Concrete, measurable message number {i} unique to us",
                "structure": ["Hook", "Mistake", "Our approach", "Numbers", "CTA"],
                "cta": "learn_more",
                "keywords": ["automation", "rev ops"],
                "hashtags": ["automation"],
            }
        )
    return ContentOpportunityList.model_validate({"opportunities": opps}).model_dump()


def _calendar_responder(_system: str, _user: str) -> dict:
    entries = []
    for day in range(1, 31):
        wd = _WEEKDAYS[(day - 1) % 7]
        if wd not in ("Tue", "Wed", "Thu"):
            continue
        entries.append(
            {
                "day": day,
                "weekday": wd,
                "pillar": [
                    "Operator Proof",
                    "Category White Space",
                    "Measurable Automation",
                    "Contrarian Takes",
                ][len(entries) % 4],
                "topic": "automation",
                "format": "thought_leadership",
                "objective": "advance the pillar",
                "cta": "learn_more",
                "opportunity_ref": len(entries) % 8,
            }
        )
    return ContentCalendar.model_validate(
        {"entries": entries, "cadence_note": "3x/week Tue-Thu"}
    ).model_dump()


def register_strategy_fakes(fake_llm: FakeLLM) -> None:
    fake_llm.register(OriginalityVerdict, _originality_responder)
    fake_llm.register(RegeneratedField, _regenerated_field_responder)
    fake_llm.register(ContentStrategy, _content_strategy_responder)
    fake_llm.register(ContentOpportunityList, _opportunities_responder)
    fake_llm.register(ContentCalendar, _calendar_responder)
