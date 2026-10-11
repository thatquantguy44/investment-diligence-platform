from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from diligence_pipelines.sources.uspto_bulk import iter_bulk_patent_index, iter_bulk_rows


def _record_digest(record: dict) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def compare_bulk_releases(previous: Path, current: Path, max_examples: int = 100) -> dict:
    """Compare normalized patent records without loading both releases at once."""
    if max_examples < 1:
        raise ValueError("max_examples must be at least 1")
    old = {record["patent_id"]: _record_digest(record) for record in iter_bulk_patent_index(previous)}
    new = {record["patent_id"]: _record_digest(record) for record in iter_bulk_patent_index(current)}
    new_ids = sorted(set(new) - set(old))
    removed_ids = sorted(set(old) - set(new))
    changed_ids = sorted(key for key in set(old) & set(new) if old[key] != new[key])
    return {
        "previous_path": str(previous),
        "current_path": str(current),
        "previous_record_count": len(old),
        "current_record_count": len(new),
        "new_count": len(new_ids),
        "changed_count": len(changed_ids),
        "removed_count": len(removed_ids),
        "new_patent_ids": new_ids[:max_examples],
        "changed_patent_ids": changed_ids[:max_examples],
        "removed_patent_ids": removed_ids[:max_examples],
        "examples_truncated": any(len(values) > max_examples for values in (new_ids, changed_ids, removed_ids)),
    }


def profile_bulk_release(path: Path, sample_limit: int = 5000, max_age_days: int | None = None) -> dict:
    """Profile release shape, normalized coverage, and optional date freshness."""
    if sample_limit < 1:
        raise ValueError("sample_limit must be at least 1")
    raw_count = 0
    normalized_count = 0
    missing_id = 0
    missing_title = 0
    fields: set[str] = set()
    patent_dates: list[date] = []
    for row in iter_bulk_rows(path):
        raw_count += 1
        if raw_count <= sample_limit:
            fields.update(str(key) for key in row)
        patent_id = next((row.get(key) for key in ("patent_id", "patent_number", "publication_number", "document_number") if row.get(key) not in (None, "")), None)
        title = next((row.get(key) for key in ("patent_title", "title", "invention_title") if row.get(key) not in (None, "")), None)
        if patent_id in (None, ""):
            missing_id += 1
        if title in (None, ""):
            missing_title += 1
        if patent_id not in (None, "") and title not in (None, ""):
            normalized_count += 1
        raw_date = next((row.get(key) for key in ("patent_date", "grant_date", "publication_date", "filing_date") if row.get(key) not in (None, "")), None)
        if raw_date:
            try:
                patent_dates.append(date.fromisoformat(str(raw_date)[:10]))
            except ValueError:
                pass
    latest_date = max(patent_dates).isoformat() if patent_dates else None
    freshness_days = None
    freshness_status = "unknown"
    if latest_date:
        freshness_days = (datetime.now(timezone.utc).date() - date.fromisoformat(latest_date)).days
        freshness_status = "pass" if max_age_days is None or freshness_days <= max_age_days else "fail"
    schema_status = "pass" if any(field in fields for field in ("patent_id", "patent_number", "publication_number", "document_number")) and any(field in fields for field in ("patent_title", "title", "invention_title")) else "fail"
    status = "pass" if raw_count > 0 and normalized_count > 0 and not missing_id and not missing_title and freshness_status != "fail" and schema_status == "pass" else "fail"
    return {
        "path": str(path),
        "status": status,
        "raw_record_count": raw_count,
        "normalized_record_count": normalized_count,
        "missing_patent_id": missing_id,
        "missing_title": missing_title,
        "sampled_fields": sorted(fields),
        "schema_status": schema_status,
        "latest_patent_date": latest_date,
        "freshness_days": freshness_days,
        "freshness_status": freshness_status,
        "sample_limit": sample_limit,
        "max_age_days": max_age_days,
        "coverage": {
            "normalized_rate": normalized_count / raw_count if raw_count else 0.0,
            "patent_id_completeness": 1 - (missing_id / raw_count) if raw_count else 0.0,
            "title_completeness": 1 - (missing_title / raw_count) if raw_count else 0.0,
        },
    }
