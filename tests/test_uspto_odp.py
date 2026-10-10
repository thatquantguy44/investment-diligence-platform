import json
from pathlib import Path

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
