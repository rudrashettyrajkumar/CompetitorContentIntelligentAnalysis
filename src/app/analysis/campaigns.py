"""Campaign detection (brief step 7) — a deep agent proposes multi-post campaigns; Python
decides what is real.

Flow: ``build_campaign_inputs`` turns the run's classified posts into per-competitor JSON
files → a :class:`CampaignAgent` (deepagents in prod, a scripted stub offline) clusters
them into :class:`CampaignRecord` proposals → ``validate_campaigns`` drops anything that
references an unknown URL, mixes competitors, misses the ``min_posts`` floor, or spills
past the ``window_days`` span → ``resolve_overlaps`` makes campaigns disjoint, keeping the
higher-engagement one when two claim the same post. Aggregates are always recomputed from
the member posts, never trusted from the agent.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.config.settings import PROMPTS_DIR, AppConfig, get_app_config
from app.core.logging import get_logger
from app.core.model_router import LLMError, ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.db.repos import AnalysisRepo, CampaignRepo, RunRepo
from app.schemas.analysis import CampaignClustering, CampaignRecord, ValidatedCampaign

log = get_logger(__name__)

PROMPT = "campaign_cluster"


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RunPostRef:
    post_id: int
    competitor_id: int
    competitor_name: str
    url: str
    posted_at: datetime
    format: str | None
    topic: str | None
    sub_topic: str | None
    cta: str | None
    score: float
    keywords: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)

    def as_prompt_dict(self, index: int) -> dict:
        return {
            "index": index,
            "url": self.url,
            "date": self.posted_at.date().isoformat(),
            "format": self.format or "unknown",
            "topic": self.topic or "other",
            "sub_topic": self.sub_topic or "",
            "cta": self.cta or "none",
            "score": round(self.score, 1),
            "keywords": list(self.keywords),
            "hashtags": list(self.hashtags),
        }


@dataclass
class CampaignInputs:
    refs: list[RunPostRef]

    @property
    def posts_by_url(self) -> dict[str, RunPostRef]:
        return {ref.url: ref for ref in self.refs}

    @property
    def refs_by_id(self) -> dict[int, RunPostRef]:
        return {ref.post_id: ref for ref in self.refs}

    @property
    def competitor_names(self) -> dict[int, str]:
        return {ref.competitor_id: ref.competitor_name for ref in self.refs}

    def by_competitor(self) -> dict[int, list[RunPostRef]]:
        grouped: dict[int, list[RunPostRef]] = defaultdict(list)
        for ref in sorted(self.refs, key=lambda r: (r.competitor_id, r.posted_at)):
            grouped[ref.competitor_id].append(ref)
        return grouped

    def files(self) -> dict[str, str]:
        """Virtual-FS payload for the deep agent: one JSON file per competitor."""
        out: dict[str, str] = {}
        for competitor_id, refs in self.by_competitor().items():
            payload = [ref.as_prompt_dict(i) for i, ref in enumerate(refs)]
            out[f"competitor_{competitor_id}.json"] = json.dumps(payload, indent=2)
        return out


def build_campaign_inputs(session: Session, run_id: int) -> CampaignInputs:
    rows = AnalysisRepo(session).scored_rows_for_run(run_id)
    refs = [
        RunPostRef(
            post_id=row.post_id,
            competitor_id=row.competitor_id,
            competitor_name=row.competitor_name,
            url=row.url,
            posted_at=row.posted_at,
            format=row.format,
            topic=row.topic,
            sub_topic=row.sub_topic,
            cta=row.cta,
            score=row.engagement_score or 0.0,
            keywords=[k.get("term", "") for k in (row.keywords or []) if k.get("term")],
            hashtags=list(row.hashtags or []),
        )
        for row in rows
    ]
    return CampaignInputs(refs=refs)


# --------------------------------------------------------------------------- #
# agents
# --------------------------------------------------------------------------- #
class FakeCampaignAgent:
    """Deterministic offline stub. Buckets each competitor's posts by classified topic and
    slices every bucket into ``window_days`` windows; a window with ``>= min_posts`` posts
    becomes a campaign. Enough structure for tests/demo to exercise the whole pipeline."""

    def detect(
        self, inputs: CampaignInputs, *, window_days: int, min_posts: int
    ) -> list[CampaignRecord]:
        records: list[CampaignRecord] = []
        for refs in inputs.by_competitor().values():
            by_topic: dict[str, list[RunPostRef]] = defaultdict(list)
            for ref in refs:
                by_topic[ref.topic or "other"].append(ref)
            for topic, topic_refs in by_topic.items():
                topic_refs.sort(key=lambda r: r.posted_at)
                for window in _slice_windows(topic_refs, window_days, min_posts):
                    records.append(_record_from_refs(topic, window))
        return records


class DeepCampaignAgent:
    """Production path: a deepagents run per competitor over its JSON file, with a single
    reasoning call as the fallback when the agent errors. Never used under fake mode."""

    def __init__(
        self,
        router: ModelRouter,
        registry: PromptRegistry | None = None,
    ) -> None:
        self.router = router
        self.registry = registry or PromptRegistry(PROMPTS_DIR)

    def detect(
        self, inputs: CampaignInputs, *, window_days: int, min_posts: int
    ) -> list[CampaignRecord]:
        records: list[CampaignRecord] = []
        files = inputs.files()
        for competitor_id, refs in inputs.by_competitor().items():
            name = inputs.competitor_names.get(competitor_id, f"competitor {competitor_id}")
            rendered = self.registry.render(
                PROMPT,
                competitor=name,
                posts=[ref.as_prompt_dict(i) for i, ref in enumerate(refs)],
                min_posts=min_posts,
                window_days=window_days,
            )
            clustering = self._invoke(rendered, files.get(f"competitor_{competitor_id}.json", "[]"))
            records.extend(clustering.campaigns)
        return records

    def _invoke(self, rendered, file_content: str) -> CampaignClustering:
        try:
            text = self._run_deep_agent(rendered, file_content)
            from app.core.model_router import extract_json

            return CampaignClustering.model_validate_json(extract_json(text))
        except Exception as exc:  # noqa: BLE001 — deep agent is best-effort; router call is the net
            log.warning("deep_agent_fallback_single_call", prompt=PROMPT, error=str(exc))
            return self.router.invoke(
                tier=rendered.meta.model_tier,
                system=rendered.system,
                user=rendered.user,
                schema=rendered.schema,
                temperature=rendered.meta.temperature,
                prompt_name=rendered.meta.name,
                prompt_version=rendered.meta.version,
            )

    def _run_deep_agent(self, rendered, file_content: str) -> str:
        from deepagents import create_deep_agent

        model = self.router.chat_model_for(
            rendered.meta.model_tier, temperature=rendered.meta.temperature
        )
        agent = create_deep_agent(tools=[], system_prompt=rendered.system, model=model)
        state = agent.invoke(
            {
                "messages": [{"role": "user", "content": rendered.user}],
                "files": {"posts.json": file_content},
            }
        )
        messages = state.get("messages", []) if isinstance(state, dict) else []
        if not messages:
            raise LLMError("deep agent returned no messages")
        last = messages[-1]
        return getattr(last, "content", None) or last.get("content", "")


# --------------------------------------------------------------------------- #
# clustering helpers (shared by the fake agent + finalisation)
# --------------------------------------------------------------------------- #
def _slice_windows(
    refs: list[RunPostRef], window_days: int, min_posts: int
) -> list[list[RunPostRef]]:
    """Greedy left-anchored windows over date-sorted refs; only ``>= min_posts`` kept."""
    windows: list[list[RunPostRef]] = []
    pending = list(refs)
    while pending:
        anchor = pending[0].posted_at
        window = [r for r in pending if (r.posted_at - anchor).days <= window_days]
        pending = pending[len(window) :]
        if len(window) >= min_posts:
            windows.append(window)
    return windows


def _dedupe(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        if value:
            seen.setdefault(value, None)
    return list(seen)


def _record_from_refs(topic: str, refs: list[RunPostRef]) -> CampaignRecord:
    refs = sorted(refs, key=lambda r: r.posted_at)
    title = topic.replace("_", " ").title()
    sub = next((r.sub_topic for r in refs if r.sub_topic), None)
    ctas = [r.cta for r in refs if r.cta and r.cta != "none"]
    dominant_cta = max(set(ctas), key=ctas.count) if ctas else None
    top = max(refs, key=lambda r: r.score)
    total = sum(r.score for r in refs)
    return CampaignRecord(
        name=f"{title}: {sub}" if sub else f"{title} campaign",
        theme=sub or title,
        objective=None,
        post_urls=[r.url for r in refs],
        start_date=refs[0].posted_at.date(),
        end_date=refs[-1].posted_at.date(),
        formats=_dedupe([r.format or "" for r in refs]),
        keywords=_dedupe([kw for r in refs for kw in r.keywords])[:12],
        hashtags=_dedupe([tag for r in refs for tag in r.hashtags])[:12],
        dominant_cta=dominant_cta,
        inferred_target_audience=None,
        total_engagement=total,
        top_post_url=top.url,
        performance_summary=(
            f"{len(refs)} posts, total engagement {total:.0f}; top post {top.url}"
        ),
    )


def _finalize(candidate: CampaignRecord, refs: list[RunPostRef]) -> ValidatedCampaign:
    """Build a ValidatedCampaign with every aggregate recomputed from the member posts."""
    refs = sorted(refs, key=lambda r: r.posted_at)
    top = max(refs, key=lambda r: r.score)
    total = sum(r.score for r in refs)
    keywords = _dedupe([kw for r in refs for kw in r.keywords] + list(candidate.keywords))[:12]
    hashtags = _dedupe([t for r in refs for t in r.hashtags] + list(candidate.hashtags))[:12]
    return ValidatedCampaign(
        competitor_id=refs[0].competitor_id,
        name=candidate.name.strip() or f"{(candidate.theme or 'Campaign').strip()}",
        theme=(candidate.theme or "").strip() or candidate.name.strip(),
        objective=candidate.objective,
        post_ids=sorted(r.post_id for r in refs),
        post_urls=[r.url for r in refs],
        start_date=refs[0].posted_at,
        end_date=refs[-1].posted_at,
        formats=_dedupe([r.format or "" for r in refs]),
        keywords=keywords,
        hashtags=hashtags,
        dominant_cta=candidate.dominant_cta,
        target_audience=candidate.inferred_target_audience,
        total_engagement=total,
        top_post_id=top.post_id,
        top_post_url=top.url,
        performance_summary=candidate.performance_summary
        or f"{len(refs)} posts, total engagement {total:.0f}",
    )


# --------------------------------------------------------------------------- #
# validation + overlap resolution
# --------------------------------------------------------------------------- #
def validate_campaigns(
    candidates: list[CampaignRecord],
    *,
    posts_by_url: dict[str, RunPostRef],
    window_days: int,
    min_posts: int,
) -> tuple[list[ValidatedCampaign], list[tuple[str, str]]]:
    """Return ``(validated, dropped)`` where ``dropped`` is ``[(campaign_name, reason)]``."""
    validated: list[ValidatedCampaign] = []
    dropped: list[tuple[str, str]] = []

    for candidate in candidates:
        name = candidate.name or "(unnamed)"
        urls = _dedupe(candidate.post_urls)

        unknown = [u for u in urls if u not in posts_by_url]
        if unknown:
            reason = f"references unknown post url(s): {unknown[:3]}"
            dropped.append((name, reason))
            log.warning("campaign_dropped", campaign=name, reason=reason)
            continue

        refs = [posts_by_url[u] for u in urls]
        competitors = {r.competitor_id for r in refs}
        if len(competitors) > 1:
            reason = f"spans {len(competitors)} competitors"
            dropped.append((name, reason))
            log.warning("campaign_dropped", campaign=name, reason=reason)
            continue

        if len(refs) < min_posts:
            reason = f"only {len(refs)} posts (< {min_posts})"
            dropped.append((name, reason))
            log.warning("campaign_dropped", campaign=name, reason=reason)
            continue

        if (
            candidate.start_date
            and candidate.end_date
            and candidate.start_date > candidate.end_date
        ):
            reason = "start_date after end_date"
            dropped.append((name, reason))
            log.warning("campaign_dropped", campaign=name, reason=reason)
            continue

        span_days = (max(r.posted_at for r in refs) - min(r.posted_at for r in refs)).days
        if span_days > window_days:
            reason = f"posts span {span_days}d (> window {window_days}d)"
            dropped.append((name, reason))
            log.warning("campaign_dropped", campaign=name, reason=reason)
            continue

        validated.append(_finalize(candidate, refs))

    return validated, dropped


def resolve_overlaps(
    campaigns: list[ValidatedCampaign],
    *,
    refs_by_id: dict[int, RunPostRef],
    min_posts: int,
) -> tuple[list[ValidatedCampaign], list[tuple[str, str]]]:
    """Make campaigns post-disjoint. Higher total engagement wins a contested post; a
    campaign that drops below ``min_posts`` after losing posts is discarded."""
    ordered = sorted(campaigns, key=lambda c: (-c.total_engagement, c.name))
    claimed: set[int] = set()
    kept: list[ValidatedCampaign] = []
    conflicts: list[tuple[str, str]] = []

    for campaign in ordered:
        overlap = [pid for pid in campaign.post_ids if pid in claimed]
        remaining = [pid for pid in campaign.post_ids if pid not in claimed]
        if overlap:
            conflicts.append(
                (campaign.name, f"ceded {len(overlap)} post(s) to a stronger campaign")
            )
            log.info("campaign_overlap", campaign=campaign.name, ceded=len(overlap))
        if len(remaining) < min_posts:
            conflicts.append((campaign.name, f"dropped — only {len(remaining)} unclaimed post(s)"))
            log.warning("campaign_dropped", campaign=campaign.name, reason="lost posts to overlap")
            continue
        if overlap:
            campaign = _refinalize(campaign, [refs_by_id[pid] for pid in remaining])
        claimed.update(campaign.post_ids)
        kept.append(campaign)

    return kept, conflicts


def _refinalize(campaign: ValidatedCampaign, refs: list[RunPostRef]) -> ValidatedCampaign:
    refs = sorted(refs, key=lambda r: r.posted_at)
    top = max(refs, key=lambda r: r.score)
    total = sum(r.score for r in refs)
    return campaign.model_copy(
        update=dict(
            post_ids=sorted(r.post_id for r in refs),
            post_urls=[r.url for r in refs],
            start_date=refs[0].posted_at,
            end_date=refs[-1].posted_at,
            formats=_dedupe([r.format or "" for r in refs]),
            total_engagement=total,
            top_post_id=top.post_id,
            top_post_url=top.url,
            performance_summary=f"{len(refs)} posts, total engagement {total:.0f}",
        )
    )


# --------------------------------------------------------------------------- #
# stage entrypoint
# --------------------------------------------------------------------------- #
@dataclass
class CampaignDetectionResult:
    run_id: int
    proposed: int
    validated: int
    persisted: int
    dropped: list[tuple[str, str]] = field(default_factory=list)
    conflicts: list[tuple[str, str]] = field(default_factory=list)


def detect_campaigns_for_run(
    session: Session,
    *,
    run_id: int,
    router: ModelRouter,
    registry: PromptRegistry,
    app_config: AppConfig | None = None,
    agent: object | None = None,
    set_stage: bool = True,
) -> CampaignDetectionResult:
    app_config = app_config or get_app_config()
    cfg = app_config.campaigns or {}
    window_days = int(cfg.get("window_days", 30))
    min_posts = int(cfg.get("min_posts", 3))

    if set_stage:
        RunRepo(session).set_stage(run_id, "campaigns")

    inputs = build_campaign_inputs(session, run_id)
    if agent is None:
        agent = FakeCampaignAgent() if router.use_fake else DeepCampaignAgent(router, registry)

    proposed = agent.detect(inputs, window_days=window_days, min_posts=min_posts)
    validated, dropped = validate_campaigns(
        proposed,
        posts_by_url=inputs.posts_by_url,
        window_days=window_days,
        min_posts=min_posts,
    )
    resolved, conflicts = resolve_overlaps(
        validated, refs_by_id=inputs.refs_by_id, min_posts=min_posts
    )
    rows = CampaignRepo(session).replace_for_run(run_id, resolved)
    session.commit()

    log.info(
        "campaigns_detected",
        run_id=run_id,
        proposed=len(proposed),
        validated=len(validated),
        persisted=len(rows),
        dropped=len(dropped),
    )
    return CampaignDetectionResult(
        run_id=run_id,
        proposed=len(proposed),
        validated=len(validated),
        persisted=len(rows),
        dropped=dropped,
        conflicts=conflicts,
    )
