"""Offline, analyst-curated FundComb profile map pilot.

This module never requests FundComb pages. Input is a small, locally held CSV
of profile observations reviewed by an analyst; output is a research report,
not a curated data product or an estimate of the full investor universe.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


FOCUS_AREAS = {"semiconductors", "sensors", "maritime_systems"}
REQUIRED_COLUMNS = {
    "investor_name", "profile_url", "headquarters_country", "focus_area",
    "evidence_excerpt", "evidence_kind", "observed_on",
}
EVIDENCE_KINDS = {"profile_focus", "profile_description"}


def _validate_profile_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc.lower() not in {"fundcomb.com", "www.fundcomb.com"}:
        raise ValueError("profile_url must be an HTTPS FundComb URL")
    if not parsed.path.startswith("/funds/") or len(parsed.path.split("/")) != 3 or not parsed.path.split("/")[2]:
        raise ValueError("profile_url must identify one /funds/<slug> profile")
    if parsed.query or parsed.fragment or parsed.username or parsed.password or parsed.port:
        raise ValueError("profile_url must not contain credentials, query parameters, fragments, or a port")
    return f"https://fundcomb.com{parsed.path.rstrip('/')}"


def load_manual_profiles(path: Path) -> tuple[list[dict], str]:
    payload = path.read_bytes()
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
            raise ValueError(f"CSV requires columns: {', '.join(sorted(REQUIRED_COLUMNS))}")
        rows = []
        seen = set()
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"line {line_number}: unexpected extra column")
            values = {key: (row.get(key) or "").strip() for key in REQUIRED_COLUMNS}
            if not all(values.values()):
                raise ValueError(f"line {line_number}: required fields must be nonempty")
            values["profile_url"] = _validate_profile_url(values["profile_url"])
            if values["focus_area"] not in FOCUS_AREAS:
                raise ValueError(f"line {line_number}: invalid focus_area")
            if values["evidence_kind"] not in EVIDENCE_KINDS:
                raise ValueError(f"line {line_number}: invalid evidence_kind")
            try:
                observed = date.fromisoformat(values["observed_on"])
            except ValueError as exc:
                raise ValueError(f"line {line_number}: observed_on must be YYYY-MM-DD") from exc
            if observed > datetime.now(timezone.utc).date():
                raise ValueError(f"line {line_number}: observed_on is in the future")
            key = (values["profile_url"], values["focus_area"])
            if key in seen:
                raise ValueError(f"line {line_number}: duplicate profile and focus area")
            seen.add(key)
            values["source_id"] = "fundcomb_manual"
            values["signal_type"] = "profile_claim"
            values["review_status"] = "unreviewed"
            values["record_id"] = "fundcomb_manual:" + hashlib.sha256("|".join(key).encode()).hexdigest()[:24]
            rows.append(values)
    if not rows:
        raise ValueError("CSV has no observations")
    return rows, hashlib.sha256(payload).hexdigest()


def build_manual_map(rows: list[dict], input_sha256: str) -> dict:
    by_focus = Counter(row["focus_area"] for row in rows)
    investors = {row["profile_url"] for row in rows}
    return {
        "schema_version": "1.0.0",
        "source_id": "fundcomb_manual",
        "input_sha256": input_sha256,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "research_sample_only",
        "evidence_basis": "analyst_entered_profile_excerpts_not_independently_verified",
        "row_count": len(rows),
        "distinct_investor_count": len(investors),
        "focus_counts": {area: by_focus[area] for area in sorted(FOCUS_AREAS)},
        "headquarters_counts": dict(sorted(Counter(row["headquarters_country"] for row in rows).items())),
        "limitations": [
            "Selected profiles are not a complete or representative investor universe.",
            "Profile statements do not establish a completed investment, funding flow, supplier link, or current investment mandate.",
            "Zero in a focus area means zero curated rows in this sample, not zero market activity.",
        ],
    }


def write_manual_map(input_path: Path, output_dir: Path) -> dict:
    rows, input_sha256 = load_manual_profiles(input_path)
    report = build_manual_map(rows, input_sha256)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "investor_focus_observations.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    (output_dir / "sample_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
