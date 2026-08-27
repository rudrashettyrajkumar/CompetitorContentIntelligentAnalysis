import pandas as pd
import pytest

from app.input.excel import IngestError, ingest_excel, normalize_company_url

CANON_COLUMNS = ["Competitor", "LinkedIn URL", "Industry", "Country/Market", "Priority"]


def _write_xlsx(path, rows, columns=CANON_COLUMNS):
    pd.DataFrame(rows, columns=columns).to_excel(path, index=False)
    return path


# --------------------------------------------------------------------------- #
# URL normalisation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://www.linkedin.com/company/acme", "https://www.linkedin.com/company/acme"),
        ("http://linkedin.com/company/Acme-Corp/", "https://www.linkedin.com/company/acme-corp"),
        ("https://de.linkedin.com/company/acme", "https://www.linkedin.com/company/acme"),
    ],
)
def test_normalize_company_url_ok(raw, expected):
    assert normalize_company_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://www.linkedin.com/in/some-person",
        "https://www.linkedin.com/school/some-university",
    ],
)
def test_normalize_company_url_rejects_non_company(raw):
    with pytest.raises(ValueError, match="profile or school"):
        normalize_company_url(raw)


def test_normalize_company_url_rejects_garbage():
    with pytest.raises(ValueError, match="not a valid LinkedIn company URL"):
        normalize_company_url("https://example.com/acme")


# --------------------------------------------------------------------------- #
# whole-file ingest
# --------------------------------------------------------------------------- #
def test_sample_workbook_all_accepted():
    report = ingest_excel("data/input/sample_competitors.xlsx")
    assert report.accepted_count == 5
    assert report.rejected_count == 0
    assert {c.priority for c in report.accepted} <= {"High", "Medium", "Low"}


def test_column_order_and_case_insensitive(tmp_path):
    path = _write_xlsx(
        tmp_path / "reordered.xlsx",
        [["Acme", "IT", "https://www.linkedin.com/company/acme", "high", "USA"]],
        columns=["competitor", "industry", "linkedin url", "PRIORITY", "Country/Market"],
    )
    report = ingest_excel(path)
    assert report.accepted_count == 1
    row = report.accepted[0]
    assert row.priority == "High"
    assert row.industry == "IT"
    assert row.market == "USA"


def test_bad_urls_are_rejected_per_row(tmp_path):
    path = _write_xlsx(
        tmp_path / "badurls.xlsx",
        [
            ["Good Co", "https://www.linkedin.com/company/good-co", "IT", "USA", "High"],
            ["Person", "https://www.linkedin.com/in/jane-doe", "IT", "USA", "Low"],
            ["Junk", "not-a-url", "IT", "USA", "Low"],
        ],
    )
    report = ingest_excel(path)
    assert report.accepted_count == 1
    assert {e.row for e in report.rejected} == {3, 4}
    assert any("profile or school" in e.reason for e in report.rejected)


def test_missing_required_columns_raises(tmp_path):
    path = _write_xlsx(
        tmp_path / "missing.xlsx",
        [["Acme", "IT"]],
        columns=["Competitor", "Industry"],
    )
    with pytest.raises(IngestError, match="LinkedIn URL"):
        ingest_excel(path)


def test_empty_and_partial_rows(tmp_path):
    path = _write_xlsx(
        tmp_path / "empty.xlsx",
        [
            ["Acme", "https://www.linkedin.com/company/acme", "IT", "USA", "High"],
            [None, None, None, None, None],
            [None, "https://www.linkedin.com/company/orphan-url", "IT", "USA", "High"],
            ["No URL Co", None, "IT", "USA", "High"],
        ],
    )
    report = ingest_excel(path)
    assert report.accepted_count == 1
    # fully-blank row silently skipped; the two partial rows rejected with reasons
    reasons = {e.row: e.reason for e in report.rejected}
    assert set(reasons) == {4, 5}
    assert "name" in reasons[4].lower()
    assert "linkedin url" in reasons[5].lower()


def test_blank_priority_defaults_medium_with_warning(tmp_path):
    path = _write_xlsx(
        tmp_path / "prio.xlsx",
        [["Acme", "https://www.linkedin.com/company/acme", "IT", "USA", None]],
    )
    report = ingest_excel(path)
    assert report.accepted[0].priority == "Medium"
    assert any("defaulted to Medium" in w for w in report.warnings)


def test_invalid_priority_rejected(tmp_path):
    path = _write_xlsx(
        tmp_path / "prio2.xlsx",
        [["Acme", "https://www.linkedin.com/company/acme", "IT", "USA", "Urgent"]],
    )
    report = ingest_excel(path)
    assert report.accepted_count == 0
    assert "Urgent" in report.rejected[0].reason


def test_duplicate_competitors_deduped_with_warning(tmp_path):
    path = _write_xlsx(
        tmp_path / "dupes.xlsx",
        [
            ["Acme", "https://www.linkedin.com/company/acme", "IT", "USA", "High"],
            ["Acme Corp", "http://linkedin.com/company/Acme/", "IT", "USA", "Low"],
        ],
    )
    report = ingest_excel(path)
    assert report.accepted_count == 1
    assert any("duplicate" in w for w in report.warnings)
