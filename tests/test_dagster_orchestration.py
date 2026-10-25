import pytest


def test_dagster_uspto_definitions_load():
    dagster = pytest.importorskip("dagster")
    from diligence_pipelines.orchestration.dagster_defs import defs

    dagster.Definitions.validate_loadable(defs)
