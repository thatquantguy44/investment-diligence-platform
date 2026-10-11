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
from diligence_pipelines.sources import RawCapture, SourceRequest, download_bulk_artifact, enrich_bulk_patents, fetch_gleif_lei, fetch_openalex_works, fetch_patents, fetch_patents_from_bulk_file, fetch_sec_submissions, iter_bulk_patent_index, load_bulk_patent_index, normalize_gleif_alias, normalize_openalex_works, normalize_patents, normalize_sec_entity, search_odp_products, select_catalog_artifact
from diligence_pipelines.storage import build_storage
from diligence_pipelines.technology import derive_institution_edges, derive_topic_observation


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


def download_uspto_bulk(url: str, output: Path, settings: Settings) -> int:
    artifact = download_bulk_artifact(url, output, api_key=settings.uspto_api_key)
    print(json.dumps({"status": "downloaded", **artifact.__dict__}, indent=2))
    return 0


def search_uspto_odp(query: str, output: Path | None, settings: Settings) -> int:
    if not settings.uspto_api_key:
        raise SystemExit("USPTO_API_KEY is required for ODP catalog access")
    payload = search_odp_products(query, settings.uspto_api_key, settings.uspto_odp_catalog_url)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
        print(json.dumps({"status": "saved", "output": str(output), "bytes": len(payload)}, indent=2))
    else:
        print(payload.decode("utf-8"))
    return 0


def select_uspto_odp(catalog: Path, contains: str, output: Path) -> int:
    selection = select_catalog_artifact(catalog.read_bytes(), contains)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(selection, indent=2) + "\n")
    print(json.dumps({"status": "selected", "output": str(output), "download_url": selection["download_url"]}, indent=2))
    return 0


def index_uspto_bulk(path: Path, limit: int | None, settings: Settings) -> int:
    records, metadata = load_bulk_patent_index(path, limit=limit)
    storage = build_storage(settings)
    indexed = storage.upsert_patent_index(records, metadata)
    print(json.dumps({"status": "indexed", "indexed_count": indexed, **metadata}, indent=2))
    return 0


def search_uspto_index(query: str, limit: int, settings: Settings) -> int:
    storage = build_storage(settings)
    results = storage.search_patent_index(query, limit=limit)
    print(json.dumps({"query": query, "count": len(results), "results": results}, indent=2))
    return 0


def enrich_uspto_index(patent_file: Path, abstract_file: Path | None, assignee_file: Path | None, limit: int | None, settings: Settings) -> int:
    records, metadata = load_bulk_patent_index(patent_file, limit=limit)
    records = enrich_bulk_patents(records, abstract_file, assignee_file)
    metadata["abstract_source_path"] = str(abstract_file) if abstract_file else None
    metadata["assignee_source_path"] = str(assignee_file) if assignee_file else None
    storage = build_storage(settings)
    enriched = storage.upsert_patent_index(records, metadata)
    print(json.dumps({"status": "enriched", "enriched_count": enriched, **metadata}, indent=2))
    return 0


def ingest_uspto_bulk(patent_file: Path, abstract_file: Path | None, assignee_file: Path | None, limit: int | None, batch_size: int, settings: Settings) -> int:
    storage = build_storage(settings)
    source_hash = __import__("hashlib").sha256(patent_file.read_bytes()).hexdigest()
    metadata = {"source_path": str(patent_file), "source_file_sha256": source_hash, "adapter_version": "uspto-odp-batch-1.0.0", "limit": limit}
    records = []
    target_ids = set()
    total = 0
    for record in iter_bulk_patent_index(patent_file, limit=limit):
        target_ids.add(record["patent_id"])
        records.append(record)
        if len(records) >= batch_size:
            storage.upsert_patent_index(records, {**metadata, "record_count": len(records)})
            total += len(records)
            records = []
    if records:
        storage.upsert_patent_index(records, {**metadata, "record_count": len(records)})
        total += len(records)
    enriched = 0
    if hasattr(storage, "stage_patent_enrichment"):
        from diligence_pipelines.sources.uspto_bulk import iter_bulk_rows
        for path, field in ((abstract_file, "abstract"), (assignee_file, "assignee_name")):
            if path is None:
                continue
            rows = []
            remaining = set(target_ids) if limit is not None else None
            for row in iter_bulk_rows(path):
                patent_id = row.get("patent_id")
                if remaining is not None and str(patent_id) not in remaining:
                    continue
                value = row.get("patent_abstract") if field == "abstract" else row.get("disambig_assignee_organization")
                if patent_id and value:
                    rows.append({"patent_id": patent_id, field: value})
                    if remaining is not None:
                        remaining.discard(str(patent_id))
                if len(rows) >= batch_size:
                    storage.stage_patent_enrichment(rows, source_hash)
                    rows = []
                if remaining is not None and not remaining:
                    break
            if rows:
                storage.stage_patent_enrichment(rows, source_hash)
        enriched = storage.apply_patent_enrichment(source_hash)
    print(json.dumps({"status": "batch_ingested", "indexed_count": total, "enriched_count": enriched, **metadata}, indent=2))
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


