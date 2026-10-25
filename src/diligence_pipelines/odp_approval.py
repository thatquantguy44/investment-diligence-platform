"""Filesystem-backed, revision-bound USPTO ODP review records."""

from __future__ import annotations

import hashlib
import json
import os
import pwd
import stat
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from diligence_pipelines.settings import Settings
from diligence_pipelines.sources.uspto_odp import select_odp_candidate


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError(f"Approval evidence directory is not private: {path}")


def _write_immutable(path: Path, payload: bytes) -> None:
    _private_dir(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as destination:
            destination.write(payload)
            destination.flush()
            os.fchmod(destination.fileno(), 0o400)
            os.fsync(destination.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _identifier(value: str) -> str:
    parsed = uuid.UUID(value)
    if str(parsed) != value:
        raise ValueError("Invalid approval or discovery identifier")
    return value


def discovery_record_path(data_root: Path, discovery_id: str) -> Path:
    return data_root / "uspto" / "discoveries" / f"{_identifier(discovery_id)}.json"


def approval_record_path(data_root: Path, approval_id: str) -> Path:
    return data_root / "uspto" / "approvals" / f"{_identifier(approval_id)}.json"


def record_discovery_snapshot(report: dict, data_root: Path) -> Path:
    path = discovery_record_path(data_root, report["discovery_id"])
    _write_immutable(path, _json_bytes(report))
    return path


def _verified_discovery(payload: bytes, settings: Settings, storage) -> tuple[dict, dict]:
    report = json.loads(payload)
    if report.get("schema_version") != "1.0.0" or report.get("status") != "discovered" or report.get("completion_status") != "complete":
        raise ValueError("Discovery snapshot is incomplete or blocked")
    candidates = report.get("candidates")
    if report.get("candidate_count") != 1 or not isinstance(candidates, list) or len(candidates) != 1:
        raise ValueError("Discovery snapshot must contain exactly one candidate")
    source_id = "uspto_odp"
    if not str(report.get("catalog_uri", "")).startswith("https://api.uspto.gov/"):
        if settings.environment != "test":
            raise ValueError("Fixture discovery cannot be approved for a live refresh")
        source_id = "synthetic_fixture"
    search_hash = report.get("search_capture_sha256")
    detail_hash = report.get("detail_capture_sha256")
    if not isinstance(search_hash, str) or not isinstance(detail_hash, str):
        raise ValueError("Discovery snapshot lacks source capture hashes")
    search = storage.read_raw(search_hash, source_id)
    detail = storage.read_raw(detail_hash, source_id)
    if _sha(search) != search_hash or _sha(detail) != detail_hash or report.get("catalog_sha256") != search_hash:
        raise ValueError("Discovery source capture was modified")
    expected = select_odp_candidate(search, detail, settings.uspto_odp_product_identifier, settings.uspto_odp_artifact_name, settings.uspto_odp_policy_limits)
    candidate = candidates[0]
    for key in ("logical_artifact_id", "candidate_fingerprint", "approval_policy_digest", "product_identifier", "artifact_name", "download_url", "size_bytes", "file_release_at", "file_modified_at", "provider_checksum", "policy_version"):
        if candidate.get(key) != expected.get(key):
            raise ValueError(f"Discovery candidate was modified or policy changed: {key}")
    if candidate.get("discovery_id") != report.get("discovery_id") or candidate.get("search_capture_sha256") != search_hash or candidate.get("detail_capture_sha256") != detail_hash:
        raise ValueError("Discovery candidate lacks matching lineage")
    return report, candidate


def _active_pointer(approval: dict, record_sha256: str) -> dict:
    return {key: approval[key] for key in ("status", "approval_id", "discovery_id", "candidate_fingerprint", "reviewer", "actor_os_user")} | {"approval_record_sha256": record_sha256}


def approve_candidate(discovery_path: Path, candidate_index: int, reviewer: str, note: str, output: Path, settings: Settings, storage) -> dict:
    if not settings.uspto_odp_reviewer_name or not settings.uspto_odp_reviewer_os_user:
        raise PermissionError("USPTO reviewer identity is not configured")
    actor = pwd.getpwuid(os.geteuid()).pw_name
    if actor != settings.uspto_odp_reviewer_os_user or reviewer != settings.uspto_odp_reviewer_name:
        raise PermissionError("Current OS user is not the configured USPTO reviewer")
    if not note.strip():
        raise ValueError("Review rationale is required")
    payload = discovery_path.read_bytes()
    report = json.loads(payload)
    snapshot = discovery_record_path(settings.data_root, report["discovery_id"])
    if payload != snapshot.read_bytes():
        raise ValueError("Discovery report was modified after its immutable snapshot")
    report, candidate = _verified_discovery(payload, settings, storage)
    if candidate_index != 0:
        raise ValueError("Candidate index does not identify the exact USPTO artifact")
    approval = {
        "schema_version": "1.0.0", "status": "approved_for_download", "approval_id": str(uuid.uuid4()),
        "reviewed_at": datetime.now(timezone.utc).isoformat(), "reviewer": reviewer,
        "actor_os_user": actor, "review_note": note.strip(), "discovery_id": report["discovery_id"],
        "discovery_sha256": _sha(payload), "logical_artifact_id": candidate["logical_artifact_id"],
        "candidate_fingerprint": candidate["candidate_fingerprint"], "policy_version": candidate["policy_version"],
        "approval_policy_digest": candidate["approval_policy_digest"],
        "search_capture_sha256": candidate["search_capture_sha256"],
        "detail_capture_sha256": candidate["detail_capture_sha256"],
        "product_identifier": candidate["product_identifier"], "artifact_name": candidate["artifact_name"],
        "download_url": candidate["download_url"], "size_bytes": candidate["size_bytes"],
    }
    approval_payload = _json_bytes(approval)
    _write_immutable(approval_record_path(settings.data_root, approval["approval_id"]), approval_payload)
    pointer = _active_pointer(approval, _sha(approval_payload))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="wb", dir=output.parent, prefix=".odp-approval-", delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(_json_bytes(pointer))
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temp_path, output)
    finally:
        temp_path.unlink(missing_ok=True)
    return pointer


def validate_approval(selection_path: Path, settings: Settings, storage) -> tuple[dict, dict]:
    if stat.S_IMODE(selection_path.stat().st_mode) & 0o077:
        raise PermissionError("Active USPTO approval pointer is not private")
    active = json.loads(selection_path.read_text())
    if active.get("status") != "approved_for_download" or not active.get("approval_id") or not active.get("approval_record_sha256"):
        raise ValueError("Legacy or incomplete USPTO approval is not valid for download")
    record = approval_record_path(settings.data_root, active["approval_id"])
    if stat.S_IMODE(record.parent.stat().st_mode) & 0o077:
        raise PermissionError("USPTO approval directory is not private")
    if stat.S_IMODE(record.stat().st_mode) & 0o077:
        raise PermissionError("Immutable USPTO approval record is not private")
    payload = record.read_bytes()
    if _sha(payload) != active["approval_record_sha256"]:
        raise ValueError("Immutable USPTO approval record was modified")
    approval = json.loads(payload)
    if active != _active_pointer(approval, _sha(payload)):
        raise ValueError("Active USPTO approval pointer was modified")
    if approval.get("reviewer") != settings.uspto_odp_reviewer_name or approval.get("actor_os_user") != settings.uspto_odp_reviewer_os_user:
        raise ValueError("USPTO approval reviewer no longer matches configured identity")
    snapshot = discovery_record_path(settings.data_root, approval["discovery_id"])
    if stat.S_IMODE(snapshot.parent.stat().st_mode) & 0o077:
        raise PermissionError("USPTO discovery directory is not private")
    if stat.S_IMODE(snapshot.stat().st_mode) & 0o077:
        raise PermissionError("Approved discovery snapshot is not private")
    discovery_payload = snapshot.read_bytes()
    if _sha(discovery_payload) != approval["discovery_sha256"]:
        raise ValueError("Approved discovery snapshot was modified")
    report, candidate = _verified_discovery(discovery_payload, settings, storage)
    for key in ("discovery_id", "logical_artifact_id", "candidate_fingerprint", "policy_version", "approval_policy_digest", "search_capture_sha256", "detail_capture_sha256", "product_identifier", "artifact_name", "download_url", "size_bytes"):
        expected = report["discovery_id"] if key == "discovery_id" else candidate.get(key)
        if approval.get(key) != expected:
            raise ValueError(f"Approval no longer matches candidate or current policy: {key}")
    return approval, candidate


def validate_refresh_policy(candidate: dict, settings: Settings, max_age_days: int | None) -> None:
    limits = settings.uspto_odp_policy_limits
    if any(value is None for value in limits.values()):
        raise ValueError("Analyst-reviewed USPTO size and freshness limits are required before download")
    minimum = limits["min_size_bytes"]
    maximum = limits["max_size_bytes"]
    release_limit = limits["max_release_age_days"]
    if minimum < 1 or maximum < minimum or release_limit < 0 or limits["max_patent_age_days"] < 0:
        raise ValueError("Invalid USPTO size or freshness policy")
    if max_age_days is not None and max_age_days != limits["max_patent_age_days"]:
        raise ValueError("CLI patent freshness override differs from approved policy")
    if not minimum <= candidate["size_bytes"] <= maximum:
        raise ValueError("USPTO artifact size is outside approved policy bounds")
    release = candidate.get("file_release_at")
    if not isinstance(release, str):
        raise ValueError("USPTO artifact has no release date")
    release_day = date.fromisoformat(release[:10])
    age_days = (datetime.now(timezone.utc).date() - release_day).days
    if age_days < 0 or age_days > release_limit:
        raise ValueError("USPTO release date is outside approved freshness bounds")
