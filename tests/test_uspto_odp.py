import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from diligence_pipelines.sources import uspto_odp


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        if size == -1:
            return b"artifact"
        if getattr(self, "done", False):
            return b""
        self.done = True
        return b"artifact"


def test_download_bulk_artifact_writes_checksum_sidecar(monkeypatch, tmp_path):
    monkeypatch.setattr(uspto_odp, "urlopen", lambda *args, **kwargs: _Response())
    destination = tmp_path / "patents.jsonl"
    artifact = uspto_odp.download_bulk_artifact("https://example.test/patents.jsonl", destination)
    assert destination.read_bytes() == b"artifact"
    sidecar = json.loads(Path(str(destination) + ".json").read_text())
    assert sidecar["content_sha256"] == artifact.content_sha256
    assert sidecar["size_bytes"] == 8


def test_authenticated_download_rejects_off_host_before_network(tmp_path, monkeypatch):
    monkeypatch.setattr(uspto_odp, "_official_open", lambda *args, **kwargs: pytest.fail("network attempted"))
    with pytest.raises(ValueError, match="official file host"):
        uspto_odp.download_bulk_artifact("https://example.test/g_patent.tsv.zip", tmp_path / "file.zip", api_key="test-key")


def test_authenticated_download_follows_exact_signed_uspto_redirect_without_api_key(tmp_path, monkeypatch):
    official = "https://api.uspto.gov/api/v1/datasets/products/files/PVGPATDIS/g_patent.tsv.zip"
    signed = "https://data.uspto.gov/files/PVGPATDIS/g_patent.tsv.zip?Expires=123&Key-Pair-Id=abc&Signature=xyz"
    requests = []

    def fake_open(request, **kwargs):
        requests.append(request)
        if len(requests) == 1:
            raise HTTPError(official, 302, "Found", {"Location": signed}, None)
        return _Response()

    monkeypatch.setattr(uspto_odp, "_official_open", fake_open)
    destination = tmp_path / "file.zip"
    artifact = uspto_odp.download_bulk_artifact(official, destination, api_key="test-key", expected_size=8, max_bytes=8)

    assert artifact.source_url == official
    assert destination.read_bytes() == b"artifact"
    assert len(requests) == 2
    assert requests[0].get_header("X-api-key") == "test-key"
    assert requests[1].get_header("X-api-key") is None
    assert requests[1].full_url == signed
    assert signed not in Path(str(destination) + ".json").read_text()


@pytest.mark.parametrize("signed", [
    "https://example.test/files/PVGPATDIS/g_patent.tsv.zip?Expires=123&Key-Pair-Id=abc&Signature=xyz",
    "https://data.uspto.gov/files/PVGPATDIS/other.zip?Expires=123&Key-Pair-Id=abc&Signature=xyz",
    "https://data.uspto.gov/files/PVGPATDIS/g_patent.tsv.zip?Expires=123&Signature=xyz",
])
def test_authenticated_download_rejects_unapproved_redirect(tmp_path, monkeypatch, signed):
    official = "https://api.uspto.gov/api/v1/datasets/products/files/PVGPATDIS/g_patent.tsv.zip"
    calls = []

    def fake_open(request, **kwargs):
        calls.append(request)
        raise HTTPError(official, 302, "Found", {"Location": signed}, None)

    monkeypatch.setattr(uspto_odp, "_official_open", fake_open)
    with pytest.raises(RuntimeError, match="redirect"):
        uspto_odp.download_bulk_artifact(official, tmp_path / "file.zip", api_key="test-key")
    assert len(calls) == 1
    assert not (tmp_path / "file.zip").exists()


def test_authenticated_download_rejects_second_redirect_without_leaking_signed_url(tmp_path, monkeypatch):
    official = "https://api.uspto.gov/api/v1/datasets/products/files/PVGPATDIS/g_patent.tsv.zip"
    signed = "https://data.uspto.gov/files/PVGPATDIS/g_patent.tsv.zip?Expires=123&Key-Pair-Id=abc&Signature=secret-signature"
    calls = []

    def fake_open(request, **kwargs):
        calls.append(request)
        if len(calls) == 1:
            raise HTTPError(official, 302, "Found", {"Location": signed}, None)
        raise HTTPError(signed, 302, "Found", {"Location": "https://example.test/other.zip"}, None)

    monkeypatch.setattr(uspto_odp, "_official_open", fake_open)
    with pytest.raises(RuntimeError, match="signed file host returned HTTP 302") as error:
        uspto_odp.download_bulk_artifact(official, tmp_path / "file.zip", api_key="test-key")
    assert len(calls) == 2
    assert "secret-signature" not in str(error.value)


