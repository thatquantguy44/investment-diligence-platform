import pytest


def test_approved_sensor_emits_one_run_and_waits_for_explicit_retry(tmp_path, monkeypatch):
    dagster = pytest.importorskip("dagster")
    from diligence_pipelines.orchestration.dagster_defs import approved_uspto_selection_sensor
    from diligence_pipelines.odp_execution import record_outcome, request_retry
    from diligence_pipelines.settings import Settings
    from test_odp_approval import _approved_small_release, _zip_payload
    import json

    settings, selection, _ = _approved_small_release(tmp_path, _zip_payload())
    active_path = settings.uspto_odp_reviewed_selection_path
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_bytes(selection.read_bytes())
    active_path.chmod(0o600)
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: settings))
    context = dagster.build_sensor_context()
    first = approved_uspto_selection_sensor(context)
    assert isinstance(first, dagster.RunRequest)
    active = json.loads(active_path.read_text())
    record_outcome(settings, active, {"refresh_id": "failed-run", "status": "failed"})

    waiting = approved_uspto_selection_sensor(dagster.build_sensor_context(cursor=context.cursor))
    assert isinstance(waiting, dagster.SkipReason)
    retry = request_retry(settings, active_path, "Network restored")
    second = approved_uspto_selection_sensor(dagster.build_sensor_context(cursor=context.cursor))
    assert isinstance(second, dagster.RunRequest)
    assert second.run_key != first.run_key
    assert second.tags["attempt"] == str(retry["attempt"])


def test_dagster_uspto_definitions_load():
    dagster = pytest.importorskip("dagster")
    from diligence_pipelines.orchestration.dagster_defs import defs

    dagster.Definitions.validate_loadable(defs)
