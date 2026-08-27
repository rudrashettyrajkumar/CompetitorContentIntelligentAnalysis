"""Strategy generation (brief steps 11-13, EPIC-06).

A three-step pipeline — pillars → opportunities → calendar — driven by a strategy agent:

* ``DeepStrategyAgent`` — a deepagents run (``reasoning`` tier) per step over the EPIC-05
  intelligence as virtual files, with a single ``router.invoke`` as the net when the
  agent errors. Never used in fake mode.
* ``FakeStrategyAgent`` — a deterministic scripted stub that derives a valid,
  schema-conformant bundle straight from the structured inputs. Powers tests + demo.

Between the agent's opportunity list and the calendar, ``derivation.stamp_signals``
overwrites the three signal fields from data and ``originality.run_originality_guard``
rejects / regenerates / drops any hook/angle/message too close to a competitor post.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config.settings import (
    PROMPTS_DIR,
    AppConfig,
    get_app_config,
    get_taxonomies,
)
from app.core.logging import get_logger
from app.core.model_router import LLMError, ModelRouter, extract_json
from app.core.prompt_registry import PromptRegistry
from app.schemas.strategy import (
    CalendarEntry,
    ContentCalendar,
    ContentOpportunity,
    ContentStrategy,
    FormatRec,
    Pillar,
    RegeneratedField,
    StrategyBundle,
)
from app.strategy.calendar_check import cadence_weekdays, validate_calendar
from app.strategy.derivation import stamp_signals
from app.strategy.inputs import StrategyInputs, assemble_strategy_inputs
from app.strategy.originality import run_originality_guard

log = get_logger(__name__)

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_CTAS = ["learn_more", "demo", "download", "comment"]
_DEFAULT_FORMATS = ["thought_leadership", "carousel", "case_study", "video"]
_FAKE_CADENCE = "3 posts per week on Tue, Wed and Thu"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _largest_remainder(n: int, weights: dict[str, float]) -> list[str]:
    """Allocate ``n`` slots across keys proportional to ``weights`` (largest remainder)."""
    keys = list(weights)
    if not keys or n <= 0:
        return []
    total = sum(weights.values()) or 1.0
    raw = {k: weights[k] / total * n for k in keys}
    counts = {k: int(raw[k]) for k in keys}
    remaining = n - sum(counts.values())
    for k in sorted(keys, key=lambda k: raw[k] - counts[k], reverse=True)[:remaining]:
        counts[k] += 1
    out: list[str] = []
    for k in keys:
        out.extend([k] * counts[k])
    return out


_ACRONYMS = {"ai": "AI", "cx": "CX", "roi": "ROI", "seo": "SEO", "b2b": "B2B"}


def _titleize(topic: str) -> str:
    return " ".join(_ACRONYMS.get(w, w.capitalize()) for w in topic.replace("_", " ").split())


def _even_mix(names: list[str]) -> dict[str, float]:
    """Percentages that sum to exactly 100."""
    if not names:
        return {}
    base = round(100 / len(names))
    mix = {n: float(base) for n in names}
    mix[names[-1]] = float(100 - base * (len(names) - 1))
    return mix


# --------------------------------------------------------------------------- #
# fake (offline) agent
# --------------------------------------------------------------------------- #
class FakeStrategyAgent:
    def pillars(self, inputs: StrategyInputs, *, pmin: int, pmax: int) -> ContentStrategy:
        cross = inputs.cross
        seeds: list[tuple[str, str]] = []
        for t in cross.common_themes:
            seeds.append(
                (
                    t.topic,
                    f"Competitors are converging on {t.topic.replace('_', ' ')} "
                    f"({t.competitors_covering}/{max(inputs.n_competitors, 1)} cover it); "
                    f"we win by out-specific-ing them with operator proof.",
                )
            )
        for w in cross.white_spaces:
            seeds.append(
                (
                    w.topic,
                    f"White space: only {w.competitors_covering} competitor(s) cover "
                    f"{w.topic.replace('_', ' ')} ({w.reason}) — first credible voice takes it.",
                )
            )
        for o in cross.opportunity_topics:
            seeds.append(
                (
                    o.topic,
                    f"{o.topic.replace('_', ' ')} runs "
                    f"{o.engagement_vs_median:+.0f} above median engagement at low coverage.",
                )
            )
        for diff in inputs.company.differentiators:
            seeds.append(("differentiator", f"Own our edge: {diff}."))

        picked: list[Pillar] = []
        used: set[str] = set()
        for topic, rationale in seeds:
            key = topic if topic != "differentiator" else rationale
            if key in used:
                continue
            used.add(key)
            name = (
                _titleize(topic)
                if topic not in ("differentiator", "other")
                else rationale.split(":", 1)[-1].strip().rstrip(".")[:48]
            )
            picked.append(
                Pillar(name=name, description=f"Content built around {name}.", rationale=rationale)
            )
            if len(picked) >= pmax:
                break
        while len(picked) < pmin:
            n = len(picked) + 1
            picked.append(
                Pillar(
                    name=f"Operator Playbooks {n}",
                    description="Repeatable how-we-did-it breakdowns.",
                    rationale="Fills the pillar minimum; anchored on our services.",
                )
            )

        pillar_names = [p.name for p in picked]
        mix = _even_mix(pillar_names)
        fmt_recs: list[FormatRec] = []
        fmt_names: list[str] = []
        for fo in cross.format_opportunities:
            fmt_names.append(fo.format)
            fmt_recs.append(
                FormatRec(
                    format=fo.format,
                    share=0.0,
                    rationale=f"{fo.engagement_multiplier}x average engagement at "
                    f"{fo.post_share:.0%} of competitor posts — under-served.",
                )
            )
        for f in _DEFAULT_FORMATS:
            if f not in fmt_names:
                fmt_names.append(f)
                fmt_recs.append(FormatRec(format=f, share=0.0, rationale="Reliable base format."))
        fmt_share = _even_mix(fmt_names)
        for rec in fmt_recs:
            rec.share = fmt_share[rec.format]

        windows = Counter(w for p in inputs.profiles for w in p.engagement_windows)
        eng_windows = [w for w, _ in windows.most_common(3)] or ["Tue", "Wed", "Thu"]

        return ContentStrategy(
            pillars=picked,
            content_mix=mix,
            recommended_formats=fmt_recs,
            posting_cadence=_FAKE_CADENCE,
            engagement_windows=eng_windows,
        )

    def opportunities(
        self, inputs: StrategyInputs, strategy: ContentStrategy, *, omin: int, omax: int
    ) -> list[ContentOpportunity]:
        pool: list[str] = []
        for src in (
            [w.topic for w in inputs.cross.white_spaces],
            [o.topic for o in inputs.cross.opportunity_topics],
            [t.topic for t in inputs.cross.common_themes],
            list(inputs.topic_stats),
        ):
            for topic in src:
                if topic not in pool and topic != "other":
                    pool.append(topic)
        if not pool:
            pool = ["digital_transformation", "automation", "data_analytics"]

        target = max(omin, min(omax, len(pool)))
        target = max(target, omin)
        kw = inputs.keyword_terms()
        pillars = strategy.pillars
        formats = [r.format for r in strategy.recommended_formats] or _DEFAULT_FORMATS

        opps: list[ContentOpportunity] = []
        for i in range(target):
            topic = pool[i % len(pool)]
            human = topic.replace("_", " ")
            diff = (
                inputs.company.differentiators[i % max(len(inputs.company.differentiators), 1)]
                if inputs.company.differentiators
                else "measurable outcomes"
            )
            svc = (
                inputs.company.services[i % max(len(inputs.company.services), 1)]
                if inputs.company.services
                else "our platform"
            )
            opps.append(
                ContentOpportunity(
                    topic=topic,
                    pillar=pillars[i % len(pillars)].name,
                    recommended_format=formats[i % len(formats)],
                    target_audience=inputs.company.target_audience
                    or "mid-market operations leaders",
                    hook=(
                        f"The {human} advice nobody posts: what actually moved our "
                        f"numbers, step by step"
                    ),
                    angle=f"Northwind's operator read on {human} — {diff}, shown not claimed",
                    key_message=(
                        f"Teams can make real progress on {human} in weeks, not quarters, "
                        f"by going {svc}-first and measuring every step."
                    ),
                    structure=[
                        "Hook + what's at stake",
                        "The default approach and why it stalls",
                        "Our approach, step by step",
                        "The numbers it produced",
                        "Call to action",
                    ],
                    cta=_CTAS[i % len(_CTAS)],
                    keywords=[human, *kw[:2]],
                    hashtags=[human.replace(" ", "")],
                )
            )
        return opps

    def calendar(
        self,
        inputs: StrategyInputs,
        strategy: ContentStrategy,
        opportunities: list[ContentOpportunity],
        *,
        days: int,
    ) -> ContentCalendar:
        allowed = cadence_weekdays(strategy.posting_cadence)
        slot_days = [d for d in range(1, days + 1) if _WEEKDAYS[(d - 1) % 7] in allowed]
        pillars = _largest_remainder(len(slot_days), strategy.content_mix) or [
            p.name for p in strategy.pillars
        ]
        entries: list[CalendarEntry] = []
        for i, day in enumerate(slot_days):
            pillar = pillars[i % len(pillars)]
            opp = opportunities[i % len(opportunities)] if opportunities else None
            entries.append(
                CalendarEntry(
                    day=day,
                    weekday=_WEEKDAYS[(day - 1) % 7],
                    pillar=pillar,
                    topic=opp.topic if opp else pillar,
                    format=opp.recommended_format if opp else _DEFAULT_FORMATS[i % 4],
                    objective=f"Advance the {pillar} pillar",
                    cta=opp.cta if opp else "learn_more",
                    opportunity_ref=(i % len(opportunities)) if opportunities else None,
                )
            )
        note = f"{len(entries)} posts across {days} days on {', '.join(sorted(allowed))}."
        return ContentCalendar(entries=entries, cadence_note=note)

    def regenerate_field(
        self, inputs: StrategyInputs, opp: ContentOpportunity, field: str, reason: str
    ) -> str:
        human = opp.topic.replace("_", " ")
        return {
            "hook": (
                f"An unglamorous field note on {human}: three calls we got wrong before it worked"
            ),
            "angle": f"What our {human} rollout taught us that no competitor deck will admit",
            "key_message": (
                f"On {human}, the winning move is boring: instrument first, ship small, "
                f"and let the {inputs.company.name} dashboards settle the argument."
            ),
        }.get(field, f"Fresh original take on {human}.")


# --------------------------------------------------------------------------- #
# deep (production) agent
# --------------------------------------------------------------------------- #
class DeepStrategyAgent:
    def __init__(self, router: ModelRouter, registry: PromptRegistry | None = None) -> None:
        self.router = router
        self.registry = registry or PromptRegistry(PROMPTS_DIR)

    def _run(self, prompt: str, files: dict[str, str], **variables):
        rendered = self.registry.render(prompt, **variables)
        try:
            text = self._deep_agent_text(rendered, files)
            return rendered.schema.model_validate_json(extract_json(text))
        except Exception as exc:  # noqa: BLE001 — deep agent is best-effort; router is the net
            log.warning("strategy_deep_agent_fallback", prompt=prompt, error=str(exc))
            return self.router.invoke(
                tier=rendered.meta.model_tier,
                system=rendered.system,
                user=rendered.user,
                schema=rendered.schema,
                temperature=rendered.meta.temperature,
                prompt_name=rendered.meta.name,
                prompt_version=rendered.meta.version,
            )

    def _deep_agent_text(self, rendered, files: dict[str, str]) -> str:
        from deepagents import create_deep_agent

        model = self.router.chat_model_for(
            rendered.meta.model_tier, temperature=rendered.meta.temperature
        )
        agent = create_deep_agent(tools=[], system_prompt=rendered.system, model=model)
        state = agent.invoke(
            {"messages": [{"role": "user", "content": rendered.user}], "files": files}
        )
        messages = state.get("messages", []) if isinstance(state, dict) else []
        if not messages:
            raise LLMError("strategy deep agent returned no messages")
        last = messages[-1]
        return getattr(last, "content", None) or last.get("content", "")

    def pillars(self, inputs: StrategyInputs, *, pmin: int, pmax: int) -> ContentStrategy:
        return self._run(
            "pillars",
            inputs.as_agent_files(),
            company=inputs.company.model_dump(),
            profiles=[p.model_dump() for p in inputs.profiles],
            cross=inputs.cross.model_dump(),
            top_content=inputs.top_content.model_dump(),
            campaigns=inputs.campaigns,
            pillars_min=pmin,
            pillars_max=pmax,
        )

    def opportunities(
        self, inputs: StrategyInputs, strategy: ContentStrategy, *, omin: int, omax: int
    ) -> list[ContentOpportunity]:
        result = self._run(
            "opportunities",
            inputs.as_agent_files(),
            company=inputs.company.model_dump(),
            strategy=strategy.model_dump(),
            cross=inputs.cross.model_dump(),
            topic_stats={t: vars(s) for t, s in inputs.topic_stats.items()},
            keyword_terms=inputs.keyword_terms(),
            opportunities_min=omin,
            opportunities_max=omax,
            taxonomy_formats=get_taxonomies().formats,
        )
        return list(result.opportunities)

    def calendar(
        self,
        inputs: StrategyInputs,
        strategy: ContentStrategy,
        opportunities: list[ContentOpportunity],
        *,
        days: int,
    ) -> ContentCalendar:
        return self._run(
            "calendar",
            inputs.as_agent_files(),
            company=inputs.company.model_dump(),
            strategy=strategy.model_dump(),
            opportunities=[o.model_dump() for o in opportunities],
            calendar_days=days,
        )

    def regenerate_field(
        self, inputs: StrategyInputs, opp: ContentOpportunity, field: str, reason: str
    ) -> str:
        rendered = self.registry.render(
            "regenerate_field",
            company=inputs.company.model_dump(),
            topic=opp.topic,
            field=field,
            reason=reason,
            current=getattr(opp, field),
        )
        try:
            out = self.router.invoke(
                tier=rendered.meta.model_tier,
                system=rendered.system,
                user=rendered.user,
                schema=rendered.schema,
                temperature=rendered.meta.temperature,
                prompt_name=rendered.meta.name,
                prompt_version=rendered.meta.version,
            )
            return out.text if isinstance(out, RegeneratedField) else ""
        except LLMError:
            return ""


# --------------------------------------------------------------------------- #
# steps (composed by generate_strategy and by the LangGraph stage)
# --------------------------------------------------------------------------- #
@dataclass
class StrategyConfig:
    pmin: int
    pmax: int
    omin: int
    omax: int
    days: int
    tol: float
    raw: dict

    @classmethod
    def from_app(cls, app_config: AppConfig | None) -> StrategyConfig:
        cfg = (app_config or get_app_config()).strategy or {}
        return cls(
            pmin=int(cfg.get("pillars_min", 4)),
            pmax=int(cfg.get("pillars_max", 6)),
            omin=int(cfg.get("opportunities_min", 8)),
            omax=int(cfg.get("opportunities_max", 12)),
            days=int(cfg.get("calendar_days", 30)),
            tol=float(cfg.get("mix_tolerance_pct", 10)),
            raw=cfg,
        )


def resolve_agent(router: ModelRouter, registry: PromptRegistry, agent: object | None):
    if agent is not None:
        return agent
    return FakeStrategyAgent() if router.use_fake else DeepStrategyAgent(router, registry)


def step_pillars(inputs: StrategyInputs, agent, cfg: StrategyConfig) -> ContentStrategy:
    strategy = agent.pillars(inputs, pmin=cfg.pmin, pmax=cfg.pmax)
    strategy.pillars = strategy.pillars[: cfg.pmax] or strategy.pillars
    if not strategy.content_mix:
        strategy.content_mix = _even_mix([p.name for p in strategy.pillars])
    return strategy


def step_opportunities(
    inputs: StrategyInputs,
    agent,
    strategy: ContentStrategy,
    *,
    router: ModelRouter,
    registry: PromptRegistry,
    cfg: StrategyConfig,
) -> tuple[list[ContentOpportunity], list]:
    opportunities = agent.opportunities(inputs, strategy, omin=cfg.omin, omax=cfg.omax)
    for opp in opportunities:
        for name, value in stamp_signals(opp.topic, inputs.topic_stats, cfg.raw).items():
            setattr(opp, name, value)
    guard = run_originality_guard(
        opportunities,
        inputs.competitor_texts,
        router=router,
        registry=registry,
        cfg=cfg.raw,
        regenerate=lambda oi, field, reason: agent.regenerate_field(
            inputs, opportunities[oi], field, reason
        ),
    )
    return guard.opportunities, guard.checks


def step_calendar(
    inputs: StrategyInputs,
    agent,
    strategy: ContentStrategy,
    opportunities: list[ContentOpportunity],
    cfg: StrategyConfig,
):
    calendar = agent.calendar(inputs, strategy, opportunities, days=cfg.days)
    validation = validate_calendar(
        calendar, strategy, calendar_days=cfg.days, mix_tolerance_pct=cfg.tol
    )
    return calendar, validation


# --------------------------------------------------------------------------- #
# orchestrator (direct; the graph in strategy/graph.py adds persistence)
# --------------------------------------------------------------------------- #
@dataclass
class StrategyRunResult:
    run_id: int
    bundle: StrategyBundle
    calendar_valid: bool
    calendar_errors: list[str]


def generate_strategy(
    session: Session,
    *,
    run_id: int,
    router: ModelRouter,
    registry: PromptRegistry,
    app_config: AppConfig | None = None,
    agent: object | None = None,
) -> StrategyRunResult:
    cfg = StrategyConfig.from_app(app_config)
    inputs = assemble_strategy_inputs(session, run_id=run_id)
    agent = resolve_agent(router, registry, agent)

    strategy = step_pillars(inputs, agent, cfg)
    opportunities, checks = step_opportunities(
        inputs, agent, strategy, router=router, registry=registry, cfg=cfg
    )
    calendar, validation = step_calendar(inputs, agent, strategy, opportunities, cfg)
    if not validation.ok:
        log.warning("calendar_validation_failed", run_id=run_id, errors=validation.errors)

    bundle = StrategyBundle(
        strategy=strategy,
        opportunities=opportunities,
        calendar=calendar,
        originality_checks=checks,
    )
    log.info(
        "strategy_generated",
        run_id=run_id,
        pillars=len(strategy.pillars),
        opportunities=len(opportunities),
        calendar_entries=len(calendar.entries),
        calendar_valid=validation.ok,
    )
    return StrategyRunResult(
        run_id=run_id,
        bundle=bundle,
        calendar_valid=validation.ok,
        calendar_errors=validation.errors,
    )