@pytest.mark.parametrize("stage,expected", [
    ("api", "Official USPTO file endpoint returned HTTP 403"),
    ("signed", "USPTO signed file host returned HTTP 403"),
])
def test_authenticated_download_reports_safe_http_failure_stage(tmp_path, monkeypatch, stage, expected):
    official = "https://api.uspto.gov/api/v1/datasets/products/files/PVGPATDIS/g_patent.tsv.zip"
    signed = "https://data.uspto.gov/files/PVGPATDIS/g_patent.tsv.zip?Expires=123&Key-Pair-Id=abc&Signature=secret-signature"
    calls = []

    def fake_open(request, **kwargs):
        calls.append(request)
        if stage == "api" or len(calls) == 2:
            raise HTTPError(request.full_url, 403, "Forbidden", {}, None)
        raise HTTPError(official, 302, "Found", {"Location": signed}, None)

    monkeypatch.setattr(uspto_odp, "_official_open", fake_open)
    with pytest.raises(RuntimeError, match=expected) as error:
        uspto_odp.download_bulk_artifact(official, tmp_path / "file.zip", api_key="test-key")
    assert "secret-signature" not in str(error.value)


def test_download_rejects_excess_bytes_and_removes_partial_file(monkeypatch, tmp_path):
    monkeypatch.setattr(uspto_odp, "urlopen", lambda *args, **kwargs: _Response())
    output = tmp_path / "file.zip"
    with pytest.raises(RuntimeError, match="byte count"):
        uspto_odp.download_bulk_artifact("https://example.test/file.zip", output, expected_size=7, max_bytes=7)
    assert not output.exists()


def test_select_catalog_artifact_requires_one_matching_file():
    payload = Path("tests/fixtures/odp_catalog.json").read_bytes()
    selection = uspto_odp.select_catalog_artifact(payload, "2025-Q4")
    assert selection["download_url"].endswith("patents-2025q4.jsonl")


def test_discover_catalog_artifacts_records_all_matching_candidates():
    payload = Path("tests/fixtures/odp_catalog.json").read_bytes()
    candidates = uspto_odp.discover_catalog_artifacts(payload, "PatentsView granted patent disambiguated")
    assert len(candidates) == 1
    assert candidates[0]["download_url"].endswith("patents-2025q4.jsonl")


def test_search_odp_products_follows_catalog_next_link(monkeypatch):
    responses = iter([
        {"products": [{"release": "2025-Q4"}], "next": "https://api.uspto.gov/api/v1/datasets/products/search?page=2"},
        {"products": [{"release": "2026-Q1"}]},
    ])

    class Response:
        status = 200

        def __init__(self, payload):
            self.payload = json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size=-1):
            return self.payload

    def fake_open(request: Request, **kwargs):
        return Response(next(responses))

    monkeypatch.setattr(uspto_odp, "open_url_with_retries", fake_open)
    result = json.loads(uspto_odp.search_odp_products("patents", "key"))
    assert [item["release"] for item in result["products"]] == ["2025-Q4", "2026-Q1"]
    assert result["_pagination"]["pages_fetched"] == 2


def test_search_odp_products_retries_rate_limit(monkeypatch):
    calls = {"count": 0}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size=-1):
            return b'{"products": []}'

    def fake_urlopen(request, timeout, context):
        calls["count"] += 1
        if calls["count"] == 1:
            raise HTTPError(request.full_url, 429, "rate limited", {}, None)
        return Response()

    monkeypatch.setattr(uspto_odp, "_official_open", fake_urlopen)
    monkeypatch.setattr("diligence_pipelines.sources.base.time.sleep", lambda seconds: None)
    assert json.loads(uspto_odp.search_odp_products("patents", "key"))["products"] == []
    assert calls["count"] == 2


def test_review_catalog_artifact_requires_reviewer_note():
    discovery = {"discovery_id": "d1", "candidates": [{"download_url": "https://example.test/a"}]}
    selection = uspto_odp.review_catalog_artifact(discovery, candidate_index=0, reviewer="analyst", note="Matches approved product")
    assert selection["status"] == "approved_for_download"
    assert selection["download_url"].endswith("/a")


