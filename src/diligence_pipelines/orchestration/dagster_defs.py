"""Dagster definitions for the analyst-gated USPTO ODP refresh path.

Install with ``pip install -e '.[dagster,postgres]'`` and run locally with:
``dagster dev -m diligence_pipelines.orchestration.dagster_defs``.
"""

from __future__ import annotations

import json
from pathlib import Path

import dagster as dg

from diligence_pipelines.cli import discover_uspto_odp, refresh_uspto_odp
from diligence_pipelines.odp_approval import validate_approval
from diligence_pipelines.odp_execution import load_execution_state, record_scheduled, run_key_for_state
from diligence_pipelines.settings import Settings
from diligence_pipelines.storage import build_storage


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _metadata(report: dict) -> dict:
    quality = report.get("quality") or {}
    artifact = report.get("artifact") or {}
    return {
        "status": report.get("status", "unknown"),
        "refresh_id": report.get("refresh_id", ""),
        "changed": bool(artifact.get("changed", False)),
        "source_sha256": artifact.get("content_sha256", ""),
        "freshness_status": quality.get("freshness_status", "unknown"),
        "normalized_record_count": quality.get("normalized_record_count", 0),
        "report_path": report.get("report_path", ""),
    }


@dg.asset(group_name="uspto_odp", compute_kind="python")
def uspto_odp_discovery() -> dg.MaterializeResult:
    """Discover ODP artifacts on a schedule; no selection, download, or ingest occurs here."""
    settings = Settings.from_env()
    output = settings.uspto_odp_discovery_path
    exit_code = discover_uspto_odp(None, None, None, settings)
    if exit_code:
        raise dg.Failure("USPTO ODP discovery did not complete")
    report = _read_json(output)
    return dg.MaterializeResult(metadata={
        "discovery_id": report["discovery_id"],
        "candidate_count": report["candidate_count"],
        "catalog_sha256": report["catalog_sha256"],
        "output": str(output),
    })


@dg.asset(group_name="uspto_odp", compute_kind="python")
def uspto_odp_approved_refresh() -> dg.MaterializeResult:
    """Prepare one already-reviewed release and fail visibly on download or quality issues."""
    settings = Settings.from_env()
    selection = settings.uspto_odp_reviewed_selection_path
    output = settings.uspto_odp_refresh_path
    report_path = Path(str(output) + ".refresh.json")
    exit_code = refresh_uspto_odp(
        selection, output, settings.uspto_odp_previous_file, report_path, None,
        settings.uspto_odp_refresh_max_age_days, 100, settings,
    )
    report = _read_json(report_path)
    report["report_path"] = str(report_path)
    if exit_code:
        raise dg.Failure("USPTO approved refresh was blocked or failed", metadata=_metadata(report))
    return dg.MaterializeResult(metadata=_metadata(report))


discovery_job = dg.define_asset_job("uspto_odp_discovery_job", selection=dg.AssetSelection.assets(uspto_odp_discovery))
approved_refresh_job = dg.define_asset_job("uspto_odp_approved_refresh_job", selection=dg.AssetSelection.assets(uspto_odp_approved_refresh))

discovery_schedule = dg.ScheduleDefinition(
    job=discovery_job,
    cron_schedule="0 */6 * * *",
    name="uspto_odp_discovery_every_six_hours",
)


@dg.sensor(job=approved_refresh_job, minimum_interval_seconds=300)
def approved_uspto_selection_sensor(context):
    """Trigger exactly once per changed analyst-approved selection file.

    This sensor intentionally only observes a pre-existing approval record. It
    cannot select an artifact, grant approval, ingest the index, or materialize
    the patent catalog.
    """
    settings = Settings.from_env()
    selection = settings.uspto_odp_reviewed_selection_path
    if not selection.exists():
        return dg.SkipReason(f"Waiting for approved selection: {selection}")
    try:
        approval, _ = validate_approval(selection, settings, build_storage(settings))
        state = load_execution_state(settings, approval)
    except (ValueError, KeyError, FileNotFoundError, PermissionError) as exc:
        return dg.SkipReason(f"USPTO selection is not valid for a Dagster run: {exc}")
    run_key = run_key_for_state(approval, state)
    if run_key is None:
        return dg.SkipReason(f"USPTO approval is {state['status']}; an explicit retry is required after a failed run")
    if context.cursor == run_key:
        return dg.SkipReason("This approval attempt was already requested")
    record_scheduled(settings, approval)
    context.update_cursor(run_key)
    return dg.RunRequest(run_key=run_key, tags={
        "source": "uspto_odp",
        "approval_reviewer": str(approval.get("reviewer") or "unknown"),
        "approval_id": approval["approval_id"],
        "attempt": str(state["attempt"]),
    })


defs = dg.Definitions(
    assets=[uspto_odp_discovery, uspto_odp_approved_refresh],
    jobs=[discovery_job, approved_refresh_job],
    schedules=[discovery_schedule],
    sensors=[approved_uspto_selection_sensor],
)
