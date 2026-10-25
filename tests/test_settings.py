from pathlib import Path

from diligence_pipelines.settings import Settings


def test_yaml_variables_are_loaded_and_environment_overrides(tmp_path: Path, monkeypatch):
    variables = tmp_path / "variables.yaml"
    variables.write_text("DILIGENCE_STORAGE_BACKEND: postgres\nDILIGENCE_POSTGRES_PORT: 55433\nSEC_USER_AGENT: yaml-agent\nOPENALEX_EMAIL: analyst@example.com\n")
    monkeypatch.setenv("DILIGENCE_VARIABLES_FILE", str(variables))
    monkeypatch.setenv("DILIGENCE_POSTGRES_PORT", "55434")
    settings = Settings.from_env()
    assert settings.storage_backend == "postgres"
    assert settings.postgres_port == 55434
    assert settings.sec_user_agent == "yaml-agent"
    assert settings.openalex_email == "analyst@example.com"


def test_comtrade_primary_and_secondary_keys_are_ordered_without_exposing_values(tmp_path: Path, monkeypatch):
    variables = tmp_path / "variables.yaml"
    variables.write_text("COMTRADE_API_KEY_PRIMARY: primary-secret\nCOMTRADE_API_KEY_SECONDARY: secondary-secret\n")
    monkeypatch.setenv("DILIGENCE_VARIABLES_FILE", str(variables))
    settings = Settings.from_env()
    assert settings.comtrade_api_keys == ("primary-secret", "secondary-secret")


def test_slack_webhook_configuration_is_optional_and_environment_scoped(monkeypatch):
    monkeypatch.setenv("DILIGENCE_ALERT_SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/example")
    assert Settings.from_env().alert_slack_webhook_url == "https://hooks.slack.com/services/example"
