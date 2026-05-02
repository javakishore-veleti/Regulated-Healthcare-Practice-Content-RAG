from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "rhc_admin"
    db_password: str = "rhc_local_dev"
    db_name: str = "rag_app"
    db_pool_min_size: int = 1
    db_pool_max_size: int = 5

    otel_service_name: str = "datamgmt-service"
    otel_exporter_otlp_endpoint: str | None = None

    api_host: str = "0.0.0.0"
    api_port: int = 8001

    # Airflow integration. When airflow_base_url is set, the ingest flow triggers a
    # DAG via Airflow's REST API instead of running the synchronous storage-handler stub.
    airflow_base_url: str | None = None
    airflow_username: str = "admin"
    airflow_password: str = "admin"
    airflow_poll_interval_secs: float = 1.5
    airflow_timeout_secs: float = 180.0

    @property
    def db_conninfo(self) -> str:
        return (
            f"host={self.db_host} port={self.db_port} "
            f"user={self.db_user} password={self.db_password} dbname={self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
