from __future__ import annotations

import json
from pathlib import Path

from diligence_pipelines.sources.base import RawCapture


class LocalStorage:
    """Append-only local storage for development and fixture replay."""

    def __init__(self, root: Path):
        self.root = root

    def write_raw(self, capture: RawCapture) -> str:
        destination = self.root / "raw" / capture.request.source_id / f"{capture.content_sha256}.bin"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(capture.payload)
        metadata = destination.with_suffix(".json")
        metadata.write_text(json.dumps({
            "source_id": capture.request.source_id,
            "source_uri": capture.request.uri,
            "params": dict(capture.request.params),
            "retrieved_at": capture.retrieved_at.isoformat(),
            "status_code": capture.status_code,
            "adapter_version": capture.adapter_version,
            "content_sha256": capture.content_sha256,
        }, indent=2) + "\n")
        return str(destination)

    def read_raw(self, content_sha256: str, source_id: str = "uspto_odp") -> bytes:
        return (self.root / "raw" / source_id / f"{content_sha256}.bin").read_bytes()

    def write_jsonl(self, relative_path: str, records: list[dict]) -> Path:
        destination = self.root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("".join(json.dumps(record, default=str) + "\n" for record in records))
        return destination

    def upsert_patent_index(self, records: list[dict], metadata: dict) -> int:
        self.write_jsonl("indexes/uspto_patents/patent_index.jsonl", records)
        self.write_jsonl("indexes/uspto_patents/index_runs.jsonl", [metadata])
        self.upsert_patent_catalog(records, metadata["source_file_sha256"], metadata.get("source_release"))
        return len(records)

    def upsert_patent_catalog(self, records: list[dict], source_file_sha256: str, source_release: str | None = None) -> int:
        path = self.root / "indexes/uspto_patents/patent_catalog.jsonl"
        existing = {}
        if path.exists():
            existing = {row["patent_id"]: row for row in (json.loads(line) for line in path.read_text().splitlines() if line.strip())}
        for record in records:
            existing[record["patent_id"]] = {
                "patent_id": record["patent_id"],
                "source_file_sha256": source_file_sha256,
                "source_release": source_release,
                "record": record,
            }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, default=str) + "\n" for row in existing.values()))
        return len(records)

    def materialize_patent_catalog(self) -> dict:
        index_path = self.root / "indexes/uspto_patents/patent_index.jsonl"
        if not index_path.exists():
            return {"status": "completed", "patent_index_rows": 0, "patent_catalog_rows": 0, "parity_mismatch_count": 0, "upserted_row_count": 0, "source_file_sha256s": []}
        records = [json.loads(line) for line in index_path.read_text().splitlines() if line.strip()]
        source_hashes = {record.get("source_file_sha256") for record in records if record.get("source_file_sha256")}
        if not source_hashes:
            run_path = self.root / "indexes/uspto_patents/index_runs.jsonl"
            if run_path.exists():
                source_hashes = {
                    row.get("source_file_sha256")
                    for row in (json.loads(line) for line in run_path.read_text().splitlines() if line.strip())
                    if row.get("source_file_sha256")
                }
        upserted = self.upsert_patent_catalog(records, next(iter(source_hashes), "unknown"))
        catalog_path = self.root / "indexes/uspto_patents/patent_catalog.jsonl"
        catalog_rows = sum(1 for line in catalog_path.read_text().splitlines() if line.strip())
        return {"status": "completed", "patent_index_rows": len(records), "patent_catalog_rows": catalog_rows, "parity_mismatch_count": 0, "upserted_row_count": upserted, "source_file_sha256s": sorted(source_hashes)}

    def record_uspto_odp_discovery(self, report: dict) -> str:
        """Persist the latest catalog snapshot and retain discovery history."""
        latest = self.root / "indexes/uspto_patents/odp_discovery.json"
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(json.dumps(report, indent=2) + "\n")
        history = self.root / "indexes/uspto_patents/odp_discovery_history.jsonl"
        with history.open("a") as destination:
            destination.write(json.dumps(report, default=str) + "\n")
        return str(latest)

    def record_uspto_odp_refresh(self, report: dict) -> str:
        """Persist every approved refresh outcome, including failures, for scheduler inspection."""
        latest = self.root / "indexes/uspto_patents/odp_refresh.json"
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(json.dumps(report, indent=2, default=str) + "\n")
        history = self.root / "indexes/uspto_patents/odp_refresh_history.jsonl"
        with history.open("a") as destination:
            destination.write(json.dumps(report, default=str) + "\n")
        return str(latest)

    def search_patent_index(self, query: str, limit: int = 25) -> list[dict]:
        path = self.root / "indexes/uspto_patents/patent_index.jsonl"
        if not path.exists():
            return []
        needle = query.casefold()
        matches = []
        for line in path.read_text().splitlines():
            record = json.loads(line)
            haystack = " ".join(str(record.get(field) or "") for field in ("title", "abstract", "assignee_name"))
            if needle in haystack.casefold():
                matches.append(record)
                if len(matches) >= limit:
                    break
        return matches

    def publish_entity_product(self, run_id: str, entities: list[dict], product: dict, aliases: list[dict] | None = None, match_candidates: list[dict] | None = None) -> str:
        output = self.write_jsonl(f"curated/01_entity_graph/{run_id}/entities.jsonl", entities)
        self.write_jsonl(f"curated/01_entity_graph/{run_id}/entity_aliases.jsonl", aliases or [])
        self.write_jsonl(f"curated/01_entity_graph/{run_id}/unresolved_match_candidates.jsonl", match_candidates or [])
        self.write_jsonl(f"curated/01_entity_graph/{run_id}/product_manifest.jsonl", [product])
        return str(output)

    def publish_reviewed_match_product(self, run_id: str, candidates: list[dict], product: dict) -> str:
        output = self.write_jsonl(f"curated/01_entity_graph/{run_id}/reviewed_match_candidates.jsonl", candidates)
        self.write_jsonl(f"curated/01_entity_graph/{run_id}/product_manifest.jsonl", [product])
        return str(output)

    def publish_research_product(self, run_id: str, records: list[dict], product: dict, observations: list[dict] | None = None, patent_records: list[dict] | None = None, assignments: list[dict] | None = None, inventor_edges: list[dict] | None = None, institution_edges: list[dict] | None = None) -> str:
        output = self.write_jsonl(f"curated/02_technology_talent/{run_id}/research_works.jsonl", records)
        self.write_jsonl(f"curated/02_technology_talent/{run_id}/technology_topic_observations.jsonl", observations or [])
        self.write_jsonl(f"curated/02_technology_talent/{run_id}/patent_records.jsonl", patent_records or [])
        self.write_jsonl(f"curated/02_technology_talent/{run_id}/patent_assignments.jsonl", assignments or [])
        self.write_jsonl(f"curated/02_technology_talent/{run_id}/inventor_edges.jsonl", inventor_edges or [])
        self.write_jsonl(f"curated/02_technology_talent/{run_id}/institution_edges.jsonl", institution_edges or [])
        self.write_jsonl(f"curated/02_technology_talent/{run_id}/product_manifest.jsonl", [product])
        return str(output)

    def publish_trade_product(self, run_id: str, records: list[dict], product: dict, outputs: dict[str, list[dict]]) -> str:
        output = self.write_jsonl(f"curated/03_trade_exposure/{run_id}/trade_flows.jsonl", records)
        for name, rows in outputs.items():
            self.write_jsonl(f"curated/03_trade_exposure/{run_id}/{name}.jsonl", rows)
        self.write_jsonl(f"curated/03_trade_exposure/{run_id}/product_manifest.jsonl", [product])
        return str(output)

    def _publish_outputs(self, pipeline_id: str, run_id: str, outputs: dict[str, list[dict]], product: dict, primary: str) -> str:
        for name, rows in outputs.items():
            self.write_jsonl(f"curated/{pipeline_id}/{run_id}/{name}.jsonl", rows)
        self.write_jsonl(f"curated/{pipeline_id}/{run_id}/product_manifest.jsonl", [product])
        return str(self.root / f"curated/{pipeline_id}/{run_id}/{primary}.jsonl")

    def publish_award_product(self, run_id: str, awards: list[dict], product: dict, outputs: dict[str, list[dict]]) -> str:
        return self._publish_outputs("04_public_awards", run_id, {"awards": awards, **outputs}, product, "awards")

    def publish_financial_product(self, run_id: str, facts: list[dict], product: dict, metrics: list[dict]) -> str:
        return self._publish_outputs("01_entity_graph", run_id, {"financial_facts": facts, "financial_metrics": metrics}, product, "financial_facts")

    def publish_event_product(self, run_id: str, documents: list[dict], product: dict, outputs: dict[str, list[dict]]) -> str:
        return self._publish_outputs("05_multilingual_events", run_id, {"source_documents": documents, **outputs}, product, "source_documents")
