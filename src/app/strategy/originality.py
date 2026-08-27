"""Originality guard for generated content opportunities (EPIC-06, solution-design §8).

Every generated ``hook`` / ``angle`` / ``key_message`` is checked against all competitor
post texts in two layers:

1. **Deterministic** — normalized n-gram overlap ratio (n and threshold from
   ``config: strategy``). Above the threshold ⇒ reject. This alone catches copy-paste and
   light paraphrase.
2. **LLM judge** — ``prompts/strategy/originality_check`` (fast tier, batched): "is this a
   rewrite of any of these excerpts?" ⇒ reject on yes.

A rejected field is regenerated once (the rejection reason is fed back to the caller's
``regenerate`` callback). If the regenerated text still fails either layer, the whole
opportunity is dropped and logged. Every decision is recorded as an ``OriginalityCheck``
and kept with the strategy bundle.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.core.logging import get_logger
from app.core.model_router import LLMError, ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.schemas.strategy import ContentOpportunity, OriginalityCheck, OriginalityVerdict

log = get_logger(__name__)

CHECK_PROMPT = "originality_check"
GUARDED_FIELDS = ("hook", "angle", "key_message")

RegenFn = Callable[[int, str, str], str | None]


def _normalize(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).split()


def _ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


@dataclass
class OverlapIndex:
    """Precomputed competitor n-gram corpus for the deterministic check."""

    n: int
    grams: set[tuple[str, ...]]
    short_grams: set[tuple[str, ...]]  # every k<=n gram, for texts shorter than n tokens

    @classmethod
    def build(cls, texts: list[str], n: int) -> OverlapIndex:
        grams: set[tuple[str, ...]] = set()
        short: set[tuple[str, ...]] = set()
        for text in texts:
            toks = _normalize(text)
            grams |= _ngrams(toks, n)
            for k in range(2, n):
                short |= _ngrams(toks, k)
        return cls(n=n, grams=grams, short_grams=short)

    def overlap_ratio(self, text: str) -> float:
        toks = _normalize(text)
        cand = _ngrams(toks, self.n)
        if not cand:
            return 0.0
        corpus = self.grams if len(toks) >= self.n else (self.grams | self.short_grams)
        hits = sum(1 for g in cand if g in corpus)
        return hits / len(cand)


def _llm_is_rewrite(
    texts_by_index: dict[int, str],
    excerpts: list[str],
    *,
    router: ModelRouter,
    registry: PromptRegistry,
) -> dict[int, tuple[bool, str]]:
    if not texts_by_index:
        return {}
    rendered = registry.render(
        CHECK_PROMPT,
        candidates=[{"index": i, "text": t} for i, t in sorted(texts_by_index.items())],
        excerpts=excerpts[:40],
    )
    try:
        result = router.invoke(
            tier=rendered.meta.model_tier,
            system=rendered.system,
            user=rendered.user,
            schema=rendered.schema,
            temperature=rendered.meta.temperature,
            prompt_name=rendered.meta.name,
            prompt_version=rendered.meta.version,
        )
    except LLMError as exc:
        log.warning("originality_llm_check_failed", error=str(exc))
        return {}
    if not isinstance(result, OriginalityVerdict):
        return {}
    return {r.index: (r.is_rewrite, r.reason) for r in result.results}


@dataclass
class GuardResult:
    opportunities: list[ContentOpportunity]
    checks: list[OriginalityCheck]


def run_originality_guard(
    opportunities: list[ContentOpportunity],
    competitor_texts: list[str],
    *,
    router: ModelRouter,
    registry: PromptRegistry,
    cfg: dict,
    regenerate: RegenFn | None = None,
) -> GuardResult:
    n = int(cfg.get("originality_ngram", 6))
    max_overlap = float(cfg.get("originality_max_overlap", 0.30))
    index = OverlapIndex.build(competitor_texts, n)
    excerpts = [t[:280] for t in competitor_texts[:60]]

    checks: list[OriginalityCheck] = []
    # (opp_index, field) -> current text
    pending: dict[tuple[int, str], str] = {}
    for oi, opp in enumerate(opportunities):
        for field in GUARDED_FIELDS:
            pending[(oi, field)] = getattr(opp, field)

    # -- layer 1: deterministic n-gram overlap -----------------------------
    rejected: dict[tuple[int, str], tuple[str, str, float]] = {}
    survivors: dict[tuple[int, str], str] = {}
    for key, text in pending.items():
        ratio = index.overlap_ratio(text)
        if ratio > max_overlap:
            rejected[key] = ("rejected_ngram", f"{ratio:.0%} n-gram overlap", ratio)
        else:
            survivors[key] = text

    # -- layer 2: LLM similarity judge on the survivors -------------------
    flat = list(survivors.items())
    verdicts = _llm_is_rewrite(
        {i: text for i, (_key, text) in enumerate(flat)},
        excerpts,
        router=router,
        registry=registry,
    )
    for i, (key, _text) in enumerate(flat):
        is_rewrite, reason = verdicts.get(i, (False, ""))
        if is_rewrite:
            rejected[key] = ("rejected_llm", reason or "LLM judged this a rewrite", None)

    # -- regeneration (once) then drop -----------------------------------
    drop_opps: set[int] = set()
    regen_attempts = int(cfg.get("originality_regen_attempts", 1))
    for (oi, field), (verdict, detail, ratio) in sorted(rejected.items()):
        original = pending[(oi, field)]
        new_text: str | None = None
        for _ in range(max(0, regen_attempts)):
            if regenerate is None:
                break
            candidate = regenerate(oi, field, detail)
            if not candidate:
                break
            r2 = index.overlap_ratio(candidate)
            llm2 = _llm_is_rewrite({0: candidate}, excerpts, router=router, registry=registry)
            if r2 <= max_overlap and not llm2.get(0, (False, ""))[0]:
                new_text = candidate
                break
        if new_text is not None:
            setattr(opportunities[oi], field, new_text)
            checks.append(
                OriginalityCheck(
                    field=field,
                    opportunity_index=oi,
                    text=new_text,
                    verdict="regenerated",
                    detail=f"replaced (was: {verdict} — {detail})",
                    overlap_ratio=ratio,
                )
            )
        else:
            drop_opps.add(oi)
            checks.append(
                OriginalityCheck(
                    field=field,
                    opportunity_index=oi,
                    text=original,
                    verdict="dropped",
                    detail=detail,
                    overlap_ratio=ratio,
                )
            )
            log.warning(
                "opportunity_dropped_originality", opportunity=oi, field=field, reason=detail
            )

    kept = [opp for oi, opp in enumerate(opportunities) if oi not in drop_opps]
    for oi, opp in enumerate(opportunities):
        if oi in drop_opps:
            continue
        for field in GUARDED_FIELDS:
            if (oi, field) not in rejected:
                checks.append(
                    OriginalityCheck(
                        field=field,
                        opportunity_index=oi,
                        text=getattr(opp, field),
                        verdict="ok",
                    )
                )
    checks.sort(key=lambda c: (c.opportunity_index, c.field))
    log.info(
        "originality_guard_done",
        opportunities_in=len(opportunities),
        kept=len(kept),
        dropped=len(drop_opps),
        regenerated=sum(1 for c in checks if c.verdict == "regenerated"),
    )
    return GuardResult(opportunities=kept, checks=checks)
