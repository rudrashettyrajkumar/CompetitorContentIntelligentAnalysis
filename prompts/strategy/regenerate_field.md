You write for {{ company.name }}. A generated {{ field }} for a post about
"{{ topic }}" was rejected as too similar to a competitor's content. Reason:
{{ reason }}. Write ONE replacement {{ field }} on the same topic that is clearly
original — different angle, structure and phrasing. Respond with JSON only.

---USER---
Rejected {{ field }}: {{ current }}

JSON shape:
{"text": "<the new {{ field }}>"}
