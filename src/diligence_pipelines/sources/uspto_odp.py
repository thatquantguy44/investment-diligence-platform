from __future__ import annotations

import hashlib
import json
import re
import ssl
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener, urlopen

import certifi

from diligence_pipelines.sources.base import open_url_with_retries


DEFAULT_ODP_CATALOG_URL = "https://api.uspto.gov/api/v1/datasets/products/search"
ODP_POLICY_VERSION = "uspto-odp-pvgpatdis-g-patent-v1"
ODP_API_PREFIX = "/api/v1/datasets/products/"
MAX_METADATA_BYTES = 2_000_000
DOWNLOAD_KEYS = {"url", "downloadurl", "filedownloaduri", "downloaduri", "fileurl", "download_url", "file_download_uri"}


@dataclass(frozen=True)
class BulkArtifact:
    path: str
    source_url: str
    retrieved_at: str
    content_sha256: str
    size_bytes: int
    status_code: int


def discover_catalog_artifacts(payload: bytes, query: str) -> list[dict]:
    """Return all downloadable catalog artifacts matching a product query.

    Discovery is intentionally broader than ``select_catalog_artifact``: a
    release poll should record new candidates for review, not guess which
    release is safe to ingest.
    """
    data = json.loads(payload)
    needle = query.casefold().strip()
    if not needle:
        raise ValueError("ODP product query must not be empty")
    candidates: list[dict] = []
    seen_urls: set[str] = set()
    for item, context in _walk_dicts(data):
        urls = [
            str(value)
            for key, value in item.items()
            if key.casefold().replace("-", "_") in DOWNLOAD_KEYS
            and isinstance(value, str)
            and value.startswith(("https://", "http://"))
        ]
        if not urls:
            continue
        text = f"{context} {json.dumps(item, sort_keys=True)}".casefold()
        if needle not in text:
            continue
        for url in urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            candidates.append({"source": item, "download_url": url})
    return candidates


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


def _next_page(value: object) -> str | None:
    if isinstance(value, dict):
        for key in ("next", "nextPage", "next_page", "nextLink", "next_link"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.startswith(("https://", "http://")):
                return candidate
        for key in ("pagination", "page", "links"):
            child = value.get(key)
            if isinstance(child, dict):
                found = _next_page(child)
                if found:
                    return found
    return None


def _official_odp_url(uri: str, path_prefix: str = ODP_API_PREFIX) -> bool:
    parsed = urlparse(uri)
    return parsed.scheme == "https" and parsed.netloc == "api.uspto.gov" and parsed.path.startswith(path_prefix) and not parsed.username and not parsed.password and not parsed.fragment


def _read_metadata(response) -> bytes:
    payload = response.read(MAX_METADATA_BYTES + 1)
    if len(payload) > MAX_METADATA_BYTES:
        raise ValueError("USPTO ODP metadata response exceeds the configured size limit")
    return payload


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _official_open(request, *, timeout: float, context):
    """Do not forward an API key across a redirect, even to another USPTO URL."""
    return build_opener(HTTPSHandler(context=context), _RejectRedirects()).open(request, timeout=timeout)


def _exact_record(records: object, key: str, expected: str, label: str) -> dict:
    if not isinstance(records, list):
        raise ValueError(f"Incomplete {label} records")
    matches = [record for record in records if isinstance(record, dict) and record.get(key) == expected]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {label} {expected}; found {len(matches)}")
    return matches[0]


def _complete_bag(data: object, bag_key: str, count_key: str = "count") -> list[dict]:
    if not isinstance(data, dict) or not isinstance(data.get(bag_key), list):
        raise ValueError(f"Incomplete {bag_key} response")
    bag = data[bag_key]
    count = data.get(count_key)
    if not isinstance(count, int) or count < 0 or count != len(bag):
        raise ValueError(f"Incomplete {bag_key} response: count does not match records")
    return bag


def select_odp_candidate(search_payload: bytes, detail_payload: bytes, product_identifier: str, artifact_name: str, policy_limits: dict | None = None) -> dict:
    """Select one exact USPTO product/file from complete provider metadata."""
    search = json.loads(search_payload)
    detail = json.loads(detail_payload)
    search_product = _exact_record(_complete_bag(search, "bulkDataProductBag"), "productIdentifier", product_identifier, "product")
    product = _exact_record(_complete_bag(detail, "bulkDataProductBag"), "productIdentifier", product_identifier, "product")
    files = _complete_bag(product.get("productFileBag"), "fileDataBag")
    file = _exact_record(files, "fileName", artifact_name, "artifact")
    url = file.get("fileDownloadURI")
    expected_path = f"{ODP_API_PREFIX}files/{product_identifier}/{artifact_name}"
    if not isinstance(url, str) or not _official_odp_url(url, expected_path) or urlparse(url).path != expected_path or urlparse(url).query:
        raise ValueError("Selected artifact has an invalid USPTO download URL")
    size = file.get("fileSize")
    if not isinstance(size, int) or size <= 0:
        raise ValueError("Selected artifact has an invalid file size")
    if file.get("fileTypeText") != "Data":
        raise ValueError("Selected artifact is not a USPTO data file")
    policy = {"source_id": "uspto_odp", "product_identifier": product_identifier, "artifact_name": artifact_name, "download_host": "api.uspto.gov", "file_type": "Data", "limits": policy_limits or {"min_size_bytes": None, "max_size_bytes": None, "max_release_age_days": None, "max_patent_age_days": None}}
    policy_digest = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    material = {"policy": policy, "download_url": url, "size_bytes": size, "file_release_at": file.get("fileReleaseDate"), "file_modified_at": file.get("fileLastModifiedDateTime"), "provider_checksum": file.get("fileChecksum")}
    fingerprint = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "schema_version": "1.0.0", "source_id": "uspto_odp", "product_identifier": product_identifier,
        "product_title": product.get("productTitleText") or search_product.get("productTitleText"),
        "artifact_name": artifact_name, "logical_artifact_id": f"uspto_odp:{product_identifier}:{artifact_name}",
        "candidate_fingerprint": f"sha256:{fingerprint}", "policy_version": ODP_POLICY_VERSION,
        "approval_policy_digest": f"sha256:{policy_digest}", "download_url": url,
        "file_size": size, "size_bytes": size, "file_release_at": file.get("fileReleaseDate"),
        "file_modified_at": file.get("fileLastModifiedDateTime"), "provider_checksum": file.get("fileChecksum"),
        "provider_checksum_status": "provided" if file.get("fileChecksum") else "unavailable",
        "policy_status": "review_required", "policy_reasons": [], "source": file,
    }


