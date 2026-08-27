"""Generate the shipped input workbooks.

    python scripts/make_sample_input.py

Writes:
- data/input/competitors_template.xlsx  — headers + one placeholder row
- data/input/sample_competitors.xlsx    — 5 fictional competitors for demo/tests
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "input"

COLUMNS = ["Competitor", "LinkedIn URL", "Industry", "Country/Market", "Priority"]

TEMPLATE_ROW = [
    [
        "Example Corp",
        "https://www.linkedin.com/company/example-corp",
        "IT Services",
        "United States",
        "Medium",
    ]
]

SAMPLE_ROWS = [
    [
        "Nimbus Analytics",
        "https://www.linkedin.com/company/nimbus-analytics",
        "Data & Analytics SaaS",
        "United States",
        "High",
    ],
    [
        "Helvetica Cloud",
        "https://www.linkedin.com/company/helvetica-cloud",
        "Cloud Infrastructure",
        "Germany",
        "High",
    ],
    [
        "Kettle & Co Consulting",
        "https://www.linkedin.com/company/kettle-co-consulting",
        "Management Consulting",
        "United Kingdom",
        "Medium",
    ],
    [
        "Pangolin Security",
        "https://www.linkedin.com/company/pangolin-security",
        "Cybersecurity",
        "Singapore",
        "High",
    ],
    [
        "BrightLoom Marketing",
        "https://www.linkedin.com/company/brightloom-marketing",
        "MarTech",
        "Canada",
        "Low",
    ],
]


def _write(path: Path, rows: list[list[str]]) -> None:
    pd.DataFrame(rows, columns=COLUMNS).to_excel(path, index=False)
    print(f"wrote {path} ({len(rows)} row(s))")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _write(OUT_DIR / "competitors_template.xlsx", TEMPLATE_ROW)
    _write(OUT_DIR / "sample_competitors.xlsx", SAMPLE_ROWS)


if __name__ == "__main__":
    main()
