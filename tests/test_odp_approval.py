import json
import os
import pwd
import hashlib
import io
import stat
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

import pytest

from diligence_pipelines.cli import discover_uspto_odp, refresh_uspto_odp, review_uspto_odp
from diligence_pipelines.settings import Settings
from diligence_pipelines.sources.uspto_odp import BulkArtifact
from diligence_pipelines.odp_execution import load_execution_state, record_outcome, request_retry, run_key_for_state


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_root=tmp_path,
        environment="test",
        uspto_odp_reviewer_name="Analyst",
        uspto_odp_reviewer_os_user=pwd.getpwuid(os.geteuid()).pw_name,
    )


def _discovery(tmp_path: Path, settings: Settings) -> Path:
    path = tmp_path / "discovery.json"
    assert discover_uspto_odp(
        None, path, Path("tests/fixtures/odp_search_products.json"), settings,
        Path("tests/fixtures/odp_product_PVGPATDIS.json"),
    ) == 0
    return path


def test_review_binds_candidate_to_immutable_discovery_and_os_actor(tmp_path: Path):
    settings = _settings(tmp_path)
    discovery = _discovery(tmp_path, settings)
    selection = tmp_path / "reviewed_selection.json"

    assert review_uspto_odp(discovery, 0, "Analyst", "Checked provider file metadata", selection, settings) == 0

    active = json.loads(selection.read_text())
    report = json.loads(discovery.read_text())
    assert active["status"] == "approved_for_download"
    assert active["candidate_fingerprint"] == report["candidates"][0]["candidate_fingerprint"]
    assert active["discovery_id"] == report["discovery_id"]
    assert active["actor_os_user"] == settings.uspto_odp_reviewer_os_user
    approval_record = tmp_path / "uspto/approvals" / f"{active['approval_id']}.json"
    discovery_record = tmp_path / "uspto/discoveries" / f"{report['discovery_id']}.json"
    assert stat.S_IMODE(approval_record.stat().st_mode) == 0o400
    assert stat.S_IMODE(discovery_record.stat().st_mode) == 0o400


def test_review_rejects_modified_snapshot_and_wrong_os_reviewer(tmp_path: Path):
    settings = _settings(tmp_path)
    discovery = _discovery(tmp_path, settings)
    output = tmp_path / "selection.json"
    report = json.loads(discovery.read_text())
    report["candidates"][0]["download_url"] = "https://example.test/other.zip"
    discovery.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="modified|snapshot"):
        review_uspto_odp(discovery, 0, "Analyst", "Checked metadata", output, settings)
    assert not output.exists()

    original = tmp_path / "uspto/discoveries" / f"{report['discovery_id']}.json"
    discovery.write_bytes(original.read_bytes())
    unauthorized = Settings(data_root=tmp_path, environment="test", uspto_odp_reviewer_name="Analyst", uspto_odp_reviewer_os_user="not-this-user")
    with pytest.raises(PermissionError, match="reviewer"):
        review_uspto_odp(discovery, 0, "Analyst", "Checked metadata", output, unauthorized)
    assert not output.exists()


def test_refresh_rejects_legacy_url_only_selection_before_download(tmp_path: Path, monkeypatch):
    selection = tmp_path / "legacy.json"
    selection.write_text(json.dumps({"status": "approved_for_download", "download_url": "https://example.test/file.zip"}))
    monkeypatch.setattr("diligence_pipelines.cli.download_bulk_artifact", lambda *args, **kwargs: pytest.fail("download attempted"))
    report_path = tmp_path / "refresh.json"

    assert refresh_uspto_odp(selection, tmp_path / "file.zip", None, report_path, None, None, 10, _settings(tmp_path)) == 2
    assert json.loads(report_path.read_text())["status"] == "blocked"


