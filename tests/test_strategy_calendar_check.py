"""Calendar validation rules (EPIC-06)."""

from app.schemas.strategy import ContentCalendar, ContentStrategy, Pillar
from app.strategy.calendar_check import cadence_weekdays, validate_calendar

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _strategy(pillars=("A", "B"), mix=None, cadence="3 posts per week on Tue, Wed and Thu"):
    return ContentStrategy(
        pillars=[Pillar(name=p, description="d", rationale="r") for p in pillars],
        content_mix=mix or {p: round(100 / len(pillars), 2) for p in pillars},
        posting_cadence=cadence,
    )


def _calendar(strategy, days=30):
    allowed = cadence_weekdays(strategy.posting_cadence)
    slots = [d for d in range(1, days + 1) if _WEEKDAYS[(d - 1) % 7] in allowed]
    names = [p.name for p in strategy.pillars]
    return ContentCalendar(
        entries=[
            {
                "day": d,
                "weekday": _WEEKDAYS[(d - 1) % 7],
                "pillar": names[i % len(names)],
                "topic": "ai",
                "format": "thought_leadership",
                "objective": "o",
                "cta": "learn_more",
                "opportunity_ref": None,
            }
            for i, d in enumerate(slots)
        ],
        cadence_note="n",
    )


def test_cadence_weekdays_parsing():
    assert cadence_weekdays("Tuesday and Thursday only") == {"Tue", "Thu"}
    assert cadence_weekdays("post daily") == {"Tue", "Wed", "Thu"}  # default fallback
    assert cadence_weekdays("Mon/Wed/Fri") == {"Mon", "Wed", "Fri"}


def test_a_well_formed_calendar_passes():
    s = _strategy()
    v = validate_calendar(_calendar(s), s)
    assert v.ok, v.errors


def test_off_cadence_entry_is_flagged():
    s = _strategy()
    cal = _calendar(s)
    cal.entries[0].weekday = "Sat"
    v = validate_calendar(cal, s)
    assert not v.ok and any("not in cadence" in e for e in v.errors)


def test_unknown_pillar_is_flagged():
    s = _strategy()
    cal = _calendar(s)
    cal.entries[0].pillar = "Ghost"
    v = validate_calendar(cal, s)
    assert not v.ok and any("not one of" in e for e in v.errors)


def test_mix_skew_beyond_tolerance_is_flagged():
    s = _strategy(pillars=("A", "B"), mix={"A": 50.0, "B": 50.0})
    cal = _calendar(s)
    for e in cal.entries:  # slam everything onto pillar A
        e.pillar = "A"
    v = validate_calendar(cal, s, mix_tolerance_pct=10)
    assert not v.ok and any("off the recommended" in e for e in v.errors)


def test_day_out_of_window_is_flagged():
    s = _strategy()
    cal = _calendar(s)
    cal.entries[-1].day = 45
    v = validate_calendar(cal, s)
    assert not v.ok and any("1..30" in e for e in v.errors)


def test_calendar_not_spanning_window_is_flagged():
    s = _strategy()
    cal = _calendar(s)
    cal.entries = [e for e in cal.entries if e.day <= 7]
    v = validate_calendar(cal, s)
    assert not v.ok and any("final week" in e for e in v.errors)
