import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

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
        {"products": [{"release": "2025-Q4"}], "next": "https://example.test/catalog?page=2"},
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

    monkeypatch.setattr("diligence_pipelines.sources.base.urlopen", fake_urlopen)
    monkeypatch.setattr("diligence_pipelines.sources.base.time.sleep", lambda seconds: None)
    assert json.loads(uspto_odp.search_odp_products("patents", "key"))["products"] == []
    assert calls["count"] == 2


def test_review_catalog_artifact_requires_reviewer_note():
    discovery = {"discovery_id": "d1", "candidates": [{"download_url": "https://example.test/a"}]}
    selection = uspto_odp.review_catalog_artifact(discovery, candidate_index=0, reviewer="analyst", note="Matches approved product")
    assert selection["status"] == "approved_for_download"
    assert selection["download_url"].endswith("/a")
