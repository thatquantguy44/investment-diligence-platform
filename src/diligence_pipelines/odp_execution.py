"""Durable Dagster attempt state for one analyst-approved USPTO revision."""

from __future__ import annotations

import json
import os
import pwd
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from diligence_pipelines.odp_approval import _json_bytes, _private_dir, _write_immutable, validate_approval
from diligence_pipelines.settings import Settings
from diligence_pipelines.storage import build_storage


def _state_path(settings: Settings, approval_id: str) -> Path:
    uuid.UUID(approval_id)
    return settings.data_root / "uspto" / "execution" / f"{approval_id}.json"


def _write_state(path: Path, state: dict) -> None:
    _private_dir(path.parent)
    with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=".odp-state-", delete=False) as handle:
        temp = Path(handle.name)
        handle.write(_json_bytes(state))
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def load_execution_state(settings: Settings, approval: dict) -> dict:
    path = _state_path(settings, approval["approval_id"])
    if not path.exists():
        return {"approval_id": approval["approval_id"], "candidate_fingerprint": approval["candidate_fingerprint"], "attempt": 0, "status": "pending"}
    state = json.loads(path.read_text())
    if state.get("approval_id") != approval["approval_id"] or state.get("candidate_fingerprint") != approval["candidate_fingerprint"]:
        raise ValueError("USPTO execution state does not match the approved revision")
    if not isinstance(state.get("attempt"), int) or state["attempt"] < 0:
        raise ValueError("USPTO execution attempt is invalid")
    return state


def run_key_for_state(approval: dict, state: dict) -> str | None:
    if state.get("status") not in {"pending", "retry_requested"}:
        return None
    return f"{approval['approval_id']}:{approval['candidate_fingerprint']}:{state['attempt']}"


def record_scheduled(settings: Settings, approval: dict) -> dict:
    state = load_execution_state(settings, approval)
    if run_key_for_state(approval, state) is None:
        raise ValueError("USPTO approval is not awaiting a Dagster run")
    state.update({"status": "scheduled", "updated_at": datetime.now(timezone.utc).isoformat()})
    _write_state(_state_path(settings, approval["approval_id"]), state)
    return state


def record_outcome(settings: Settings, approval: dict, report: dict) -> dict:
    if report.get("status") not in {"prepared", "blocked", "failed"}:
        raise ValueError("USPTO execution outcome must be prepared, blocked, or failed")
    state = load_execution_state(settings, approval)
    state.update({"status": report["status"], "refresh_id": report["refresh_id"], "updated_at": datetime.now(timezone.utc).isoformat()})
    _write_state(_state_path(settings, approval["approval_id"]), state)
    return state


def request_retry(settings: Settings, selection: Path, note: str, *, confirm_interrupted: bool = False) -> dict:
    approval, _ = validate_approval(selection, settings, build_storage(settings))
    actor = pwd.getpwuid(os.geteuid()).pw_name
    if not settings.uspto_odp_reviewer_os_user or actor != settings.uspto_odp_reviewer_os_user:
        raise PermissionError("Current OS user is not the configured USPTO reviewer")
    if not note.strip():
        raise ValueError("Retry rationale is required")
    state = load_execution_state(settings, approval)
    if state["status"] not in {"failed", "blocked"} and not (confirm_interrupted and state["status"] == "scheduled"):
        raise ValueError("Only a failed, blocked, or confirmed interrupted run can be retried")
    retry = {
        "retry_id": str(uuid.uuid4()), "approval_id": approval["approval_id"],
        "candidate_fingerprint": approval["candidate_fingerprint"],
        "previous_status": state["status"], "attempt": state["attempt"] + 1,
        "actor_os_user": actor, "reviewer": approval["reviewer"],
        "note": note.strip(), "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_immutable(settings.data_root / "uspto" / "retries" / f"{retry['retry_id']}.json", _json_bytes(retry))
    state.update({"attempt": retry["attempt"], "status": "retry_requested", "retry_id": retry["retry_id"], "updated_at": retry["requested_at"]})
    _write_state(_state_path(settings, approval["approval_id"]), state)
    return retry
