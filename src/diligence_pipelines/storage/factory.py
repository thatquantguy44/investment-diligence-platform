from __future__ import annotations

from diligence_pipelines.settings import Settings
from diligence_pipelines.storage.local import LocalStorage
from diligence_pipelines.storage.postgres import PostgresStorage


def postgres_dsn(settings: Settings) -> str:
    if settings.postgres_dsn:
        return settings.postgres_dsn
    password = f":{settings.postgres_password}" if settings.postgres_password else ""
    return f"postgresql://{settings.postgres_user}{password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"


def build_storage(settings: Settings):
    if settings.storage_backend == "local":
        return LocalStorage(settings.data_root)
    if settings.storage_backend == "postgres":
        storage = PostgresStorage(postgres_dsn(settings))
        storage.initialize()
        return storage
    raise ValueError(f"Unsupported DILIGENCE_STORAGE_BACKEND: {settings.storage_backend}")