def test_refresh_blocks_changed_provider_detail_before_download(tmp_path: Path, monkeypatch):
    settings = replace(_settings(tmp_path), uspto_api_key="test-key", uspto_odp_min_size_bytes=1,
                       uspto_odp_max_size_bytes=300_000_000, uspto_odp_max_release_age_days=365,
                       uspto_odp_refresh_max_age_days=10)
    discovery = _discovery(tmp_path, settings)
    selection = tmp_path / "selection.json"
    review_uspto_odp(discovery, 0, "Analyst", "Checked metadata", selection, settings)
    detail = json.loads(Path("tests/fixtures/odp_product_PVGPATDIS.json").read_text())
    detail["bulkDataProductBag"][0]["productFileBag"]["fileDataBag"][0]["fileSize"] += 1
    monkeypatch.setattr("diligence_pipelines.cli.fetch_odp_product", lambda *args: json.dumps(detail).encode())
    monkeypatch.setattr("diligence_pipelines.cli.download_bulk_artifact", lambda *args, **kwargs: pytest.fail("download attempted"))
    report_path = tmp_path / "refresh.json"

    assert refresh_uspto_odp(selection, tmp_path / "g_patent.tsv.zip", None, report_path, None, None, 10, settings) == 2
    report = json.loads(report_path.read_text())
    assert report["status"] == "blocked"
    assert "changed" in report["reason"]


def test_refresh_requires_reviewed_bounds_before_provider_request(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path)
    discovery = _discovery(tmp_path, settings)
    selection = tmp_path / "selection.json"
    review_uspto_odp(discovery, 0, "Analyst", "Checked metadata", selection, settings)
    monkeypatch.setattr("diligence_pipelines.cli.fetch_odp_product", lambda *args: pytest.fail("provider request attempted"))
    report_path = tmp_path / "refresh.json"

    assert refresh_uspto_odp(selection, tmp_path / "g_patent.tsv.zip", None, report_path, None, None, 10, settings) == 2
    assert "limits are required" in json.loads(report_path.read_text())["reason"]


def _approved_small_release(tmp_path: Path, payload: bytes, provider_checksum: str | None = None):
    today = datetime.now(timezone.utc).date().isoformat()
    settings = replace(
        _settings(tmp_path), uspto_api_key="test-key", uspto_odp_min_size_bytes=1,
        uspto_odp_max_size_bytes=100_000, uspto_odp_max_release_age_days=1,
        uspto_odp_refresh_max_age_days=1,
    )
    detail = json.loads(Path("tests/fixtures/odp_product_PVGPATDIS.json").read_text())
    file = detail["bulkDataProductBag"][0]["productFileBag"]["fileDataBag"][0]
    file["fileSize"] = len(payload)
    file["fileReleaseDate"] = f"{today} 12:00:00"
    if provider_checksum is not None:
        file["fileChecksum"] = provider_checksum
    detail_bytes = json.dumps(detail).encode()
    detail_path = tmp_path / "product.json"
    detail_path.write_bytes(detail_bytes)
    discovery = tmp_path / "discovery.json"
    assert discover_uspto_odp(None, discovery, Path("tests/fixtures/odp_search_products.json"), settings, detail_path) == 0
    selection = tmp_path / "selection.json"
    assert review_uspto_odp(discovery, 0, "Analyst", "Checked exact file", selection, settings) == 0
    return settings, selection, detail_bytes


def _zip_payload() -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("g_patent.tsv", f"patent_id\tpatent_title\tpatent_date\nT1\tDemo patent\t{datetime.now(timezone.utc).date().isoformat()}\n")
    return buffer.getvalue()


