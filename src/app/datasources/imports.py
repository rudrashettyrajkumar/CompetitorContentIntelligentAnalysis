"""Read a competitor's data from local files exported by hand or a third-party tool.

Layout (see ``docs/import-format.md``)::

    data/imports/<slug>/profile.json
    data/imports/<slug>/posts.json      # or posts.csv

``<slug>`` is the LinkedIn company slug (the last path segment of the company URL).
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from app.config.settings import PROJECT_ROOT
from app.datasources.base import DataSource
from app.schemas.collection import CompanyProfile, RawPost

_DEFAULT_DIR = PROJECT_ROOT / "data" / "imports"


class ImportDataError(RuntimeError):
    """A competitor's import directory is missing or malformed."""


def _slug_of(linkedin_url: str) -> str:
    tail = linkedin_url.rstrip("/").rsplit("/company/", 1)[-1]
    return tail.rsplit("/", 1)[-1].lower() or "company"


def _split_list(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).replace(";", ",").split(",") if part.strip()]


class ImportAdapter(DataSource):
    name = "import"

    def __init__(self, imports_dir: str | Path | None = None) -> None:
        self.imports_dir = Path(imports_dir) if imports_dir else _DEFAULT_DIR

    def _dir_for(self, linkedin_url: str) -> Path:
        path = self.imports_dir / _slug_of(linkedin_url)
        if not path.is_dir():
            raise ImportDataError(f"No import directory at {path}")
        return path

    # ------------------------------------------------------------------ #
    def fetch_company_profile(self, linkedin_url: str) -> CompanyProfile:
        path = self._dir_for(linkedin_url) / "profile.json"
        if not path.exists():
            raise ImportDataError(f"Missing {path}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ImportDataError(f"{path} is not valid JSON: {exc}") from exc
        for field in ("geographies", "services"):
            if field in raw:
                raw[field] = _split_list(raw[field])
        raw.setdefault("linkedin_url", linkedin_url)
        return CompanyProfile.model_validate(raw)

    # ------------------------------------------------------------------ #
    def fetch_posts(self, linkedin_url: str, since: datetime) -> list[RawPost]:
        directory = self._dir_for(linkedin_url)
        json_path, csv_path = directory / "posts.json", directory / "posts.csv"
        if json_path.exists():
            rows = self._read_json_posts(json_path)
        elif csv_path.exists():
            rows = self._read_csv_posts(csv_path)
        else:
            raise ImportDataError(f"Missing posts.json/posts.csv in {directory}")

        posts: list[RawPost] = []
        for row in rows:
            row = {k: v for k, v in row.items() if v not in ("", None)}
            if "hashtags" in row:
                row["hashtags"] = _split_list(row["hashtags"])
            posts.append(RawPost.model_validate(row))
        posts.sort(key=lambda p: p.posted_at)
        return [p for p in posts if p.posted_at >= since]

    @staticmethod
    def _read_json_posts(path: Path) -> list[dict]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ImportDataError(f"{path} is not valid JSON: {exc}") from exc
        if isinstance(data, dict) and "posts" in data:
            data = data["posts"]
        if not isinstance(data, list):
            raise ImportDataError(f"{path} must hold a list of posts")
        return data

    @staticmethod
    def _read_csv_posts(path: Path) -> list[dict]:
        with path.open(encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
