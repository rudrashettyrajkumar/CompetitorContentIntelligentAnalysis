"""Deterministic FakeLLM responders for the four classification prompts.

Registered on the router's ``FakeLLM`` so ``make test`` and ``make demo`` produce
plausible, schema-valid classifications for mock/sample content with zero quota spend.
Each responder parses the rendered ``[index] media=... :: content`` lines back out of the
user prompt and applies light keyword heuristics. Keyword output is deliberately sparse
so the TF-IDF cross-check has terms to merge.
"""

from __future__ import annotations

import re

from app.core.model_router import FakeLLM
from app.schemas.intelligence import (
    CtaClassification,
    FormatClassification,
    KeywordClassification,
    TopicClassification,
)

_LINE_RE = re.compile(r"^\[(\d+)\]\s+media=(\S+)\s+::\s+(.*)$", re.MULTILINE)

_MEDIA_TO_FORMAT = {
    "image": "static_image",
    "carousel": "carousel",
    "video": "video",
    "text": "text_only",
    "poll": "poll",
    "article": "blog_article",
    "document": "whitepaper_report",
    "unknown": "text_only",
}

_TOPIC_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("ai ", "a.i.", "artificial intelligence", "automation", "machine learning"), "ai"),
    (("cybersecurity", "security", "threat", "zero trust"), "cybersecurity"),
    (("cloud", "kubernetes", "serverless"), "cloud"),
    (("data", "analytics", "dashboard"), "data_analytics"),
    (("marketing", "campaign", "seo", "demand gen"), "digital_marketing"),
    (("digital transformation", "modernization", "legacy"), "digital_transformation"),
    (("customer", "cx", "experience", "retention", "success"), "customer_experience"),
    (("manufacturing", "industry 4", "iiot", "factory"), "industry_4_0"),
]

_CTA_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("download", "get the guide", "grab our"), "download"),
    (("register", "sign up", "save your seat", "rsvp"), "register"),
    (("book a demo", "request a demo", "see it in action"), "demo"),
    (("contact us", "talk to", "reach out"), "contact"),
    (("follow us", "follow along"), "follow"),
    (("your take", "want your", "tell us", "comment below", "what do you think"), "comment"),
    (("watch", "swipe through", "read more", "new on our blog", "learn how"), "learn_more"),
]


def _parse_posts(user: str) -> list[dict[str, object]]:
    return [
        {"index": int(idx), "media_type": media, "content": content}
        for idx, media, content in _LINE_RE.findall(user)
    ]


def _guess_format(post: dict[str, object]) -> str:
    content = str(post["content"]).lower()
    if any(k in content for k in ("we're hiring", "we are hiring", "join our team", "hiring &")):
        return "hiring"
    if "case study" in content or "case-study" in content:
        return "case_study"
    if "customer story" in content or "customer success" in content:
        return "customer_story"
    if "webinar" in content or "events & webinars" in content or " event" in content:
        return "event_webinar"
    if "company culture" in content or "life at" in content or "behind the scenes" in content:
        return "employer_branding"
    if "quick thought" in content or "thought leadership" in content:
        return "thought_leadership"
    if "product launch" in content or "new release" in content or "introducing" in content:
        return "product_promotion"
    if "research" in content or "survey" in content or "report finds" in content:
        return "research_data"
    return _MEDIA_TO_FORMAT.get(str(post["media_type"]), "text_only")


def _guess_topic(content: str) -> str:
    low = f" {content.lower()} "
    for keys, topic in _TOPIC_KEYWORDS:
        if any(k in low for k in keys):
            return topic
    return "other"


def _sub_topic(content: str) -> str | None:
    head = content.split(".", 1)[0].strip()
    return head[:60] or None


def _guess_cta(content: str) -> tuple[str, str | None]:
    low = content.lower()
    for keys, cta in _CTA_KEYWORDS:
        for key in keys:
            if key in low:
                return cta, key
    return "none", None


def _guess_keywords(content: str) -> list[dict[str, str]]:
    tags: list[dict[str, str]] = []
    topic = _guess_topic(content)
    if topic != "other":
        tags.append({"term": topic.replace("_", " "), "category": "industry_term"})
    if "quarter" in content.lower():
        tags.append({"term": "this quarter", "category": "frequent"})
    if not tags:
        first = re.sub(r"[^a-zA-Z ]", " ", content).split()
        tags.append({"term": (first[0] if first else "update"), "category": "frequent"})
    return tags


def _format_responder(_system: str, user: str) -> dict:
    return {
        "results": [{"index": p["index"], "format": _guess_format(p)} for p in _parse_posts(user)]
    }


def _topic_responder(_system: str, user: str) -> dict:
    posts = _parse_posts(user)
    return {
        "results": [
            {
                "index": p["index"],
                "topic": _guess_topic(str(p["content"])),
                "sub_topic": _sub_topic(str(p["content"])),
            }
            for p in posts
        ]
    }


def _cta_responder(_system: str, user: str) -> dict:
    results = []
    for p in _parse_posts(user):
        cta, text = _guess_cta(str(p["content"]))
        results.append({"index": p["index"], "cta": cta, "cta_text": text})
    return {"results": results}


def _keyword_responder(_system: str, user: str) -> dict:
    return {
        "results": [
            {"index": p["index"], "keywords": _guess_keywords(str(p["content"]))}
            for p in _parse_posts(user)
        ]
    }


def register_classification_fakes(fake_llm: FakeLLM) -> None:
    fake_llm.register(FormatClassification, _format_responder)
    fake_llm.register(TopicClassification, _topic_responder)
    fake_llm.register(CtaClassification, _cta_responder)
    fake_llm.register(KeywordClassification, _keyword_responder)
