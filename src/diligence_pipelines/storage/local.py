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

    def write_jsonl(self, relative_path: str, records: list[dict]) -> Path:
        destination = self.root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("".join(json.dumps(record, default=str) + "\n" for record in records))
        return destination

    def publish_entity_product(self, run_id: str, entities: list[dict], product: dict) -> str:
        output = self.write_jsonl(f"curated/01_entity_graph/{run_id}/entities.jsonl", entities)
        self.write_jsonl(f"curated/01_entity_graph/{run_id}/product_manifest.jsonl", [product])
        return str(output)
