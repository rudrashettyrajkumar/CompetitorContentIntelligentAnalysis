"""Deterministic validation of a generated 30-day calendar (EPIC-06).

Rules (from the spec):
* exactly ``calendar_days`` consecutive days, numbered 1..N with no gaps or repeats;
* entries fall only on the strategy's cadence weekdays;
* every entry's ``pillar`` is one of the strategy's pillars;
* the per-pillar share of entries lands within ``mix_tolerance_pct`` points of the
  recommended ``content_mix``.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from app.schemas.strategy import ContentCalendar, ContentStrategy

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_WEEKDAY_ALIASES = {
    "monday": "Mon",
    "tuesday": "Tue",
    "wednesday": "Wed",
    "thursday": "Thu",
    "friday": "Fri",
    "saturday": "Sat",
    "sunday": "Sun",
}


@dataclass
class CalendarValidation:
    ok: bool
    errors: list[str] = field(default_factory=list)


def cadence_weekdays(cadence: str) -> set[str]:
    """Pull weekday tokens out of a free-text cadence string; default Tue/Wed/Thu."""
    found: set[str] = set()
    low = (cadence or "").lower()
    for token in re.findall(r"[a-z]+", low):
        if token[:3].capitalize() in _WEEKDAYS:
            found.add(token[:3].capitalize())
        elif token in _WEEKDAY_ALIASES:
            found.add(_WEEKDAY_ALIASES[token])
    return found or {"Tue", "Wed", "Thu"}


def validate_calendar(
    calendar: ContentCalendar,
    strategy: ContentStrategy,
    *,
    calendar_days: int = 30,
    mix_tolerance_pct: float = 10.0,
) -> CalendarValidation:
    errors: list[str] = []
    entries = sorted(calendar.entries, key=lambda e: e.day)

    days = [e.day for e in entries]
    if days and (min(days) < 1 or max(days) > calendar_days):
        errors.append(f"entry days must fall in 1..{calendar_days}; got {min(days)}..{max(days)}")
    if len(set(days)) != len(days):
        errors.append("duplicate day numbers in calendar")

    allowed = cadence_weekdays(strategy.posting_cadence)
    pillar_names = {p.name for p in strategy.pillars}

    for e in entries:
        if e.weekday not in allowed:
            errors.append(f"day {e.day}: weekday {e.weekday!r} not in cadence {sorted(allowed)}")
        if e.pillar not in pillar_names:
            errors.append(f"day {e.day}: pillar {e.pillar!r} is not one of {sorted(pillar_names)}")

    # calendar must actually span the window: at least one entry in the first and last week
    if entries:
        if min(days) > 7:
            errors.append("no entry in the first 7 days — calendar does not span the window")
        if max(days) <= calendar_days - 7:
            errors.append(f"no entry in the final week (day > {calendar_days - 7})")
    else:
        errors.append("calendar has no entries")

    # per-pillar mix within tolerance of the recommended content_mix
    if entries and strategy.content_mix:
        counts = Counter(e.pillar for e in entries)
        total = sum(counts.values())
        for pillar, target_pct in strategy.content_mix.items():
            actual_pct = counts.get(pillar, 0) / total * 100
            if abs(actual_pct - target_pct) > mix_tolerance_pct:
                errors.append(
                    f"pillar {pillar!r}: calendar share {actual_pct:.0f}% is >"
                    f"{mix_tolerance_pct:.0f}pts off the recommended {target_pct:.0f}%"
                )

    return CalendarValidation(ok=not errors, errors=errors)