def fetch_odp_product(product_identifier: str, api_key: str) -> bytes:
    if not re.fullmatch(r"[A-Z0-9]+", product_identifier):
        raise ValueError("Invalid USPTO ODP product identifier")
    if not api_key:
        raise ValueError("USPTO_API_KEY is required for ODP product detail")
    uri = f"https://api.uspto.gov{ODP_API_PREFIX}{product_identifier}"
    request = Request(uri, headers={"X-Api-Key": api_key, "Accept": "application/json", "User-Agent": "investment-diligence-pipelines/0.1"})
    try:
        with open_url_with_retries(request, timeout=60, context=ssl.create_default_context(cafile=certifi.where()), open_request=_official_open) as response:
            return _read_metadata(response)
    except HTTPError as exc:
        raise RuntimeError(f"USPTO ODP product detail returned HTTP {exc.code}: {uri}") from exc
    except URLError as exc:
        raise RuntimeError(f"Unable to reach USPTO ODP product detail {uri}: {exc.reason}") from exc


def search_odp_products(query: str, api_key: str, api_url: str = DEFAULT_ODP_CATALOG_URL, max_pages: int = 20) -> bytes:
    if not query.strip():
        raise ValueError("ODP product query must not be empty")
    if not api_key:
        raise ValueError("USPTO_API_KEY is required for ODP catalog access")
    if max_pages < 1:
        raise ValueError("max_pages must be at least 1")
    if not _official_odp_url(api_url, "/api/v1/datasets/products/search") or urlparse(api_url).path != "/api/v1/datasets/products/search" or urlparse(api_url).query:
        raise ValueError("USPTO ODP catalog URL must use the official API host")
    uri = f"{api_url}?{urlencode({'productTitle': query})}"
    context = ssl.create_default_context(cafile=certifi.where())
    pages: list[object] = []
    visited: set[str] = set()
    for _ in range(max_pages):
        if uri in visited or not _official_odp_url(uri, "/api/v1/datasets/products/search") or urlparse(uri).path != "/api/v1/datasets/products/search":
            raise ValueError("Invalid or repeated USPTO ODP pagination URL")
        visited.add(uri)
        request = Request(uri, headers={"X-Api-Key": api_key, "Accept": "application/json", "User-Agent": "investment-diligence-pipelines/0.1"})
        try:
            with open_url_with_retries(request, timeout=60, context=context, open_request=_official_open) as response:
                payload = _read_metadata(response)
        except HTTPError as exc:
            raise RuntimeError(f"USPTO ODP catalog returned HTTP {exc.code}: {uri}") from exc
        except URLError as exc:
            raise RuntimeError(f"Unable to reach USPTO ODP catalog {uri}: {exc.reason}") from exc
        page = json.loads(payload)
        pages.append(page)
        uri = _next_page(page)
        if not uri:
            break
    else:
        raise ValueError("Incomplete USPTO ODP search: page limit reached")
    if len(pages) == 1:
        return json.dumps(pages[0], separators=(",", ":")).encode()
    if all(isinstance(page, dict) for page in pages):
        merged = dict(pages[0])
        for key in ("bulkDataProductBag", "products", "data", "results", "items"):
            values = [page.get(key) for page in pages if isinstance(page.get(key), list)]
            if values:
                merged[key] = [item for group in values for item in group]
                break
        merged["_pagination"] = {"pages_fetched": len(pages), "max_pages": max_pages}
        return json.dumps(merged, separators=(",", ":")).encode()
    return json.dumps({"pages": pages, "_pagination": {"pages_fetched": len(pages), "max_pages": max_pages}}, separators=(",", ":")).encode()


