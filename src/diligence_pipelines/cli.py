from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

from diligence_pipelines.awards import award_coverage_report, derive_award_outputs, load_award_sector
from diligence_pipelines.contracts import Entity
from diligence_pipelines.docs_validation import validate_docs
from diligence_pipelines.entities import load_entity_candidates
from diligence_pipelines.events import RuleBasedEventExtractor, derive_event_outputs, event_coverage_report, load_event_query
from diligence_pipelines.quality import validate_awards, validate_entities, validate_event_candidates, validate_patent_records, validate_research_works, validate_trade_flows
from diligence_pipelines.settings import Settings
from diligence_pipelines.sources import RawCapture, SourceRequest, comtrade_response_metadata, compare_bulk_releases, discover_catalog_artifacts, download_bulk_artifact, enrich_bulk_patents, fetch_comtrade, fetch_gleif_lei, fetch_openalex_works, fetch_patents, fetch_patents_from_bulk_file, fetch_sec_submissions, iter_bulk_patent_index, load_bulk_patent_index, load_comtrade_fixture, normalize_cik, normalize_gleif_alias, normalize_lei, normalize_openalex_works, normalize_patents, normalize_sec_entity, normalize_trade_flows, profile_bulk_release, review_catalog_artifact, search_odp_products, select_catalog_artifact
from diligence_pipelines.sources.gdelt import fetch_gdelt_articles, gdelt_response_metadata, load_gdelt_fixture, normalize_gdelt_articles
from diligence_pipelines.sources.usaspending import award_search_metadata, fetch_award_search, fetch_award_transactions, load_usaspending_fixture, normalize_award_transactions, normalize_awards
from diligence_pipelines.storage import build_storage
from diligence_pipelines.technology import derive_institution_edges, derive_topic_observation
from diligence_pipelines.trade import coverage_report, derive_trade_outputs


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


def discover_uspto_odp(query: str | None, output: Path | None, fixture: Path | None, settings: Settings) -> int:
    """Poll the ODP catalog and persist a release-candidate snapshot."""
    product_query = (query or settings.uspto_odp_product_query).strip()
    if fixture:
        payload = fixture.read_bytes()
        catalog_uri = str(fixture)
    else:
        if not settings.uspto_api_key:
            raise SystemExit("USPTO_API_KEY is required for live ODP release discovery")
        payload = search_odp_products(product_query, settings.uspto_api_key, settings.uspto_odp_catalog_url)
        catalog_uri = settings.uspto_odp_catalog_url
    discovered_at = datetime.now(timezone.utc).isoformat()
    report = {
        "discovery_id": str(uuid.uuid4()),
        "status": "discovered",
        "discovered_at": discovered_at,
        "product_query": product_query,
        "catalog_uri": catalog_uri,
        "catalog_sha256": hashlib.sha256(payload).hexdigest(),
        "candidates": discover_catalog_artifacts(payload, product_query),
    }
    report["candidate_count"] = len(report["candidates"])
    destination = output or settings.uspto_odp_discovery_output
    if not destination.is_absolute() and output is not None:
        destination = settings.data_root / destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n")
    storage = build_storage(settings)
    storage.record_uspto_odp_discovery(report)
    print(json.dumps({"status": "discovered", "output": str(destination), "candidate_count": report["candidate_count"], "catalog_sha256": report["catalog_sha256"]}, indent=2))
    return 0


def select_uspto_odp(catalog: Path, contains: str, output: Path) -> int:
    selection = select_catalog_artifact(catalog.read_bytes(), contains)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(selection, indent=2) + "\n")
    print(json.dumps({"status": "selected", "output": str(output), "download_url": selection["download_url"]}, indent=2))
    return 0


def review_uspto_odp(discovery: Path, candidate_index: int, reviewer: str, note: str, output: Path) -> int:
    selection = review_catalog_artifact(json.loads(discovery.read_text()), candidate_index=candidate_index, reviewer=reviewer, note=note)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(selection, indent=2) + "\n")
    print(json.dumps({"status": selection["status"], "output": str(output), "download_url": selection["download_url"], "reviewer": reviewer}, indent=2))
    return 0


