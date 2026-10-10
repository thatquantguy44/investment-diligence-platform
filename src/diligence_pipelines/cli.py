from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from diligence_pipelines.contracts import Entity
from diligence_pipelines.quality import validate_entities
from diligence_pipelines.settings import Settings
from diligence_pipelines.sources import RawCapture, SourceRequest, fetch_sec_submissions, normalize_sec_entity
from diligence_pipelines.storage import build_storage


ROOT = Path(__file__).resolve().parents[2]


def validate_manifests() -> int:
    required = {"pipeline_id", "title", "status", "owner", "purpose", "sources", "outputs", "schedule", "partition_by", "sensitivity", "model_use", "quality_checks"}
    manifests = sorted(ROOT.glob("pipelines/*/manifest.yaml"))
    if not manifests:
        raise SystemExit("No pipeline manifests found")
    for path in manifests:
        data = yaml.safe_load(path.read_text())
        missing = sorted(required - set(data or {}))
        if missing:
            raise SystemExit(f"{path}: missing fields: {', '.join(missing)}")
        if data["status"] not in {"prototype", "pilot", "active", "paused", "retired"}:
            raise SystemExit(f"{path}: invalid status")
        for source in data["sources"]:
            if not source.get("source_id") or not source.get("allowed_domains"):
                raise SystemExit(f"{path}: source requires source_id and allowed_domains")
    print(f"validated {len(manifests)} manifest(s)")
    return 0


def run_entity_graph(input_path: Path, settings: Settings) -> int:
    run_id = str(uuid.uuid4())
    storage = build_storage(settings)
    payload = input_path.read_bytes()
    request = SourceRequest("synthetic_fixture", input_path.resolve().as_uri())
    capture = RawCapture(request=request, payload=payload, status_code=200, adapter_version="fixture-1.0.0")
    raw_uri = storage.write_raw(capture)
    records = []
    for line in input_path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        records.append(Entity(
            record_id=f"entity:{row['entity_id']}", entity_id=row["entity_id"],
            schema_version="1.0.0", pipeline_id="01_entity_graph", source_id="synthetic_fixture",
            run_id=run_id, canonical_name=row["canonical_name"], jurisdiction=row.get("jurisdiction"),
            entity_type=row.get("entity_type", "organization"),
            identifiers=row.get("identifiers", []), entity_status=row.get("entity_status", "unknown"),
        ))
    quality = validate_entities(records)
    failed = [result for result in quality if result.status == "fail"]
    if failed:
        print(json.dumps({"run_id": run_id, "status": "blocked", "quality": [item.model_dump(mode="json") for item in quality]}, indent=2))
        return 2
    entity_dicts = [item.model_dump(mode="json") for item in records]
    product = {
        "product_id": "entity_graph",
        "contract_version": "1.0.0",
        "materialization_id": run_id,
        "pipeline_id": "01_entity_graph",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "partition_keys": {"source_id": "synthetic_fixture"},
        "lineage": {"raw_object_uri": raw_uri, "content_sha256": capture.content_sha256},
        "location": "storage://curated/01_entity_graph/" + run_id + "/entities",
        "quality": [item.model_dump(mode="json") for item in quality],
    }
    storage.publish_entity_product(run_id, entity_dicts, product)
    print(json.dumps({"run_id": run_id, "status": "published", "entity_count": len(records), "materialization_id": run_id}, indent=2))
    return 0


def run_sec_entity_graph(cik: str, settings: Settings) -> int:
    run_id = str(uuid.uuid4())
    storage = build_storage(settings)
    capture = fetch_sec_submissions(cik, settings.sec_user_agent)
    raw_uri = storage.write_raw(capture)
    entity = Entity(**normalize_sec_entity(capture.payload, run_id), created_at=capture.retrieved_at, first_seen_at=capture.retrieved_at)
    quality = validate_entities([entity])
    failed = [result for result in quality if result.status == "fail"]
    if failed:
        print(json.dumps({"run_id": run_id, "status": "blocked", "quality": [item.model_dump(mode="json") for item in quality]}, indent=2))
        return 2
    entity_dict = entity.model_dump(mode="json")
    product = {
        "product_id": "entity_graph",
        "contract_version": "1.0.0",
        "materialization_id": run_id,
        "pipeline_id": "01_entity_graph",
        "as_of": capture.retrieved_at.isoformat(),
        "partition_keys": {"source_id": "sec_edgar", "cik": entity.identifiers[0]["value"]},
        "lineage": {"raw_object_uri": raw_uri, "content_sha256": capture.content_sha256},
        "location": "storage://curated/01_entity_graph/" + run_id + "/entities",
        "quality": [item.model_dump(mode="json") for item in quality],
    }
    storage.publish_entity_product(run_id, [entity_dict], product)
    print(json.dumps({"run_id": run_id, "status": "published", "entity_count": 1, "materialization_id": run_id, "entity": entity_dict}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="diligence-pipelines")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate-manifests")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("pipeline_id")
    run_parser.add_argument("--input", type=Path)
    run_parser.add_argument("--cik", help="Fetch one SEC EDGAR company-submissions record")
    args = parser.parse_args()
    if args.command == "validate-manifests":
        return validate_manifests()
    if args.pipeline_id != "01_entity_graph":
        parser.error("Only 01_entity_graph is implemented in the initial buildout")
    if bool(args.input) == bool(args.cik):
        parser.error("Provide exactly one of --input or --cik")
    settings = Settings.from_env()
    return run_entity_graph(args.input, settings) if args.input else run_sec_entity_graph(args.cik, settings)


if __name__ == "__main__":
    raise SystemExit(main())