def review_catalog_artifact(discovery: dict, *, candidate_index: int, reviewer: str, note: str) -> dict:
    """Create an explicit human-review record from a discovery snapshot."""
    if not reviewer.strip():
        raise ValueError("reviewer must not be empty")
    if not note.strip():
        raise ValueError("review note must not be empty")
    candidates = discovery.get("candidates")
    if not isinstance(candidates, list) or not 0 <= candidate_index < len(candidates):
        raise ValueError("candidate_index does not identify a discovered ODP artifact")
    candidate = candidates[candidate_index]
    return {
        "status": "approved_for_download",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": reviewer,
        "review_note": note,
        "discovery_id": discovery.get("discovery_id"),
        "catalog_sha256": discovery.get("catalog_sha256"),
        "product_query": discovery.get("product_query"),
        "candidate_index": candidate_index,
        "source": candidate.get("source", {}),
        "download_url": candidate.get("download_url"),
    }


def download_bulk_artifact(url: str, output_path: Path, api_key: str | None = None, *, expected_size: int | None = None, max_bytes: int | None = None) -> BulkArtifact:
    if not url.startswith(("https://", "http://")):
        raise ValueError("Bulk artifact URL must use http:// or https://")
    if api_key and (not _official_odp_url(url, f"{ODP_API_PREFIX}files/") or urlparse(url).query):
        raise ValueError("Authenticated USPTO download requires the official file host and path")
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
        opener = _official_open if api_key else urlopen
        with opener(request, timeout=120, context=context) as response, output_path.open("wb") as destination:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if (max_bytes is not None and size > max_bytes) or (expected_size is not None and size > expected_size):
                    raise ValueError("USPTO artifact exceeds approved byte count")
                destination.write(chunk)
                digest.update(chunk)
            status_code = getattr(response, "status", 200)
            if status_code != 200 or (expected_size is not None and size != expected_size):
                raise ValueError("USPTO artifact response status or byte count does not match approved metadata")
    except (HTTPError, URLError, ValueError) as exc:
        if output_path.exists():
            output_path.unlink()
        detail = f"HTTP {exc.code}" if isinstance(exc, HTTPError) else str(exc.reason) if isinstance(exc, URLError) else str(exc)
        raise RuntimeError(f"Unable to download USPTO ODP artifact {url}: {detail}") from exc
    artifact = BulkArtifact(str(output_path), url, retrieved_at, digest.hexdigest(), size, status_code)
    output_path.with_suffix(output_path.suffix + ".json").write_text(json.dumps(asdict(artifact), indent=2) + "\n")
    return artifact


def verify_patent_archive(path: Path, *, max_uncompressed_bytes: int) -> dict:
    """Require exactly the expected TSV and verify ZIP CRC before promotion."""
    if not zipfile.is_zipfile(path):
        raise ValueError("USPTO artifact is not a ZIP archive")
    with zipfile.ZipFile(path) as archive:
        files = [item for item in archive.infolist() if not item.is_dir()]
        if len(files) != 1 or files[0].filename != "g_patent.tsv":
            raise ValueError("USPTO archive does not contain exactly g_patent.tsv")
        member = files[0]
        if member.file_size <= 0 or member.file_size > max_uncompressed_bytes:
            raise ValueError("USPTO archive expands beyond approved size bounds")
        if archive.testzip() is not None:
            raise ValueError("USPTO archive failed CRC verification")
        return {"member_name": member.filename, "uncompressed_bytes": member.file_size, "crc32": f"{member.CRC:08x}"}