def refresh_uspto_odp(selection: Path, output: Path, previous: Path | None, report_output: Path | None, quality_output: Path | None, max_age_days: int | None, max_examples: int, settings: Settings) -> int:
    """Prepare a reviewed ODP release without changing the indexed database."""
    approval = json.loads(selection.read_text())
    if approval.get("status") != "approved_for_download":
        raise SystemExit("ODP selection must have status approved_for_download")
    url = approval.get("download_url")
    if not isinstance(url, str):
        raise SystemExit("ODP selection is missing download_url")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_handle = tempfile.NamedTemporaryFile(prefix=".odp-download-", suffix=output.suffix, dir=output.parent, delete=False)
    temp_path = Path(temp_handle.name)
    temp_handle.close()
    try:
        artifact = download_bulk_artifact(url, temp_path, api_key=settings.uspto_api_key)
        new_sha = artifact.content_sha256
        existing_sha = None
        sidecar = Path(str(output) + ".json")
        if sidecar.exists():
            existing_sha = json.loads(sidecar.read_text()).get("content_sha256")
        changed = existing_sha != new_sha or not output.exists()
        if changed:
            temp_path.replace(output)
            Path(str(temp_path) + ".json").unlink(missing_ok=True)
            sidecar.write_text(json.dumps({**artifact.__dict__, "path": str(output)}, indent=2) + "\n")
        else:
            temp_path.unlink(missing_ok=True)
            Path(str(temp_path) + ".json").unlink(missing_ok=True)
        quality = profile_bulk_release(output, max_age_days=max_age_days)
        previous_quality = profile_bulk_release(previous, max_age_days=max_age_days) if previous and previous.exists() and changed else None
        diff = compare_bulk_releases(previous, output, max_examples=max_examples) if previous and previous.exists() and changed else None
        report = {
            "status": "prepared" if quality["status"] == "pass" else "blocked",
            "prepared_at": datetime.now(timezone.utc).isoformat(),
            "selection": approval,
            "artifact": {**artifact.__dict__, "path": str(output), "changed": changed},
            "quality": quality,
            "previous_quality": previous_quality,
            "diff": diff,
            "ingestion_status": "not_started",
            "ingestion_command": f"PYTHONPATH=src python -m diligence_pipelines.cli ingest-uspto-bulk --patent-file {output}",
        }
        report_path = report_output or Path(str(output) + ".refresh.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
        if quality_output:
            quality_output.parent.mkdir(parents=True, exist_ok=True)
            quality_output.write_text(json.dumps(quality, indent=2) + "\n")
        print(json.dumps({"status": report["status"], "output": str(output), "changed": changed, "report": str(report_path), "ingestion_status": "not_started"}, indent=2))
        return 0 if report["status"] == "prepared" else 2
    finally:
        temp_path.unlink(missing_ok=True)
        Path(str(temp_path) + ".json").unlink(missing_ok=True)


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


def materialize_patent_catalog(settings: Settings) -> int:
    """Backfill the deduplicated patent catalog from the loaded USPTO index."""
    storage = build_storage(settings)
    if not hasattr(storage, "materialize_patent_catalog"):
        raise SystemExit("Selected storage backend does not support patent catalog materialization")
    count = storage.materialize_patent_catalog()
    print(json.dumps({"status": "materialized", "patent_catalog_rows": count}, indent=2))
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
        normalize_cik(cik)
        if entry.get("lei"):
            normalize_lei(str(entry["lei"]))
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


def run_technology_talent(query: str, max_results: int, openalex_fixture: Path | None, patent_fixture: Path | None, patent_bulk_file: Path | None, patent_source: str, settings: Settings) -> int:
    run_id = str(uuid.uuid4())
    storage = build_storage(settings)
    if openalex_fixture:
        capture = RawCapture(
            SourceRequest("openalex_fixture", openalex_fixture.resolve().as_uri(), {"query": query, "max_results": str(max_results)}),
            openalex_fixture.read_bytes(), status_code=200, adapter_version="openalex-fixture-1.0.0",
        )
    else:
        capture = fetch_openalex_works(query, max_results=max_results, email=settings.openalex_email)
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
    quality = validate_research_works(records) + validate_patent_records(patent_records)
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


def run_trade_exposure(period: str, reporter_code: str, partner_code: str, flow_code: str, hs_codes: list[str], trade_fixture: Path | None, settings: Settings) -> int:
    run_id = str(uuid.uuid4())
    storage = build_storage(settings)
    if trade_fixture:
        capture = load_comtrade_fixture(trade_fixture.read_bytes(), source_uri=trade_fixture.resolve().as_uri())
    else:
        capture = fetch_comtrade(period=period, reporter_code=reporter_code, partner_code=partner_code, flow_code=flow_code, hs_codes=hs_codes, api_keys=settings.comtrade_api_keys, api_url=settings.comtrade_api_url)
    raw_uri = storage.write_raw(capture)
    source_record_id = f"source:{capture.content_sha256}"
    source_metadata = comtrade_response_metadata(capture.payload)
    records = normalize_trade_flows(capture.payload, run_id, source_record_id, set(hs_codes) if hs_codes else None)
    outputs = derive_trade_outputs(records)
    coverage = coverage_report(records, outputs, set(hs_codes) if hs_codes else None)
    quality = validate_trade_flows(records, coverage, source_metadata)
    failed = [result for result in quality if result.status == "fail"]
    if failed:
        print(json.dumps({"run_id": run_id, "status": "blocked", "quality": [item.model_dump(mode="json") for item in quality]}, indent=2))
        return 2
    product = {
        "product_id": "trade_exposure",
        "contract_version": "1.0.0",
        "materialization_id": run_id,
        "pipeline_id": "03_trade_exposure",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "partition_keys": {"reporter_code": reporter_code, "period": period, "hs_codes": hs_codes, "flow_code": flow_code},
        "lineage": {"raw_object_uri": raw_uri, "content_sha256": capture.content_sha256, "source_record_id": source_record_id},
        "source_metadata": source_metadata,
        "location": f"storage://curated/03_trade_exposure/{run_id}/trade_flows",
        "quality": [item.model_dump(mode="json") for item in quality],
        "coverage": coverage,
        "record_counts": {"trade_flows": len(records), **{name: len(rows) for name, rows in outputs.items()}},
        "limitations": coverage["limitations"],
    }
    storage.publish_trade_product(run_id, records, product, outputs)
    print(json.dumps({"run_id": run_id, "status": "published", **product["record_counts"], "coverage": coverage}, indent=2))
    return 0


def validate_comtrade(period: str, reporter_code: str, partner_code: str, flow_code: str, hs_codes: list[str], trade_fixture: Path | None, settings: Settings) -> int:
    """Validate a Comtrade response without writing raw or curated data."""
    run_id = f"validation-{uuid.uuid4()}"
    if trade_fixture:
        capture = load_comtrade_fixture(trade_fixture.read_bytes(), source_uri=trade_fixture.resolve().as_uri())
    else:
        capture = fetch_comtrade(period=period, reporter_code=reporter_code, partner_code=partner_code, flow_code=flow_code, hs_codes=hs_codes, api_keys=settings.comtrade_api_keys, api_url=settings.comtrade_api_url)
    source_record_id = f"source:{capture.content_sha256}"
    source_metadata = comtrade_response_metadata(capture.payload)
    records = normalize_trade_flows(capture.payload, run_id, source_record_id, set(hs_codes) if hs_codes else None)
    outputs = derive_trade_outputs(records)
    coverage = coverage_report(records, outputs, set(hs_codes) if hs_codes else None)
    quality = validate_trade_flows(records, coverage, source_metadata)
    failed = [item for item in quality if item.status == "fail"]
    print(json.dumps({
        "status": "fail" if failed else "pass",
        "write_mode": "none",
        "source_id": capture.request.source_id,
        "content_sha256": capture.content_sha256,
        "source_metadata": source_metadata,
        "record_counts": {"trade_flows": len(records), **{name: len(rows) for name, rows in outputs.items()}},
        "coverage": coverage,
        "quality": [item.model_dump(mode="json") for item in quality],
    }, indent=2))
    return 2 if failed else 0


def _collect_public_awards(options: dict, settings: Settings, run_id: str) -> dict:
    if options["awards_fixture"]:
        fixture = options["awards_fixture"]
        bundle = load_usaspending_fixture(fixture.read_bytes(), source_uri=fixture.resolve().as_uri())
        award_captures = [bundle["awards"]]
        transaction_captures = bundle["transactions"]
    else:
        award_captures = fetch_award_search(
            award_group=options["award_group"], start_date=options["start_date"], end_date=options["end_date"],
            naics_codes=options["naics_codes"], psc_codes=options["psc_codes"], keywords=options["keywords"],
            awarding_agencies=options["awarding_agencies"], max_records=options["max_records"], api_url=settings.usaspending_award_search_url,
        )
        transaction_captures = {}
    source_metadata = award_search_metadata([capture.payload for capture in award_captures])
    awards: list[dict] = []
    seen: set[str] = set()
    for capture in award_captures:
        for award in normalize_awards(capture.payload, run_id, f"source:{capture.content_sha256}", options["award_group"]):
            if award["award_id"] not in seen:
                seen.add(award["award_id"])
                awards.append(award)
    if not options["awards_fixture"]:
        for award in awards[:options["max_transaction_awards"]]:
            transaction_captures[award["award_id"]] = fetch_award_transactions(award["award_id"], api_url=settings.usaspending_transactions_url)
    events = []
    for award_id, capture in transaction_captures.items():
        if award_id in seen:
            events.extend(normalize_award_transactions(capture.payload, award_id, run_id, f"source:{capture.content_sha256}"))
    entity_candidates = load_entity_candidates(options["entities"]) if options["entities"] else None
    outputs = derive_award_outputs(awards, events, entity_candidates=entity_candidates, window_start=options["start_date"])
    coverage = award_coverage_report(awards, events, source_metadata, set(transaction_captures) & seen)
    quality = validate_awards(awards, events, coverage, source_metadata)
    captures = [*award_captures, *(transaction_captures[award_id] for award_id in sorted(transaction_captures))]
    return {"captures": captures, "awards": awards, "outputs": outputs, "coverage": coverage, "quality": quality, "source_metadata": source_metadata}


def _award_partition_keys(options: dict) -> dict:
    return {key: options[key] for key in ("sector", "award_group", "start_date", "end_date", "naics_codes", "psc_codes", "keywords", "awarding_agencies", "max_records")}


def run_public_awards(options: dict, settings: Settings) -> int:
    run_id = str(uuid.uuid4())
    storage = build_storage(settings)
    result = _collect_public_awards(options, settings, run_id)
    raw_uris = [storage.write_raw(capture) for capture in result["captures"]]
    quality = result["quality"]
    if any(item.status == "fail" for item in quality):
        print(json.dumps({"run_id": run_id, "status": "blocked", "quality": [item.model_dump(mode="json") for item in quality]}, indent=2))
        return 2
    record_counts = {"awards": len(result["awards"]), **{name: len(rows) for name, rows in result["outputs"].items()}}
    product = {
        "product_id": "public_awards",
        "contract_version": "1.0.0",
        "materialization_id": run_id,
        "pipeline_id": "04_public_awards",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "partition_keys": _award_partition_keys(options),
        "lineage": [{"raw_object_uri": uri, "content_sha256": capture.content_sha256, "source_record_id": f"source:{capture.content_sha256}", "source_uri": capture.request.uri} for uri, capture in zip(raw_uris, result["captures"])],
        "source_metadata": result["source_metadata"],
        "location": f"storage://curated/04_public_awards/{run_id}/awards",
        "quality": [item.model_dump(mode="json") for item in quality],
        "coverage": result["coverage"],
        "record_counts": record_counts,
        "limitations": result["coverage"]["limitations"],
    }
    storage.publish_award_product(run_id, result["awards"], product, result["outputs"])
    print(json.dumps({"run_id": run_id, "status": "published", **record_counts, "coverage": result["coverage"]}, indent=2))
    return 0


def validate_usaspending(options: dict, settings: Settings) -> int:
    """Validate a USAspending pull without writing raw or curated data."""
    result = _collect_public_awards(options, settings, f"validation-{uuid.uuid4()}")
    failed = [item for item in result["quality"] if item.status == "fail"]
    print(json.dumps({
        "status": "fail" if failed else "pass",
        "write_mode": "none",
        "content_sha256": [capture.content_sha256 for capture in result["captures"]],
        "source_metadata": result["source_metadata"],
        "record_counts": {"awards": len(result["awards"]), **{name: len(rows) for name, rows in result["outputs"].items()}},
        "coverage": result["coverage"],
        "quality": [item.model_dump(mode="json") for item in result["quality"]],
    }, indent=2))
    return 2 if failed else 0


def _collect_events(options: dict, settings: Settings, run_id: str) -> dict:
    if options["events_fixture"]:
        fixture = options["events_fixture"]
        capture = load_gdelt_fixture(fixture.read_bytes(), source_uri=fixture.resolve().as_uri())
    else:
        capture = fetch_gdelt_articles(
            options["query"], max_records=options["max_records"], timespan=options["timespan"],
            start_datetime=options["start_datetime"], end_datetime=options["end_datetime"],
            source_language=options["source_language"], source_country=options["source_country"],
            api_url=settings.gdelt_doc_api_url,
        )
    source_metadata = gdelt_response_metadata(capture.payload)
    documents = normalize_gdelt_articles(capture.payload, run_id, f"source:{capture.content_sha256}")
    entity_candidates = load_entity_candidates(options["entities"]) if options["entities"] else None
    extractor = RuleBasedEventExtractor()
    outputs = derive_event_outputs(documents, extractor, entity_candidates=entity_candidates, content_sha256=capture.content_sha256)
    coverage = event_coverage_report(documents, outputs, source_metadata)
    quality = validate_event_candidates(documents, outputs["event_candidates"], coverage, source_metadata)
    return {"capture": capture, "documents": documents, "outputs": outputs, "coverage": coverage, "quality": quality, "source_metadata": source_metadata, "extractor": extractor.info}


def run_multilingual_events(options: dict, settings: Settings) -> int:
    run_id = str(uuid.uuid4())
    storage = build_storage(settings)
    result = _collect_events(options, settings, run_id)
    capture = result["capture"]
    raw_uri = storage.write_raw(capture)
    quality = result["quality"]
    if any(item.status == "fail" for item in quality):
        print(json.dumps({"run_id": run_id, "status": "blocked", "quality": [item.model_dump(mode="json") for item in quality]}, indent=2))
        return 2
    record_counts = {"source_documents": len(result["documents"]), **{name: len(rows) for name, rows in result["outputs"].items()}}
    product = {
        "product_id": "multilingual_events",
        "contract_version": "1.0.0",
        "materialization_id": run_id,
        "pipeline_id": "05_multilingual_events",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "partition_keys": {key: options[key] for key in ("sector", "query", "timespan", "start_datetime", "end_datetime", "source_language", "source_country", "max_records")},
        "lineage": {"raw_object_uri": raw_uri, "content_sha256": capture.content_sha256, "source_record_id": f"source:{capture.content_sha256}"},
        "extractor": asdict(result["extractor"]),
        "source_metadata": result["source_metadata"],
        "location": f"storage://curated/05_multilingual_events/{run_id}/event_candidates",
        "quality": [item.model_dump(mode="json") for item in quality],
        "coverage": result["coverage"],
        "record_counts": record_counts,
        "limitations": result["coverage"]["limitations"],
    }
    storage.publish_event_product(run_id, result["documents"], product, result["outputs"])
    print(json.dumps({"run_id": run_id, "status": "published", **record_counts, "coverage": result["coverage"]}, indent=2))
    return 0


def validate_gdelt(options: dict, settings: Settings) -> int:
    """Validate a GDELT pull and event extraction without writing raw or curated data."""
    result = _collect_events(options, settings, f"validation-{uuid.uuid4()}")
    failed = [item for item in result["quality"] if item.status == "fail"]
    print(json.dumps({
        "status": "fail" if failed else "pass",
        "write_mode": "none",
        "content_sha256": result["capture"].content_sha256,
        "source_metadata": result["source_metadata"],
        "record_counts": {"source_documents": len(result["documents"]), **{name: len(rows) for name, rows in result["outputs"].items()}},
        "coverage": result["coverage"],
        "quality": [item.model_dump(mode="json") for item in result["quality"]],
    }, indent=2))
    return 2 if failed else 0


def _add_award_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sector", help="Pipeline 04/05 sector preset (config/award_sectors.yaml or config/event_queries.yaml); explicit filters are added to it")
    parser.add_argument("--award-group", choices=("contracts", "grants"), help="Pipeline 04 USAspending award type group; defaults to the sector's group or contracts")
    parser.add_argument("--awarding-agency", action="append", default=[], help="Pipeline 04 top-tier awarding agency name, e.g. 'Department of Defense'")
    parser.add_argument("--start-date", help="Pipeline 04 action-date window start, YYYY-MM-DD")
    parser.add_argument("--end-date", help="Pipeline 04 action-date window end, YYYY-MM-DD")
    parser.add_argument("--naics", action="append", default=[], help="Pipeline 04 NAICS code; repeat for a sector basket")
    parser.add_argument("--psc", action="append", default=[], help="Pipeline 04 product/service code; repeat for a basket")
    parser.add_argument("--keyword", action="append", default=[], help="Pipeline 04 award keyword; repeat for several")
    parser.add_argument("--max-transaction-awards", type=int, default=10, help="Pipeline 04: fetch modification history for at most this many awards")
    parser.add_argument("--awards-fixture", type=Path, help="Synthetic USAspending bundle for offline Pipeline 04 tests")


def _add_event_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--timespan", default="7d", help="Pipeline 05 GDELT relative window, e.g. 24h, 7d, 3m")
    parser.add_argument("--start-datetime", help="Pipeline 05 GDELT window start, YYYYMMDDHHMMSS; overrides --timespan")
    parser.add_argument("--end-datetime", help="Pipeline 05 GDELT window end, YYYYMMDDHHMMSS")
    parser.add_argument("--source-language", help="Pipeline 05 GDELT sourcelang filter, e.g. english, chinese")
    parser.add_argument("--source-country", help="Pipeline 05 GDELT sourcecountry filter, e.g. us, ch")
    parser.add_argument("--events-fixture", type=Path, help="Synthetic GDELT artlist response for offline Pipeline 05 tests")


def _award_options(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict:
    sector = {"name": None, "award_group": None, "naics": [], "psc": [], "keywords": []}
    if args.sector:
        try:
            sector = load_award_sector(args.sector, ROOT / "config" / "award_sectors.yaml")
        except ValueError as exc:
            parser.error(str(exc))
    naics = list(dict.fromkeys([*sector["naics"], *args.naics]))
    psc = list(dict.fromkeys([*sector["psc"], *args.psc]))
    keywords = list(dict.fromkeys([*sector["keywords"], *args.keyword]))
    if not args.awards_fixture and not (args.start_date and args.end_date):
        parser.error("Pipeline 04 requires --start-date and --end-date for live collection")
    if not args.awards_fixture and not (naics or psc or keywords):
        parser.error("Pipeline 04 requires --sector or at least one --naics, --psc, or --keyword to bound the search")
    return {
        "sector": sector["name"], "award_group": args.award_group or sector["award_group"] or "contracts",
        "start_date": args.start_date, "end_date": args.end_date,
        "naics_codes": naics, "psc_codes": psc, "keywords": keywords, "awarding_agencies": args.awarding_agency,
        "max_records": args.max_results, "max_transaction_awards": args.max_transaction_awards,
        "awards_fixture": args.awards_fixture, "entities": args.entities,
    }


def _event_options(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict:
    query = args.query or ""
    if args.sector:
        try:
            query = " ".join(part for part in (load_event_query(args.sector, ROOT / "config" / "event_queries.yaml"), args.query) if part)
        except ValueError as exc:
            parser.error(str(exc))
    if not args.events_fixture and not query:
        parser.error("Pipeline 05 requires --sector or --query for live collection")
    if bool(args.start_datetime) != bool(args.end_datetime):
        parser.error("Pipeline 05 --start-datetime and --end-datetime must be supplied together")
    return {
        "sector": args.sector, "query": query, "max_records": args.max_results, "timespan": args.timespan,
        "start_datetime": args.start_datetime, "end_datetime": args.end_datetime,
        "source_language": args.source_language, "source_country": args.source_country,
        "events_fixture": args.events_fixture, "entities": args.entities,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="diligence-pipelines")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate-manifests")
    subparsers.add_parser("validate-docs")
    validate_trade_parser = subparsers.add_parser("validate-comtrade", help="Validate a Comtrade response without publishing")
    validate_trade_parser.add_argument("--period", required=True)
    validate_trade_parser.add_argument("--reporter-code", required=True)
    validate_trade_parser.add_argument("--partner-code", default="0")
    validate_trade_parser.add_argument("--flow-code", default="M,X")
    validate_trade_parser.add_argument("--hs-code", action="append", default=[])
    validate_trade_parser.add_argument("--trade-fixture", type=Path)
    validate_awards_parser = subparsers.add_parser("validate-usaspending", help="Validate a USAspending pull without publishing")
    _add_award_arguments(validate_awards_parser)
    validate_awards_parser.add_argument("--max-results", type=int, default=100)
    validate_awards_parser.add_argument("--entities", type=Path, help="Pipeline 01 entities JSONL for recipient match candidates")
    validate_events_parser = subparsers.add_parser("validate-gdelt", help="Validate a GDELT pull and event extraction without publishing")
    _add_event_arguments(validate_events_parser)
    validate_events_parser.add_argument("--query")
    validate_events_parser.add_argument("--sector", help="Pipeline 05 sector preset from config/event_queries.yaml")
    validate_events_parser.add_argument("--max-results", type=int, default=75)
    validate_events_parser.add_argument("--entities", type=Path, help="Pipeline 01 entities JSONL for entity mention edges")
    download_parser = subparsers.add_parser("download-uspto-bulk")
    download_parser.add_argument("--url", required=True, help="Official USPTO ODP artifact URL")
    download_parser.add_argument("--output", type=Path, required=True, help="Local artifact path")
    catalog_parser = subparsers.add_parser("search-uspto-odp")
    catalog_parser.add_argument("--query", required=True, help="ODP product title query")
    catalog_parser.add_argument("--output", type=Path, help="Optional JSON output path")
    discover_parser = subparsers.add_parser("discover-uspto-odp")
    discover_parser.add_argument("--query", help="ODP product title query; defaults to USPTO_ODP_PRODUCT_QUERY")
    discover_parser.add_argument("--output", type=Path, help="Discovery snapshot path; defaults to USPTO_ODP_DISCOVERY_OUTPUT")
    discover_parser.add_argument("--catalog-fixture", type=Path, help="Offline catalog JSON for deterministic testing")
    select_parser = subparsers.add_parser("select-uspto-odp")
    select_parser.add_argument("--catalog", type=Path, required=True, help="Catalog JSON returned by search-uspto-odp")
    select_parser.add_argument("--contains", required=True, help="Text that must identify exactly one catalog item/file")
    select_parser.add_argument("--output", type=Path, required=True, help="Selection manifest path")
    review_parser = subparsers.add_parser("review-uspto-odp")
    review_parser.add_argument("--discovery", type=Path, required=True, help="Discovery snapshot returned by discover-uspto-odp")
    review_parser.add_argument("--candidate-index", type=int, required=True, help="Zero-based candidate index from the discovery snapshot")
    review_parser.add_argument("--reviewer", required=True)
    review_parser.add_argument("--note", required=True, help="Human review rationale")
    review_parser.add_argument("--output", type=Path, required=True, help="Reviewed selection manifest path")
    refresh_parser = subparsers.add_parser("refresh-uspto-odp")
    refresh_parser.add_argument("--selection", type=Path, required=True, help="Reviewed selection manifest")
    refresh_parser.add_argument("--output", type=Path, required=True, help="Local artifact path")
    refresh_parser.add_argument("--previous-file", type=Path, help="Previous artifact for release diff reporting")
    refresh_parser.add_argument("--report-output", type=Path, help="Refresh report path")
    refresh_parser.add_argument("--quality-output", type=Path, help="Quality report path")
    refresh_parser.add_argument("--max-age-days", type=int, help="Fail freshness check when latest patent date is older than this")
    refresh_parser.add_argument("--max-examples", type=int, default=100, help="Maximum new/changed/removed IDs retained in the diff report")
    patent_search_parser = subparsers.add_parser("search-uspto-index")
    patent_search_parser.add_argument("--query", required=True)
    patent_search_parser.add_argument("--limit", type=int, default=25)
    subparsers.add_parser("materialize-patent-catalog", help="Backfill deduplicated catalog from diligence.patent_index")
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
    run_parser.add_argument("--openalex-fixture", type=Path, help="Synthetic OpenAlex response for fully offline Pipeline 02 tests")
    run_parser.add_argument("--patent-fixture", type=Path, help="Synthetic USPTO response for offline Pipeline 02 tests")
    run_parser.add_argument("--patent-bulk-file", type=Path, help="Downloaded USPTO ODP bulk file (JSON, JSONL, CSV, or ZIP) to search locally")
    run_parser.add_argument("--patent-source", choices=("auto", "index", "api"), default="auto", help="Patent source; auto uses PostgreSQL index when configured")
    run_parser.add_argument("--period", help="Pipeline 03 annual period, e.g. 2024")
    run_parser.add_argument("--reporter-code", help="Pipeline 03 Comtrade reporter code")
    run_parser.add_argument("--partner-code", default="0", help="Pipeline 03 Comtrade partner code")
    run_parser.add_argument("--flow-code", default="M,X", help="Pipeline 03 Comtrade flow codes")
    run_parser.add_argument("--hs-code", action="append", default=[], help="Pipeline 03 HS code; repeat for a sector basket")
    run_parser.add_argument("--trade-fixture", type=Path, help="Synthetic UN Comtrade response for offline Pipeline 03 tests")
    _add_award_arguments(run_parser)
    _add_event_arguments(run_parser)
    run_parser.add_argument("--entities", type=Path, help="Pipeline 04/05: Pipeline 01 entities JSONL for unreviewed match candidates")
    args = parser.parse_args()
    if args.command == "validate-manifests":
        return validate_manifests()
    if args.command == "validate-docs":
        return validate_docs(ROOT)
    if args.command == "validate-comtrade":
        return validate_comtrade(args.period, args.reporter_code, args.partner_code, args.flow_code, args.hs_code, args.trade_fixture, Settings.from_env())
    if args.command == "validate-usaspending":
        return validate_usaspending(_award_options(args, parser), Settings.from_env())
    if args.command == "validate-gdelt":
        return validate_gdelt(_event_options(args, parser), Settings.from_env())
    if args.command == "download-uspto-bulk":
        return download_uspto_bulk(args.url, args.output, Settings.from_env())
    if args.command == "search-uspto-odp":
        return search_uspto_odp(args.query, args.output, Settings.from_env())
    if args.command == "discover-uspto-odp":
        return discover_uspto_odp(args.query, args.output, args.catalog_fixture, Settings.from_env())
    if args.command == "select-uspto-odp":
        return select_uspto_odp(args.catalog, args.contains, args.output)
    if args.command == "review-uspto-odp":
        return review_uspto_odp(args.discovery, args.candidate_index, args.reviewer, args.note, args.output)
    if args.command == "refresh-uspto-odp":
        return refresh_uspto_odp(args.selection, args.output, args.previous_file, args.report_output, args.quality_output, args.max_age_days, args.max_examples, Settings.from_env())
    if args.command == "search-uspto-index":
        return search_uspto_index(args.query, args.limit, Settings.from_env())
    if args.command == "materialize-patent-catalog":
        return materialize_patent_catalog(Settings.from_env())
    if args.command == "index-uspto-bulk":
        return index_uspto_bulk(args.file, args.limit, Settings.from_env())
    if args.command == "enrich-uspto-index":
        return enrich_uspto_index(args.patent_file, args.abstract_file, args.assignee_file, args.limit, Settings.from_env())
    if args.command == "ingest-uspto-bulk":
        return ingest_uspto_bulk(args.patent_file, args.abstract_file, args.assignee_file, args.limit, args.batch_size, Settings.from_env())
    if args.pipeline_id == "02_technology_talent":
        if not args.query or args.input or args.cik or args.watchlist:
            parser.error("Pipeline 02 requires --query and does not accept Pipeline 01 inputs")
        return run_technology_talent(args.query, args.max_results, args.openalex_fixture, args.patent_fixture, args.patent_bulk_file, args.patent_source, Settings.from_env())
    if args.pipeline_id == "03_trade_exposure":
        if not args.period or not args.reporter_code or args.input or args.cik or args.watchlist or args.query:
            parser.error("Pipeline 03 requires --period and --reporter-code and does not accept Pipeline 01/02 inputs")
        return run_trade_exposure(args.period, args.reporter_code, args.partner_code, args.flow_code, args.hs_code, args.trade_fixture, Settings.from_env())
    if args.pipeline_id == "04_public_awards":
        if args.input or args.cik or args.watchlist or args.query:
            parser.error("Pipeline 04 does not accept Pipeline 01/02 inputs")
        return run_public_awards(_award_options(args, parser), Settings.from_env())
    if args.pipeline_id == "05_multilingual_events":
        if args.input or args.cik or args.watchlist:
            parser.error("Pipeline 05 does not accept Pipeline 01 inputs")
        return run_multilingual_events(_event_options(args, parser), Settings.from_env())
    if args.pipeline_id != "01_entity_graph":
        parser.error("Implemented pipelines are 01_entity_graph, 02_technology_talent, 03_trade_exposure, 04_public_awards, and 05_multilingual_events")
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
