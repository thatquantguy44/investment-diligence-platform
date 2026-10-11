from __future__ import annotations

import csv
import hashlib
import io
import json
from contextlib import contextmanager
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from diligence_pipelines.sources.base import RawCapture, SourceRequest


def _records_from_bytes(payload: bytes, name: str) -> list[dict]:
    """Read the common ODP export shapes without assuming one file format."""
    suffix = Path(name).suffix.lower()
    if suffix == ".zip" or payload[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [member for member in archive.namelist() if not member.endswith("/")]
            if not members:
                return []
            member = next((item for item in members if Path(item).suffix.lower() in {".json", ".jsonl", ".csv", ".tsv"}), members[0])
            return _records_from_bytes(archive.read(member), member)

    text = payload.decode("utf-8-sig")
    if suffix in {".csv", ".tsv"} or ("\n" in text and "," in text.splitlines()[0] and not text.lstrip().startswith(("{", "["))):
        return list(csv.DictReader(io.StringIO(text), delimiter="\t" if suffix == ".tsv" else ","))

    if suffix in {".jsonl", ".ndjson"}:
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    parsed = json.loads(text)
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        for key in ("patents", "data", "results", "records"):
            if isinstance(parsed.get(key), list):
                return [item for item in parsed[key] if isinstance(item, dict)]
        return [parsed]
    raise ValueError(f"Unsupported USPTO bulk payload: {name}")


@contextmanager
def _row_reader(path: Path):
    if path.suffix.lower() == ".zip" or path.read_bytes()[:2] == b"PK":
        archive = zipfile.ZipFile(path)
        members = [member for member in archive.namelist() if not member.endswith("/")]
        member = next((item for item in members if Path(item).suffix.lower() in {".csv", ".tsv", ".jsonl", ".ndjson"}), members[0])
        handle = io.TextIOWrapper(archive.open(member), encoding="utf-8-sig")
        try:
            if Path(member).suffix.lower() in {".csv", ".tsv"}:
                yield csv.DictReader(handle, delimiter="\t" if Path(member).suffix.lower() == ".tsv" else ",")
            else:
                yield (json.loads(line) for line in handle if line.strip())
        finally:
            handle.close()
            archive.close()
        return
    if path.suffix.lower() in {".csv", ".tsv"}:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            yield csv.DictReader(handle, delimiter="\t" if path.suffix.lower() == ".tsv" else ",")
        return
    with path.open(encoding="utf-8-sig") as handle:
        if path.suffix.lower() in {".jsonl", ".ndjson"}:
            yield (json.loads(line) for line in handle if line.strip())
        else:
            yield iter(_records_from_bytes(path.read_bytes(), path.name))


def iter_bulk_rows(path: Path):
    with _row_reader(path) as rows:
        yield from rows


def _first(row: dict, *keys: str) -> object:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _to_patent(row: dict) -> dict | None:
    patent_id = _first(row, "patent_id", "patent_number", "publication_number", "document_number")
    title = _first(row, "patent_title", "title", "invention_title")
    if patent_id in (None, "") or title in (None, ""):
        return None
    patent = {
        "patent_id": str(patent_id),
        "patent_title": str(title),
        "patent_date": _first(row, "patent_date", "grant_date", "publication_date", "filing_date"),
        "patent_type": _first(row, "patent_type", "document_type"),
    }
    abstract = _first(row, "patent_abstract", "abstract")
    if abstract:
        patent["patent_abstract"] = str(abstract)
    assignee = _first(row, "assignee_organization", "assignee_name", "applicant_name")
    if assignee:
        patent["assignees"] = [{"assignee_organization": str(assignee), "assignee_id": row.get("assignee_id")}]
    return patent


def fetch_patents_from_bulk_file(path: Path, query: str, max_results: int = 25) -> RawCapture:
    if not query.strip():
        raise ValueError("Patent query must not be empty")
    if not 1 <= max_results <= 1000:
        raise ValueError("max_results must be between 1 and 1000")
    source_payload = path.read_bytes()
    needle = query.casefold()
    matches = []
    for row in _records_from_bytes(source_payload, path.name):
        patent = _to_patent(row)
        if patent is None:
            continue
        haystack = " ".join(str(patent.get(key, "")) for key in ("patent_title", "patent_abstract"))
        if needle in haystack.casefold():
            matches.append(patent)
        if len(matches) >= max_results:
            break
    payload = json.dumps({"patents": matches}, separators=(",", ":")).encode()
    return RawCapture(
        request=SourceRequest(
            "uspto_patents_bulk",
            path.resolve().as_uri(),
            {"query": query, "max_results": str(max_results), "source_format": path.suffix.lower().lstrip(".")},
        ),
        payload=payload,
        status_code=200,
        adapter_version="uspto-odp-bulk-search-1.0.0",
    )


def load_bulk_patent_index(path: Path, limit: int | None = None) -> tuple[list[dict], dict]:
    """Validate and normalize a bulk artifact for durable local/Postgres indexing."""
    payload = path.read_bytes()
    records = []
    skipped = 0
    for row in iter_bulk_rows(path):
        patent = _to_patent(row)
        if patent is None:
            skipped += 1
            continue
        records.append({
            "record_id": f"patent_index:{patent['patent_id']}",
            "schema_version": "1.0.0",
            "source_id": "uspto_patents_bulk",
            "patent_id": patent["patent_id"],
            "title": patent["patent_title"],
            "abstract": patent.get("patent_abstract"),
            "patent_date": patent.get("patent_date"),
            "patent_type": patent.get("patent_type"),
            "assignee_name": (patent.get("assignees") or [{}])[0].get("assignee_organization"),
        })
        if limit is not None and len(records) >= limit:
            break
    metadata = {
        "source_path": str(path),
        "source_file_sha256": hashlib.sha256(payload).hexdigest(),
        "record_count": len(records),
        "skipped_count": skipped,
        "adapter_version": "uspto-odp-index-1.0.0",
        "limit": limit,
    }
    return records, metadata


def enrich_bulk_patents(records: list[dict], abstract_path: Path | None = None, assignee_path: Path | None = None) -> list[dict]:
    by_id = {record["patent_id"]: record for record in records}
    for path, field, source_keys in (
        (abstract_path, "abstract", ("patent_abstract", "abstract")),
        (assignee_path, "assignee_name", ("disambig_assignee_organization", "assignee_organization", "assignee_name")),
    ):
        if path is None:
            continue
        remaining = set(by_id)
        for row in iter_bulk_rows(path):
            patent_id = _first(row, "patent_id", "patent_number", "publication_number")
            if patent_id is None or str(patent_id) not in by_id:
                continue
            value = _first(row, *source_keys)
            if value:
                by_id[str(patent_id)][field] = str(value)
                remaining.discard(str(patent_id))
            if not remaining:
                break
    return list(by_id.values())
