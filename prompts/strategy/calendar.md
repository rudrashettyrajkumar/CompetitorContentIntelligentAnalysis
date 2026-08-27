You are planning {{ company.name }}'s LinkedIn calendar for the next {{ calendar_days }}
days. Place posts ONLY on the cadence weekdays in the strategy (do not post every day).
Spread pillars so their share of entries matches the recommended content mix (within ~10
points). Each entry names its day number (1..{{ calendar_days }}), weekday, pillar,
topic, format, a one-line objective, a CTA, and — when it realises one — the index of the
opportunity it draws from. Respond with JSON only, matching the schema exactly.

---USER---
Strategy: {{ strategy }}
Opportunities (index = position in this list): {{ opportunities }}

JSON shape:
{"entries": [
  {"day": 2, "weekday": "Tue", "pillar": "<pillar name>", "topic": "...",
   "format": "<format>", "objective": "...", "cta": "<cta type>", "opportunity_ref": 0}
 ],
 "cadence_note": "one line on the rhythm"}
