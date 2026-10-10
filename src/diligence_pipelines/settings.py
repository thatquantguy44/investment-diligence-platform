from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Settings:
    data_root: Path = Path(".data")
    environment: str = "local"
    storage_backend: str = "local"
    postgres_dsn: str | None = None
    postgres_host: str = "localhost"
    postgres_port: int = 55432
    postgres_db: str = "IDP"
    postgres_user: str = "postgres"
    postgres_password: str = ""
    sec_user_agent: str = "investment-diligence-pipelines/0.1 contact@example.com"
    uspto_api_key: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        variables_path = Path(os.getenv("DILIGENCE_VARIABLES_FILE", "config/variables.yaml"))
        variables = {}
        if variables_path.exists():
            loaded = yaml.safe_load(variables_path.read_text()) or {}
            if not isinstance(loaded, dict):
                raise ValueError(f"Variables file must contain a YAML mapping: {variables_path}")
            variables = {str(key): value for key, value in loaded.items()}

        def value(name: str, default: str) -> str:
            environment_value = os.getenv(name)
            if environment_value is not None:
                return environment_value
            configured_value = variables.get(name)
            return default if configured_value is None else str(configured_value)

        return cls(
            data_root=Path(value("DILIGENCE_DATA_ROOT", ".data")),
            environment=value("DILIGENCE_ENV", "local"),
            storage_backend=value("DILIGENCE_STORAGE_BACKEND", "local"),
            postgres_dsn=value("DILIGENCE_POSTGRES_DSN", "") or None,
            postgres_host=value("DILIGENCE_POSTGRES_HOST", "localhost"),
            postgres_port=int(value("DILIGENCE_POSTGRES_PORT", "55432")),
            postgres_db=value("DILIGENCE_POSTGRES_DB", "IDP"),
            postgres_user=value("DILIGENCE_POSTGRES_USER", "postgres"),
            postgres_password=value("DILIGENCE_POSTGRES_PASSWORD", ""),
            sec_user_agent=value("SEC_USER_AGENT", "investment-diligence-pipelines/0.1 contact@example.com"),
            uspto_api_key=value("USPTO_API_KEY", "") or None,
        )
