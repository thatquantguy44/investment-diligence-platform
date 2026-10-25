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
    openalex_email: str | None = None
    uspto_api_key: str | None = None
    uspto_api_url: str = "https://search.patentsview.org/api/v1/patent/"
    uspto_odp_catalog_url: str = "https://api.uspto.gov/api/v1/datasets/products/search"
    uspto_odp_product_query: str = "PatentsView granted patent disambiguated"
    uspto_odp_discovery_output: Path = Path(".data/uspto/odp_discovery.json")
    uspto_odp_reviewed_selection: Path = Path(".data/uspto/reviewed_selection.json")
    uspto_odp_refresh_output: Path = Path(".data/uspto/g_patent.tsv.zip")
    uspto_odp_previous_file: Path | None = None
    uspto_odp_refresh_max_age_days: int = 45
    alert_slack_webhook_url: str | None = None
    comtrade_api_key: str | None = None
    comtrade_api_key_primary: str | None = None
    comtrade_api_key_secondary: str | None = None
    comtrade_api_url: str = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
    usaspending_award_search_url: str = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
    usaspending_transactions_url: str = "https://api.usaspending.gov/api/v2/transactions/"
    gdelt_doc_api_url: str = "https://api.gdeltproject.org/api/v2/doc/doc"
    llm_base_url: str = "http://localhost:11434"
    llm_event_model: str = ""
    sector_reviewer_config: Path = Path("config/sector_reviewers.yaml")

    @property
    def comtrade_api_keys(self) -> tuple[str, ...]:
        """Return configured Comtrade keys in primary-to-secondary order."""
        keys = (self.comtrade_api_key_primary or self.comtrade_api_key, self.comtrade_api_key_secondary)
        return tuple(dict.fromkeys(key for key in keys if key))

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
            openalex_email=value("OPENALEX_EMAIL", "") or None,
            uspto_api_key=value("USPTO_API_KEY", "") or None,
            uspto_api_url=value("USPTO_API_URL", "https://search.patentsview.org/api/v1/patent/"),
            uspto_odp_catalog_url=value("USPTO_ODP_CATALOG_URL", "https://api.uspto.gov/api/v1/datasets/products/search"),
            uspto_odp_product_query=value("USPTO_ODP_PRODUCT_QUERY", "PatentsView granted patent disambiguated"),
            uspto_odp_discovery_output=Path(value("USPTO_ODP_DISCOVERY_OUTPUT", ".data/uspto/odp_discovery.json")),
            uspto_odp_reviewed_selection=Path(value("USPTO_ODP_REVIEWED_SELECTION", ".data/uspto/reviewed_selection.json")),
            uspto_odp_refresh_output=Path(value("USPTO_ODP_REFRESH_OUTPUT", ".data/uspto/g_patent.tsv.zip")),
            uspto_odp_previous_file=Path(value("USPTO_ODP_PREVIOUS_FILE", "")) if value("USPTO_ODP_PREVIOUS_FILE", "") else None,
            uspto_odp_refresh_max_age_days=int(value("USPTO_ODP_REFRESH_MAX_AGE_DAYS", "45")),
            alert_slack_webhook_url=value("DILIGENCE_ALERT_SLACK_WEBHOOK_URL", "") or None,
            comtrade_api_key=value("COMTRADE_API_KEY", "") or None,
            comtrade_api_key_primary=value("COMTRADE_API_KEY_PRIMARY", "") or value("COMTRADE_API_KEY", "") or None,
            comtrade_api_key_secondary=value("COMTRADE_API_KEY_SECONDARY", "") or None,
            comtrade_api_url=value("COMTRADE_API_URL", "https://comtradeapi.un.org/public/v1/preview/C/A/HS"),
            usaspending_award_search_url=value("USASPENDING_AWARD_SEARCH_URL", "https://api.usaspending.gov/api/v2/search/spending_by_award/"),
            usaspending_transactions_url=value("USASPENDING_TRANSACTIONS_URL", "https://api.usaspending.gov/api/v2/transactions/"),
            gdelt_doc_api_url=value("GDELT_DOC_API_URL", "https://api.gdeltproject.org/api/v2/doc/doc"),
            llm_base_url=value("LLM_BASE_URL", "http://localhost:11434"),
            llm_event_model=value("LLM_EVENT_MODEL", ""),
            sector_reviewer_config=Path(value("DILIGENCE_SECTOR_REVIEWER_CONFIG", "config/sector_reviewers.yaml")),
        )
