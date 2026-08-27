"""Period-over-period diff (EPIC-08).

Compares a completed run with the previous completed run and reports what actually
moved: post volume, campaigns opened/closed, keywords emerging/fading, topic and format
engagement shifts, and per-competitor profile changes. Pure computation — thresholds in
``config/app.yaml: loop``. ``strategy_refresh_recommended`` flips when the count of
material changes reaches ``loop.refresh_shift_threshold``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config.settings import AppConfig, get_app_config
from app.core.logging import get_logger
from app.db.repos import AnalysisRepo, CampaignRepo, RunRepo, StrategyProfileRepo
from app.schemas.loop import (
    FormatShift,
    KeywordDelta,
    PeriodDiff,
    ProfileChange,
    TopicShift,
)

log = get_logger(__name__)


@dataclass
class _RunAgg:
    post_count: int
    keyword_freq: Counter
    topic_avg: dict[str, float]
    topic_n: dict[str, int]
    format_avg: dict[str, float]
    format_n: dict[str, int]
    campaigns: set
    profiles: dict[int, dict]  # competitor_id -> {name, cadence, best_format, dominant_mix}


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _aggregate(session: Session, run_id: int) -> _RunAgg:
    rows = AnalysisRepo(session).scored_rows_for_run(run_id)
    kw: Counter = Counter()
    topic_scores: dict[str, list[float]] = defaultdict(list)
    format_scores: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        for k in r.keywords or []:
            if k.get("term"):
                kw[k["term"].strip().lower()] += 1
        if r.topic:
            topic_scores[r.topic].append(r.engagement_score or 0.0)
        if r.format:
            format_scores[r.format].append(r.engagement_score or 0.0)

    profiles: dict[int, dict] = {}
    for p in StrategyProfileRepo(session).list_for_run(run_id):
        mix = p.content_mix or {}
        dominant = max(mix, key=mix.get) if mix else ""
        profiles[p.competitor_id] = {
            "name": _competitor_name(session, p.competitor_id),
            "cadence": p.posting_frequency_per_week or 0.0,
            "best_format": p.best_format or "",
            "dominant_mix": dominant,
        }

    return _RunAgg(
        post_count=len(rows),
        keyword_freq=kw,
        topic_avg={t: _mean(s) for t, s in topic_scores.items()},
        topic_n={t: len(s) for t, s in topic_scores.items()},
        format_avg={f: _mean(s) for f, s in format_scores.items()},
        format_n={f: len(s) for f, s in format_scores.items()},
        campaigns={c.name for c in CampaignRepo(session).list_for_run(run_id)},
        profiles=profiles,
    )


def _competitor_name(session: Session, competitor_id: int) -> str:
    from app.db.models import Competitor

    c = session.get(Competitor, competitor_id)
    return c.name if c else f"competitor {competitor_id}"


def _keyword_deltas(
    base: Counter, cur: Counter, *, growth: float, min_count: int
) -> tuple[list[KeywordDelta], list[KeywordDelta]]:
    emerging, fading = [], []
    for term in set(base) | set(cur):
        b, a = base.get(term, 0), cur.get(term, 0)
        if a >= min_count and a / max(b, 1) >= growth and a > b:
            emerging.append(
                KeywordDelta(term=term, before=b, after=a, growth=round(a / max(b, 1), 2))
            )
        elif b >= min_count and b / max(a, 1) >= growth and b > a:
            fading.append(
                KeywordDelta(term=term, before=b, after=a, growth=round(b / max(a, 1), 2))
            )
    emerging.sort(key=lambda d: (-d.growth, d.term))
    fading.sort(key=lambda d: (-d.growth, d.term))
    return emerging, fading


def _group_shifts(
    base_avg: dict[str, float],
    base_n: dict[str, int],
    cur_avg: dict[str, float],
    cur_n: dict[str, int],
    *,
    pct: float,
    min_n: int,
):
    out = []
    for key in set(base_avg) & set(cur_avg):
        if base_n.get(key, 0) < min_n or cur_n.get(key, 0) < min_n:
            continue
        b, a = base_avg[key], cur_avg[key]
        delta = a - b
        rel = abs(delta) / max(abs(b), 1.0)
        if rel >= pct:
            out.append((key, round(b, 2), round(a, 2), round(delta, 2), round(rel, 3)))
    out.sort(key=lambda t: -abs(t[3]))
    return out


def _profile_changes(base: dict[int, dict], cur: dict[int, dict], *, cadence_delta: float):
    changes: list[ProfileChange] = []
    for cid in set(base) & set(cur):
        b, a = base[cid], cur[cid]
        name = a["name"]
        if abs(a["cadence"] - b["cadence"]) >= cadence_delta:
            changes.append(
                ProfileChange(
                    competitor=name,
                    field="cadence",
                    before=f"{b['cadence']:.1f}/wk",
                    after=f"{a['cadence']:.1f}/wk",
                )
            )
        if b["best_format"] and a["best_format"] and b["best_format"] != a["best_format"]:
            changes.append(
                ProfileChange(
                    competitor=name,
                    field="best_format",
                    before=b["best_format"],
                    after=a["best_format"],
                )
            )
        if b["dominant_mix"] and a["dominant_mix"] and b["dominant_mix"] != a["dominant_mix"]:
            changes.append(
                ProfileChange(
                    competitor=name,
                    field="dominant_mix",
                    before=b["dominant_mix"],
                    after=a["dominant_mix"],
                )
            )
    changes.sort(key=lambda c: (c.competitor, c.field))
    return changes


def compute_period_diff(
    session: Session,
    *,
    baseline_run_id: int,
    current_run_id: int,
    app_config: AppConfig | None = None,
) -> PeriodDiff:
    cfg = (app_config or get_app_config()).loop or {}
    growth = float(cfg.get("emerging_keyword_growth", 2.0))
    min_count = int(cfg.get("emerging_keyword_min_count", 3))
    shift_pct = float(cfg.get("topic_shift_pct", 0.25))
    min_group_n = int(cfg.get("min_posts_per_group", 3))
    cadence_delta = float(cfg.get("cadence_shift_per_week", 1.0))
    refresh_threshold = int(cfg.get("refresh_shift_threshold", 3))

    base = _aggregate(session, baseline_run_id)
    cur = _aggregate(session, current_run_id)

    emerging, fading = _keyword_deltas(
        base.keyword_freq, cur.keyword_freq, growth=growth, min_count=min_count
    )
    topic_shifts = [
        TopicShift(topic=k, before=b, after=a, delta=d, pct=p)
        for k, b, a, d, p in _group_shifts(
            base.topic_avg,
            base.topic_n,
            cur.topic_avg,
            cur.topic_n,
            pct=shift_pct,
            min_n=min_group_n,
        )
    ]
    format_shifts = [
        FormatShift(format=k, before=b, after=a, delta=d, pct=p)
        for k, b, a, d, p in _group_shifts(
            base.format_avg,
            base.format_n,
            cur.format_avg,
            cur.format_n,
            pct=shift_pct,
            min_n=min_group_n,
        )
    ]
    profile_changes = _profile_changes(base.profiles, cur.profiles, cadence_delta=cadence_delta)

    new_campaigns = sorted(cur.campaigns - base.campaigns)
    ended_campaigns = sorted(base.campaigns - cur.campaigns)
    delta_pct = (
        round((cur.post_count - base.post_count) / base.post_count * 100, 1)
        if base.post_count
        else 0.0
    )

    diff = PeriodDiff(
        baseline_run_id=baseline_run_id,
        current_run_id=current_run_id,
        new_posts=cur.post_count,
        posts_delta_pct=delta_pct,
        new_campaigns=new_campaigns,
        ended_campaigns=ended_campaigns,
        emerging_keywords=emerging,
        fading_keywords=fading,
        topic_performance_shifts=topic_shifts,
        format_shifts=format_shifts,
        profile_changes=profile_changes,
    )

    reasons: list[str] = []
    if new_campaigns:
        reasons.append(f"{len(new_campaigns)} new campaign(s): {', '.join(new_campaigns[:3])}")
    if emerging:
        reasons.append(
            f"{len(emerging)} emerging keyword(s): {', '.join(d.term for d in emerging[:3])}"
        )
    if topic_shifts:
        reasons.append(f"{len(topic_shifts)} topic engagement shift(s)")
    if format_shifts:
        reasons.append(f"{len(format_shifts)} format engagement shift(s)")
    if profile_changes:
        reasons.append(f"{len(profile_changes)} competitor profile change(s)")
    diff.strategy_refresh_recommended = diff.material_change_count() >= refresh_threshold
    diff.refresh_reasons = reasons if diff.strategy_refresh_recommended else []

    log.info(
        "period_diff_computed",
        baseline=baseline_run_id,
        current=current_run_id,
        material=diff.material_change_count(),
        refresh=diff.strategy_refresh_recommended,
    )
    return diff


@dataclass
class DiffResult:
    run_id: int
    diff: PeriodDiff | None


def diff_against_previous(
    session: Session,
    *,
    run_id: int,
    app_config: AppConfig | None = None,
) -> DiffResult:
    baseline = RunRepo(session).latest_completed(before_run_id=run_id)
    if baseline is None:
        log.info("period_diff_skipped_no_baseline", run_id=run_id)
        return DiffResult(run_id=run_id, diff=None)
    return DiffResult(
        run_id=run_id,
        diff=compute_period_diff(
            session,
            baseline_run_id=baseline.id,
            current_run_id=run_id,
            app_config=app_config,
        ),
    )