def test_refresh_prepares_verified_archive_without_ingestion(tmp_path: Path, monkeypatch):
    payload = _zip_payload()
    settings, selection, detail = _approved_small_release(tmp_path, payload)
    monkeypatch.setattr("diligence_pipelines.cli.fetch_odp_product", lambda *args: detail)

    def fake_download(url, destination, api_key=None, **kwargs):
        destination.write_bytes(payload)
        return BulkArtifact(str(destination), url, datetime.now(timezone.utc).isoformat(), hashlib.sha256(payload).hexdigest(), len(payload), 200)

    monkeypatch.setattr("diligence_pipelines.cli.download_bulk_artifact", fake_download)
    output = tmp_path / "g_patent.tsv.zip"
    report_path = tmp_path / "refresh.json"
    assert refresh_uspto_odp(selection, output, None, report_path, None, 1, 10, settings) == 0
    report = json.loads(report_path.read_text())
    assert report["status"] == "prepared"
    assert report["ingestion_status"] == "not_started"
    assert output.read_bytes() == payload


def test_refresh_preserves_previous_artifact_on_size_mismatch(tmp_path: Path, monkeypatch):
    payload = _zip_payload()
    settings, selection, detail = _approved_small_release(tmp_path, payload)
    monkeypatch.setattr("diligence_pipelines.cli.fetch_odp_product", lambda *args: detail)
    output = tmp_path / "g_patent.tsv.zip"
    output.write_bytes(b"previous-good-release")
    sidecar = Path(str(output) + ".json")
    sidecar.write_text('{"content_sha256":"previous"}\n')

    def wrong_size(url, destination, api_key=None, **kwargs):
        destination.write_bytes(payload + b"x")
        return BulkArtifact(str(destination), url, datetime.now(timezone.utc).isoformat(), hashlib.sha256(payload + b"x").hexdigest(), len(payload) + 1, 200)

    monkeypatch.setattr("diligence_pipelines.cli.download_bulk_artifact", wrong_size)
    report_path = tmp_path / "refresh.json"
    assert refresh_uspto_odp(selection, output, None, report_path, None, 1, 10, settings) == 2
    assert output.read_bytes() == b"previous-good-release"
    assert json.loads(sidecar.read_text())["content_sha256"] == "previous"
    assert json.loads(report_path.read_text())["status"] == "failed"


def test_refresh_records_download_failure_without_ingesting(tmp_path: Path, monkeypatch):
    payload = _zip_payload()
    settings, selection, detail = _approved_small_release(tmp_path, payload)
    monkeypatch.setattr("diligence_pipelines.cli.fetch_odp_product", lambda *args: detail)
    monkeypatch.setattr("diligence_pipelines.cli.download_bulk_artifact", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("source unavailable")))
    report_path = tmp_path / "refresh.json"

    assert refresh_uspto_odp(selection, tmp_path / "g_patent.tsv.zip", None, report_path, None, 1, 10, settings) == 2
    report = json.loads(report_path.read_text())
    assert report["status"] == "failed"
    assert report["ingestion_status"] == "not_started"
    assert report["error"] == "source unavailable"
    history = tmp_path / "indexes/uspto_patents/odp_refresh_history.jsonl"
    assert json.loads(history.read_text().splitlines()[-1])["status"] == "failed"


def test_download_failure_remains_terminal_when_refresh_history_is_unavailable(tmp_path: Path, monkeypatch):
    from diligence_pipelines import cli

    settings, selection, detail = _approved_small_release(tmp_path, _zip_payload())
    monkeypatch.setattr(cli, "fetch_odp_product", lambda *args: detail)
    monkeypatch.setattr(cli, "download_bulk_artifact", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("source unavailable")))
    original_build_storage = cli.build_storage

    class StorageWithFailedHistory:
        def __init__(self, storage):
            self.storage = storage

        def read_raw(self, *args):
            return self.storage.read_raw(*args)

        def write_raw(self, *args):
            return self.storage.write_raw(*args)

        def record_uspto_odp_refresh(self, report):
            raise OSError("refresh history volume unavailable")

    monkeypatch.setattr(cli, "build_storage", lambda current_settings: StorageWithFailedHistory(original_build_storage(current_settings)))
    report_path = tmp_path / "refresh.json"

    assert refresh_uspto_odp(selection, tmp_path / "g_patent.tsv.zip", None, report_path, None, 1, 10, settings) == 2
    assert load_execution_state(settings, json.loads(selection.read_text()))["status"] == "failed"
    assert "refresh history volume unavailable" in json.loads(report_path.read_text())["history_record_error"]


