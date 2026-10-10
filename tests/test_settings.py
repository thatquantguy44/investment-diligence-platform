from pathlib import Path

from diligence_pipelines.settings import Settings


def test_yaml_variables_are_loaded_and_environment_overrides(tmp_path: Path, monkeypatch):
    variables = tmp_path / "variables.yaml"
    variables.write_text("DILIGENCE_STORAGE_BACKEND: postgres\nDILIGENCE_POSTGRES_PORT: 55433\nSEC_USER_AGENT: yaml-agent\n")
    monkeypatch.setenv("DILIGENCE_VARIABLES_FILE", str(variables))
    monkeypatch.setenv("DILIGENCE_POSTGRES_PORT", "55434")
    settings = Settings.from_env()
    assert settings.storage_backend == "postgres"
    assert settings.postgres_port == 55434
    assert settings.sec_user_agent == "yaml-agent"