def test_live_shaped_catalog_resolves_one_exact_product_and_artifact():
    search = Path("tests/fixtures/odp_search_products.json").read_bytes()
    detail = Path("tests/fixtures/odp_product_PVGPATDIS.json").read_bytes()

    candidate = uspto_odp.select_odp_candidate(search, detail, "PVGPATDIS", "g_patent.tsv.zip")

    assert candidate["logical_artifact_id"] == "uspto_odp:PVGPATDIS:g_patent.tsv.zip"
    assert candidate["file_size"] == 232076712
    assert candidate["download_url"].endswith("/PVGPATDIS/g_patent.tsv.zip")
    assert candidate["candidate_fingerprint"]


def test_title_change_does_not_change_artifact_revision():
    search = json.loads(Path("tests/fixtures/odp_search_products.json").read_text())
    detail = Path("tests/fixtures/odp_product_PVGPATDIS.json").read_bytes()
    original = uspto_odp.select_odp_candidate(json.dumps(search).encode(), detail, "PVGPATDIS", "g_patent.tsv.zip")
    search["bulkDataProductBag"][1]["productTitleText"] = "A new display title"

    renamed = uspto_odp.select_odp_candidate(json.dumps(search).encode(), detail, "PVGPATDIS", "g_patent.tsv.zip")

    assert renamed["candidate_fingerprint"] == original["candidate_fingerprint"]


def test_file_size_change_creates_new_candidate_revision():
    search = Path("tests/fixtures/odp_search_products.json").read_bytes()
    detail = json.loads(Path("tests/fixtures/odp_product_PVGPATDIS.json").read_text())
    original = uspto_odp.select_odp_candidate(search, json.dumps(detail).encode(), "PVGPATDIS", "g_patent.tsv.zip")
    detail["bulkDataProductBag"][0]["productFileBag"]["fileDataBag"][0]["fileSize"] += 1
    changed = uspto_odp.select_odp_candidate(search, json.dumps(detail).encode(), "PVGPATDIS", "g_patent.tsv.zip")
    assert changed["candidate_fingerprint"] != original["candidate_fingerprint"]


def test_incomplete_search_and_off_host_file_are_rejected():
    search = json.loads(Path("tests/fixtures/odp_search_products.json").read_text())
    detail = json.loads(Path("tests/fixtures/odp_product_PVGPATDIS.json").read_text())
    search["count"] += 1
    with pytest.raises(ValueError, match="Incomplete"):
        uspto_odp.select_odp_candidate(json.dumps(search).encode(), json.dumps(detail).encode(), "PVGPATDIS", "g_patent.tsv.zip")
    search["count"] -= 1
    detail["bulkDataProductBag"][0]["productFileBag"]["fileDataBag"][0]["fileDownloadURI"] = "https://elsewhere.example/g_patent.tsv.zip"
    with pytest.raises(ValueError, match="download URL"):
        uspto_odp.select_odp_candidate(json.dumps(search).encode(), json.dumps(detail).encode(), "PVGPATDIS", "g_patent.tsv.zip")


@pytest.mark.parametrize("change", ["missing_product", "duplicate_product", "missing_file", "duplicate_file"])
def test_missing_or_ambiguous_provider_records_block_selection(change):
    search = json.loads(Path("tests/fixtures/odp_search_products.json").read_text())
    detail = json.loads(Path("tests/fixtures/odp_product_PVGPATDIS.json").read_text())
    if change == "missing_product":
        search["bulkDataProductBag"].pop()
        search["count"] -= 1
    elif change == "duplicate_product":
        search["bulkDataProductBag"].append(search["bulkDataProductBag"][-1])
        search["count"] += 1
    elif change == "missing_file":
        detail["bulkDataProductBag"][0]["productFileBag"]["fileDataBag"].pop(0)
        detail["bulkDataProductBag"][0]["productFileBag"]["count"] -= 1
    else:
        files = detail["bulkDataProductBag"][0]["productFileBag"]
        files["fileDataBag"].append(files["fileDataBag"][0])
        files["count"] += 1

    with pytest.raises(ValueError, match="product|artifact"):
        uspto_odp.select_odp_candidate(json.dumps(search).encode(), json.dumps(detail).encode(), "PVGPATDIS", "g_patent.tsv.zip")