def run_technology_talent(query: str, max_results: int, patent_fixture: Path | None, patent_bulk_file: Path | None, patent_source: str, settings: Settings) -> int:
    run_id = str(uuid.uuid4())
    storage = build_storage(settings)
    capture = fetch_openalex_works(query, max_results=max_results)
    raw_uri = storage.write_raw(capture)
    source_record_id = f"source:{capture.content_sha256}"
    records = normalize_openalex_works(capture.payload, run_id, source_record_id)
    institution_edges = derive_institution_edges(records, run_id)
    if patent_fixture and patent_bulk_file:
        raise SystemExit("Use only one of --patent-fixture or --patent-bulk-file")
    patent_capture = None
    if patent_source == "index" or (patent_source == "auto" and settings.storage_backend == "postgres" and not patent_fixture and not patent_bulk_file):
        indexed = storage.search_patent_index(query, limit=max_results)
        if not indexed:
            if patent_source == "index":
                raise SystemExit("No matching patents found in diligence.patent_index")
        else:
            patents = []
            for row in indexed:
                patent = {"patent_id": row["patent_id"], "patent_title": row["title"], "patent_date": row.get("patent_date"), "patent_type": row.get("patent_type")}
                if row.get("abstract"):
                    patent["patent_abstract"] = row["abstract"]
                if row.get("assignee_name"):
                    patent["assignees"] = [{"assignee_organization": row["assignee_name"]}]
                patents.append(patent)
            patent_payload = json.dumps({"patents": patents}, separators=(",", ":")).encode()
            patent_capture = RawCapture(SourceRequest("uspto_patents_index", "postgresql://diligence/patent_index", {"query": query, "max_results": str(max_results)}), patent_payload, status_code=200, adapter_version="patent-index-1.0.0")
    if patent_capture is None and patent_fixture:
        patent_payload = patent_fixture.read_bytes()
        patent_capture = RawCapture(SourceRequest("uspto_patents_fixture", patent_fixture.resolve().as_uri()), patent_payload, status_code=200, adapter_version="patent-fixture-1.0.0")
    elif patent_capture is None and patent_bulk_file:
        patent_capture = fetch_patents_from_bulk_file(patent_bulk_file, query, max_results=max_results)
    elif patent_capture is None:
        if not settings.uspto_api_key:
            raise SystemExit("USPTO_API_KEY is required for live patent collection; use --patent-fixture for offline tests")
        patent_capture = fetch_patents(query, settings.uspto_api_key, max_results=max_results, api_url=settings.uspto_api_url)
    patent_uri = storage.write_raw(patent_capture)
    patent_source_record_id = f"source:{patent_capture.content_sha256}"
    patent_records, assignments, inventor_edges = normalize_patents(patent_capture.payload, run_id, patent_source_record_id)
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
        "lineage": {"raw_object_uris": [raw_uri, patent_uri], "content_sha256": [capture.content_sha256, patent_capture.content_sha256], "source_record_ids": [source_record_id, patent_source_record_id]},
        "location": "storage://curated/02_technology_talent/" + run_id + "/research_works",
        "quality": [item.model_dump(mode="json") for item in quality],
        "record_counts": {"research_works": len(records), "technology_topic_observations": len(observations), "patent_records": len(patent_records), "patent_assignments": len(assignments), "inventor_edges": len(inventor_edges), "institution_edges": len(institution_edges)},
        "limitations": ["OpenAlex and USPTO metadata are evidence sources, not evidence of employment, ownership, or technology quality.", "Inventor and institution relationships do not establish employment by a target company."],
    }
    storage.publish_research_product(run_id, records, product, observations=observations, patent_records=patent_records, assignments=assignments, inventor_edges=inventor_edges, institution_edges=institution_edges)
    print(json.dumps({"run_id": run_id, "status": "published", "research_work_count": len(records), "patent_count": len(patent_records), "materialization_id": run_id}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="diligence-pipelines")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate-manifests")
    download_parser = subparsers.add_parser("download-uspto-bulk")
    download_parser.add_argument("--url", required=True, help="Official USPTO ODP artifact URL")
    download_parser.add_argument("--output", type=Path, required=True, help="Local artifact path")
    catalog_parser = subparsers.add_parser("search-uspto-odp")
    catalog_parser.add_argument("--query", required=True, help="ODP product title query")
    catalog_parser.add_argument("--output", type=Path, help="Optional JSON output path")
    select_parser = subparsers.add_parser("select-uspto-odp")
    select_parser.add_argument("--catalog", type=Path, required=True, help="Catalog JSON returned by search-uspto-odp")
    select_parser.add_argument("--contains", required=True, help="Text that must identify exactly one catalog item/file")
    select_parser.add_argument("--output", type=Path, required=True, help="Selection manifest path")
    patent_search_parser = subparsers.add_parser("search-uspto-index")
    patent_search_parser.add_argument("--query", required=True)
    patent_search_parser.add_argument("--limit", type=int, default=25)
    index_parser = subparsers.add_parser("index-uspto-bulk")
    index_parser.add_argument("--file", type=Path, required=True, help="Downloaded USPTO ODP bulk artifact")
    index_parser.add_argument("--limit", type=int, help="Optional bounded pilot row count")
    enrich_parser = subparsers.add_parser("enrich-uspto-index")
    enrich_parser.add_argument("--patent-file", type=Path, required=True)
    enrich_parser.add_argument("--abstract-file", type=Path)
    enrich_parser.add_argument("--assignee-file", type=Path)
    enrich_parser.add_argument("--limit", type=int, help="Optional bounded pilot row count")
    batch_parser = subparsers.add_parser("ingest-uspto-bulk")
    batch_parser.add_argument("--patent-file", type=Path, required=True)
    batch_parser.add_argument("--abstract-file", type=Path)
    batch_parser.add_argument("--assignee-file", type=Path)
    batch_parser.add_argument("--limit", type=int)
    batch_parser.add_argument("--batch-size", type=int, default=5000)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("pipeline_id")
    run_parser.add_argument("--input", type=Path)
    run_parser.add_argument("--cik", help="Fetch one SEC EDGAR company-submissions record")
    run_parser.add_argument("--watchlist", type=Path, help="YAML watchlist with entities containing cik and optional lei")
    run_parser.add_argument("--query", help="OpenAlex search query for Pipeline 02")
    run_parser.add_argument("--max-results", type=int, default=25)
    run_parser.add_argument("--patent-fixture", type=Path, help="Synthetic USPTO response for offline Pipeline 02 tests")
    run_parser.add_argument("--patent-bulk-file", type=Path, help="Downloaded USPTO ODP bulk file (JSON, JSONL, CSV, or ZIP) to search locally")
    run_parser.add_argument("--patent-source", choices=("auto", "index", "api"), default="auto", help="Patent source; auto uses PostgreSQL index when configured")
    args = parser.parse_args()
    if args.command == "validate-manifests":
        return validate_manifests()
    if args.command == "download-uspto-bulk":
        return download_uspto_bulk(args.url, args.output, Settings.from_env())
    if args.command == "search-uspto-odp":
        return search_uspto_odp(args.query, args.output, Settings.from_env())
    if args.command == "select-uspto-odp":
        return select_uspto_odp(args.catalog, args.contains, args.output)
    if args.command == "search-uspto-index":
        return search_uspto_index(args.query, args.limit, Settings.from_env())
    if args.command == "index-uspto-bulk":
        return index_uspto_bulk(args.file, args.limit, Settings.from_env())
    if args.command == "enrich-uspto-index":
        return enrich_uspto_index(args.patent_file, args.abstract_file, args.assignee_file, args.limit, Settings.from_env())
    if args.command == "ingest-uspto-bulk":
        return ingest_uspto_bulk(args.patent_file, args.abstract_file, args.assignee_file, args.limit, args.batch_size, Settings.from_env())
    if args.pipeline_id == "02_technology_talent":
        if not args.query or args.input or args.cik or args.watchlist:
            parser.error("Pipeline 02 requires --query and does not accept Pipeline 01 inputs")
        return run_technology_talent(args.query, args.max_results, args.patent_fixture, args.patent_bulk_file, args.patent_source, Settings.from_env())
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
