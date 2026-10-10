from __future__ import annotations

import hashlib
import json
import ssl
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi


DEFAULT_ODP_CATALOG_URL = "https://api.uspto.gov/api/v1/datasets/products/search"
DOWNLOAD_KEYS = {"url", "downloadurl", "filedownloaduri", "downloaduri", "fileurl", "download_url", "file_download_uri"}


@dataclass(frozen=True)
class BulkArtifact:
    path: str
    source_url: str
    retrieved_at: str
    content_sha256: str
    size_bytes: int
    status_code: int


def _walk_dicts(value: object, context: str = ""):
    if isinstance(value, dict):
        own_context = f"{context} {json.dumps({key: child for key, child in value.items() if not isinstance(child, (dict, list))}, sort_keys=True)}"
        yield value, own_context
        for child in value.values():
            yield from _walk_dicts(child, own_context)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child, context)


def select_catalog_artifact(payload: bytes, contains: str) -> dict:
    """Select one catalog item/file without guessing among unrelated releases."""
    data = json.loads(payload)
    needle = contains.casefold().strip()
    candidates = []
    for item, context in _walk_dicts(data):
        urls = [str(value) for key, value in item.items() if key.casefold().replace("-", "_") in DOWNLOAD_KEYS and isinstance(value, str) and value.startswith(("https://", "http://"))]
        if not urls:
            continue
        text = f"{context} {json.dumps(item, sort_keys=True)}".casefold()
        if needle and needle not in text:
            continue
        for url in urls:
            candidates.append({"source": item, "download_url": url})
    if not candidates:
        raise ValueError(f"No downloadable ODP catalog item matched: {contains}")
    if len(candidates) > 1:
        raise ValueError(f"ODP catalog match is ambiguous ({len(candidates)} files); narrow --contains")
    return candidates[0]


def search_odp_products(query: str, api_key: str, api_url: str = DEFAULT_ODP_CATALOG_URL) -> bytes:
    if not query.strip():
        raise ValueError("ODP product query must not be empty")
    if not api_key:
        raise ValueError("USPTO_API_KEY is required for ODP catalog access")
    uri = f"{api_url}?{urlencode({'productTitle': query})}"
    request = Request(uri, headers={"X-Api-Key": api_key, "Accept": "application/json", "User-Agent": "investment-diligence-pipelines/0.1"})
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(request, timeout=60, context=context) as response:
            return response.read()
    except HTTPError as exc:
        raise RuntimeError(f"USPTO ODP catalog returned HTTP {exc.code}: {uri}") from exc
    except URLError as exc:
        raise RuntimeError(f"Unable to reach USPTO ODP catalog {uri}: {exc.reason}") from exc


def download_bulk_artifact(url: str, output_path: Path, api_key: str | None = None) -> BulkArtifact:
    if not url.startswith(("https://", "http://")):
        raise ValueError("Bulk artifact URL must use http:// or https://")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = {"Accept": "*/*", "User-Agent": "investment-diligence-pipelines/0.1"}
    if api_key:
        headers["X-Api-Key"] = api_key
    request = Request(url, headers=headers)
    context = ssl.create_default_context(cafile=certifi.where())
    digest = hashlib.sha256()
    size = 0
    retrieved_at = datetime.now(timezone.utc).isoformat()
    try:
        with urlopen(request, timeout=120, context=context) as response, output_path.open("wb") as destination:
            while chunk := response.read(1024 * 1024):
                destination.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            status_code = getattr(response, "status", 200)
    except (HTTPError, URLError) as exc:
        if output_path.exists():
            output_path.unlink()
        detail = f"HTTP {exc.code}" if isinstance(exc, HTTPError) else str(exc.reason)
        raise RuntimeError(f"Unable to download USPTO ODP artifact {url}: {detail}") from exc
    artifact = BulkArtifact(str(output_path), url, retrieved_at, digest.hexdigest(), size, status_code)
    output_path.with_suffix(output_path.suffix + ".json").write_text(json.dumps(asdict(artifact), indent=2) + "\n")
    return artifact
