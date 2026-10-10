from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from diligence_pipelines.contracts import Entity
from diligence_pipelines.quality import validate_entities, validate_research_works
from diligence_pipelines.settings import Settings
from diligence_pipelines.sources import RawCapture, SourceRequest, fetch_gleif_lei, fetch_openalex_works, fetch_sec_submissions, normalize_gleif_alias, normalize_openalex_works, normalize_sec_entity
from diligence_pipelines.storage import build_storage
from diligence_pipelines.technology import derive_topic_observation


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
    return run_sec_watchlist([{"cik": cik}], settings)


def load_watchlist(path: Path) -> list[dict[str, str]]:
    data = yaml.safe_load(path.read_text()) or {}
    entries = data.get("entities", data) if isinstance(data, dict) else data
    if not isinstance(entries, list) or not entries:
        raise ValueError("Watchlist must contain a non-empty 'entities' list")
    normalized = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("cik"):
            raise ValueError("Each watchlist entry requires a cik")
        cik = str(entry["cik"])
        if cik in seen:
            continue
        seen.add(cik)
        normalized.append({key: str(value) for key, value in entry.items() if value is not None})
    return normalized


def run_sec_watchlist(watchlist: list[dict[str, str]], settings: Settings) -> int:
    run_id = str(uuid.uuid4())
    storage = build_storage(settings)
    entities = []
    aliases = []
    raw_uris = []
    hashes = []
    for entry in watchlist:
        capture = fetch_sec_submissions(entry["cik"], settings.sec_user_agent)
        raw_uris.append(storage.write_raw(capture))
        hashes.append(capture.content_sha256)
        entity = Entity(**normalize_sec_entity(capture.payload, run_id), created_at=capture.retrieved_at, first_seen_at=capture.retrieved_at)
        if entry.get("lei"):
            gleif_capture = fetch_gleif_lei(entry["lei"])
            raw_uris.append(storage.write_raw(gleif_capture))
            hashes.append(gleif_capture.content_sha256)
            alias = normalize_gleif_alias(gleif_capture.payload, run_id, entity.entity_id)
            aliases.append(alias)
            entity.identifiers.append({"scheme": "lei", "value": alias["lei"]})
        entities.append(entity)
    quality = validate_entities(entities)
    failed = [result for result in quality if result.status == "fail"]
    if failed:
        print(json.dumps({"run_id": run_id, "status": "blocked", "quality": [item.model_dump(mode="json") for item in quality]}, indent=2))
        return 2
    entity_dicts = [entity.model_dump(mode="json") for entity in entities]
    product = {
        "product_id": "entity_graph",
        "contract_version": "1.0.0",
        "materialization_id": run_id,
        "pipeline_id": "01_entity_graph",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "partition_keys": {"source_id": "sec_edgar", "watchlist_size": len(watchlist)},
        "lineage": {"raw_object_uris": raw_uris, "content_sha256": hashes},
        "location": "storage://curated/01_entity_graph/" + run_id + "/entities",
        "quality": [item.model_dump(mode="json") for item in quality],
        "record_counts": {"entities": len(entity_dicts), "entity_aliases": len(aliases), "unresolved_match_candidates": 0},
    }
    storage.publish_entity_product(run_id, entity_dicts, product, aliases=aliases)
    print(json.dumps({"run_id": run_id, "status": "published", "entity_count": len(entity_dicts), "alias_count": len(aliases), "materialization_id": run_id}, indent=2))
    return 0


def run_technology_talent(query: str, max_results: int, settings: Settings) -> int:
    run_id = str(uuid.uuid4())
    storage = build_storage(settings)
    capture = fetch_openalex_works(query, max_results=max_results)
    raw_uri = storage.write_raw(capture)
    source_record_id = f"source:{capture.content_sha256}"
    records = normalize_openalex_works(capture.payload, run_id, source_record_id)
    quality = validate_research_works(records)
    failed = [result for result in quality if result.status == "fail"]
    if failed:
        print(json.dumps({"run_id": run_id, "status": "blocked", "quality": [item.model_dump(mode="json") for item in quality]}, indent=2))
        return 2
    observations = [derive_topic_observation(records, query, run_id)]
    product = {
        "product_id": "technology_talent_research_works",
        "contract_version": "1.0.0",
        "materialization_id": run_id,
        "pipeline_id": "02_technology_talent",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "partition_keys": {"source_id": "openalex", "query": query, "max_results": max_results},
        "lineage": {"raw_object_uri": raw_uri, "content_sha256": capture.content_sha256, "source_record_id": source_record_id},
        "location": "storage://curated/02_technology_talent/" + run_id + "/research_works",
        "quality": [item.model_dump(mode="json") for item in quality],
        "record_counts": {"research_works": len(records), "technology_topic_observations": len(observations)},
        "limitations": ["OpenAlex is research metadata, not a complete talent or patent database.", "Search results are not evidence of employment or company ownership."],
    }
    storage.publish_research_product(run_id, records, product, observations=observations)
    print(json.dumps({"run_id": run_id, "status": "published", "research_work_count": len(records), "materialization_id": run_id}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="diligence-pipelines")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate-manifests")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("pipeline_id")
    run_parser.add_argument("--input", type=Path)
    run_parser.add_argument("--cik", help="Fetch one SEC EDGAR company-submissions record")
    run_parser.add_argument("--watchlist", type=Path, help="YAML watchlist with entities containing cik and optional lei")
    run_parser.add_argument("--query", help="OpenAlex search query for Pipeline 02")
    run_parser.add_argument("--max-results", type=int, default=25)
    args = parser.parse_args()
    if args.command == "validate-manifests":
        return validate_manifests()
    if args.pipeline_id == "02_technology_talent":
        if not args.query or args.input or args.cik or args.watchlist:
            parser.error("Pipeline 02 requires --query and does not accept Pipeline 01 inputs")
        return run_technology_talent(args.query, args.max_results, Settings.from_env())
    if args.pipeline_id != "01_entity_graph":
        parser.error("Implemented pipelines are 01_entity_graph and 02_technology_talent")
    if sum(value is not None for value in (args.input, args.cik, args.watchlist)) != 1:
        parser.error("Provide exactly one of --input, --cik, or --watchlist")
    settings = Settings.from_env()
    if args.input:
        return run_entity_graph(args.input, settings)
    if args.cik:
        return run_sec_entity_graph(args.cik, settings)
    return run_sec_watchlist(load_watchlist(args.watchlist), settings)


if __name__ == "__main__":
    raise SystemExit(main())
