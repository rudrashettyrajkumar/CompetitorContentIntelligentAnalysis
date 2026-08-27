"""Input layer: Excel competitor ingestion + validation (EPIC-02)."""

from app.input.excel import IngestError, ingest_excel

__all__ = ["IngestError", "ingest_excel"]
