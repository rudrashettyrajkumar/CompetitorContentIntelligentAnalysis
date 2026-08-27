"""Excel competitor ingestion + per-row validation.

Columns (case-insensitive, order-free): ``Competitor``, ``LinkedIn URL``,
``Industry``, ``Country/Market``, ``Priority``. Dynamic row count.

Structural problems (unreadable file, missing required columns) raise ``IngestError``.
Row-level problems never fail the call — they land in ``IngestReport.rejected`` /
``IngestReport.warnings``.
"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

import pandas as pd

from app.schemas.collection import PRIORITIES, CompetitorIn, IngestReport, RowError

# Header aliases -> canonical field name. Comparison is done on a normalised key
# (lowercased, non-alphanumerics stripped) so "LinkedIn URL", "linkedin_url" and
# "Linkedin  Url" all match.
_COLUMN_ALIASES: dict[str, str] = {
    "competitor": "name",
    "competitorname": "name",
    "name": "name",
    "company": "name",
    "linkedinurl": "linkedin_url",
    "linkedin": "linkedin_url",
    "url": "linkedin_url",
    "industry": "industry",
    "sector": "industry",
    "countrymarket": "market",
    "country": "market",
    "market": "market",
    "geography": "market",
    "priority": "priority",
}

_REQUIRED = ("name", "linkedin_url")

_COMPANY_URL_RE = re.compile(
    r"^https?://(?:[a-z0-9-]+\.)?linkedin\.com/company/([A-Za-z0-9\-_%.]+)/?$",
    re.IGNORECASE,
)
_OTHER_LINKEDIN_RE = re.compile(
    r"^https?://(?:[a-z0-9-]+\.)?linkedin\.com/(in|school|pub|profile)/",
    re.IGNORECASE,
)


class IngestError(Exception):
    """Structural failure — the workbook itself is unusable."""


def _norm_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


def normalize_company_url(raw: str) -> str:
    """Return the canonical ``https://www.linkedin.com/company/<slug>`` form.

    Raises ``ValueError`` with a specific message for profile/school URLs and for
    anything that is not a company URL at all.
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("LinkedIn URL is missing")
    if _OTHER_LINKEDIN_RE.match(text):
        raise ValueError(
            "URL points to a personal profile or school page, not a company page "
            "(expected linkedin.com/company/<slug>)"
        )
    match = _COMPANY_URL_RE.match(text)
    if not match:
        raise ValueError(
            f"'{raw}' is not a valid LinkedIn company URL "
            "(expected https://www.linkedin.com/company/<slug>)"
        )
    slug = match.group(1).strip("/").lower()
    return f"https://www.linkedin.com/company/{slug}"


def _cell(row: pd.Series, field: str) -> str:
    if field not in row:
        return ""
    value = row[field]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _resolve_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map canonical field -> actual column label present in the frame."""
    resolved: dict[str, str] = {}
    for column in df.columns:
        field = _COLUMN_ALIASES.get(_norm_key(column))
        if field and field not in resolved:
            resolved[field] = column
    return resolved


def ingest_excel(source: str | Path | bytes) -> IngestReport:
    """Parse and validate a competitor workbook.

    ``source`` may be a path, raw bytes, or a file-like object accepted by pandas.
    """
    try:
        if isinstance(source, bytes):
            frame = pd.read_excel(BytesIO(source), dtype=str)
        else:
            frame = pd.read_excel(source, dtype=str)
    except IngestError:
        raise
    except Exception as exc:  # noqa: BLE001 — pandas/openpyxl raise a zoo of types
        raise IngestError(f"Could not read Excel workbook: {exc}") from exc

    columns = _resolve_columns(frame)
    missing = [c for c in _REQUIRED if c not in columns]
    if missing:
        pretty = {"name": "Competitor", "linkedin_url": "LinkedIn URL"}
        raise IngestError(
            "Missing required column(s): "
            + ", ".join(pretty.get(m, m) for m in missing)
            + f". Found columns: {list(frame.columns)}"
        )

    frame = frame.rename(columns={v: k for k, v in columns.items()})

    report = IngestReport()
    seen_urls: dict[str, int] = {}

    for offset, (_, row) in enumerate(frame.iterrows()):
        sheet_row = offset + 2  # +1 for 0-index, +1 for the header row
        name = _cell(row, "name")
        raw_url = _cell(row, "linkedin_url")
        raw_data = {
            "name": name,
            "linkedin_url": raw_url,
            "industry": _cell(row, "industry"),
            "market": _cell(row, "market"),
            "priority": _cell(row, "priority"),
        }

        if not name and not raw_url:
            continue  # entirely blank row — silently skip

        if not name:
            report.rejected.append(
                RowError(row=sheet_row, reason="Missing competitor name", data=raw_data)
            )
            continue
        if not raw_url:
            report.rejected.append(
                RowError(row=sheet_row, reason="Missing LinkedIn URL", data=raw_data)
            )
            continue

        try:
            canonical = normalize_company_url(raw_url)
        except ValueError as exc:
            report.rejected.append(RowError(row=sheet_row, reason=str(exc), data=raw_data))
            continue

        if canonical in seen_urls:
            report.warnings.append(
                f"Row {sheet_row}: duplicate of row {seen_urls[canonical]} ({canonical}) — skipped"
            )
            continue
        seen_urls[canonical] = sheet_row

        priority_raw = raw_data["priority"]
        priority = priority_raw.strip().title() if priority_raw else ""
        if not priority:
            priority = "Medium"
            report.warnings.append(f"Row {sheet_row}: priority blank — defaulted to Medium")
        elif priority not in PRIORITIES:
            report.rejected.append(
                RowError(
                    row=sheet_row,
                    reason=f"Priority '{priority_raw}' is not one of {list(PRIORITIES)}",
                    data=raw_data,
                )
            )
            continue

        report.accepted.append(
            CompetitorIn(
                name=name,
                linkedin_url=canonical,
                industry=raw_data["industry"] or None,
                market=raw_data["market"] or None,
                priority=priority,
            )
        )

    return report