def test_refresh_rejects_invalid_archive_before_replacing_previous(tmp_path: Path, monkeypatch):
    payload = b"not-a-zip"
    settings, selection, detail = _approved_small_release(tmp_path, payload)
    monkeypatch.setattr("diligence_pipelines.cli.fetch_odp_product", lambda *args: detail)
    output = tmp_path / "g_patent.tsv.zip"
    output.write_bytes(b"prior")

    def fake_download(url, destination, api_key=None, **kwargs):
        destination.write_bytes(payload)
        return BulkArtifact(str(destination), url, datetime.now(timezone.utc).isoformat(), hashlib.sha256(payload).hexdigest(), len(payload), 200)

    monkeypatch.setattr("diligence_pipelines.cli.download_bulk_artifact", fake_download)
    report_path = tmp_path / "refresh.json"
    assert refresh_uspto_odp(selection, output, None, report_path, None, 1, 10, settings) == 2
    assert output.read_bytes() == b"prior"
    assert json.loads(report_path.read_text())["status"] == "failed"


def test_refresh_rejects_provider_checksum_mismatch(tmp_path: Path, monkeypatch):
    payload = _zip_payload()
    settings, selection, detail = _approved_small_release(tmp_path, payload, provider_checksum="0" * 64)
    monkeypatch.setattr("diligence_pipelines.cli.fetch_odp_product", lambda *args: detail)

    def fake_download(url, destination, api_key=None, **kwargs):
        destination.write_bytes(payload)
        return BulkArtifact(str(destination), url, datetime.now(timezone.utc).isoformat(), hashlib.sha256(payload).hexdigest(), len(payload), 200)

    monkeypatch.setattr("diligence_pipelines.cli.download_bulk_artifact", fake_download)
    report_path = tmp_path / "refresh.json"
    assert refresh_uspto_odp(selection, tmp_path / "g_patent.tsv.zip", None, report_path, None, 1, 10, settings) == 2
    assert "provider checksum" in json.loads(report_path.read_text())["error"]


def test_refresh_rejects_modified_active_pointer(tmp_path: Path, monkeypatch):
    settings, selection, _ = _approved_small_release(tmp_path, _zip_payload())
    active = json.loads(selection.read_text())
    active["candidate_fingerprint"] = "sha256:tampered"
    selection.write_text(json.dumps(active))
    monkeypatch.setattr("diligence_pipelines.cli.download_bulk_artifact", lambda *args, **kwargs: pytest.fail("download attempted"))
    report_path = tmp_path / "refresh.json"
    assert refresh_uspto_odp(selection, tmp_path / "g_patent.tsv.zip", None, report_path, None, 1, 10, settings) == 2
    assert json.loads(report_path.read_text())["status"] == "blocked"


def test_failed_approval_requires_audited_retry_with_new_dagster_run_key(tmp_path: Path):
    payload = _zip_payload()
    settings, selection, _ = _approved_small_release(tmp_path, payload)
    active = json.loads(selection.read_text())
    initial = load_execution_state(settings, active)
    first_key = run_key_for_state(active, initial)
    record_outcome(settings, active, {"refresh_id": "failed-run", "status": "failed"})
    assert run_key_for_state(active, load_execution_state(settings, active)) is None

    retry = request_retry(settings, selection, "Network outage resolved")

    resumed = load_execution_state(settings, active)
    assert retry["attempt"] == 1
    assert resumed["status"] == "retry_requested"
    assert run_key_for_state(active, resumed) != first_key
    assert (tmp_path / "uspto/retries" / f"{retry['retry_id']}.json").exists()
