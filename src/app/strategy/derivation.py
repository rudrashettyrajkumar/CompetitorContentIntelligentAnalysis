"""Signal-stamping derivation rules (EPIC-06).

The deep agent proposes ``competitor_signal`` / ``competition_level`` /
``engagement_potential`` on every opportunity, but those three fields are overwritten
here from ``TopicStat`` data so they are reproducible and auditable rather than free LLM
output. Cut-offs live in ``config/app.yaml: strategy``.

* ``competitor_signal``  <- topic post-share (how loudly competitors talk about it)
* ``competition_level``   <- how many competitors cover the topic
* ``engagement_potential`` <- cross-insight quadrant flags + above/below median engagement
"""

from __future__ import annotations

from app.strategy.inputs import TopicStat

_Level = str


def _band(value: float, high: float, med: float) -> _Level:
    if value >= high:
        return "high"
    if value >= med:
        return "medium"
    return "low"


def derive_competitor_signal(stat: TopicStat | None, cfg: dict) -> _Level:
    if stat is None:
        return "low"
    return _band(
        stat.post_share,
        float(cfg.get("signal_topic_share_high", 0.15)),
        float(cfg.get("signal_topic_share_med", 0.05)),
    )


def derive_competition_level(stat: TopicStat | None, cfg: dict) -> _Level:
    if stat is None:
        return "low"
    return _band(
        float(stat.competitors_covering),
        float(cfg.get("competition_competitors_high", 3)),
        float(cfg.get("competition_competitors_med", 2)),
    )


def derive_engagement_potential(stat: TopicStat | None, cfg: dict) -> _Level:  # noqa: ARG001
    if stat is None:
        return "low"
    if stat.is_opportunity or stat.is_white_space:
        return "high"
    if stat.above_median_engagement:
        return "medium"
    return "low"


def stamp_signals(topic: str, topic_stats: dict[str, TopicStat], cfg: dict) -> dict[str, _Level]:
    """Return the three derived fields for a topic (case-insensitive lookup)."""
    stat = topic_stats.get(topic) or topic_stats.get(topic.strip().lower())
    return {
        "competitor_signal": derive_competitor_signal(stat, cfg),
        "competition_level": derive_competition_level(stat, cfg),
        "engagement_potential": derive_engagement_potential(stat, cfg),
    }
