"""Dagster definitions for the analyst-gated USPTO ODP refresh path.

Install with ``pip install -e '.[dagster,postgres]'`` and run locally with:
``dagster dev -m diligence_pipelines.orchestration.dagster_defs``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import dagster as dg

from diligence_pipelines.cli import discover_uspto_odp, refresh_uspto_odp
from diligence_pipelines.settings import Settings


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
    output = settings.uspto_odp_discovery_output
    exit_code = discover_uspto_odp(None, output, None, settings)
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
    selection = settings.uspto_odp_reviewed_selection
    output = settings.uspto_odp_refresh_output
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
    selection = settings.uspto_odp_reviewed_selection
    if not selection.exists():
        return dg.SkipReason(f"Waiting for approved selection: {selection}")
    raw = selection.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if context.cursor == digest:
        return dg.SkipReason("Approved selection was already triggered")
    approval = json.loads(raw)
    if approval.get("status") != "approved_for_download":
        return dg.SkipReason("Selection is not analyst-approved for download")
    context.update_cursor(digest)
    return dg.RunRequest(run_key=digest, tags={
        "source": "uspto_odp",
        "approval_reviewer": str(approval.get("reviewer") or "unknown"),
    })


defs = dg.Definitions(
    assets=[uspto_odp_discovery, uspto_odp_approved_refresh],
    jobs=[discovery_job, approved_refresh_job],
    schedules=[discovery_schedule],
    sensors=[approved_uspto_selection_sensor],
)
