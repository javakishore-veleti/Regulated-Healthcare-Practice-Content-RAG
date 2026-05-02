from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "rhc_admin"
    db_password: str = "rhc_local_dev"
    db_name: str = "rag_app"
    rag_vectors_db_name: str = "rag_vectors"
    db_pool_min_size: int = 1
    db_pool_max_size: int = 5

    otel_service_name: str = "ragmgmt-service"
    otel_exporter_otlp_endpoint: str | None = None

    api_host: str = "0.0.0.0"
    api_port: int = 8002

    # LLM drafter selection. `auto` picks AnthropicDrafter when anthropic_api_key is
    # set, falls back to StubDrafter otherwise. Force a specific drafter with
    # `stub` or `anthropic`. The Excel architecture calls for Bedrock Claude Opus
    # 4.7 for drafting; using the direct Anthropic API here for local dev.
    llm_drafter: str = "auto"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-7"
    anthropic_max_tokens: int = 1500

    # Self-RAG regenerate loop: when a draft fails the faithfulness threshold AND the
    # active drafter supports regeneration, recompose with a hint up to this many
    # extra times. Capped low (1) for cost; real production tuning lives downstream.
    max_regenerate_attempts: int = 1

    @property
    def db_conninfo(self) -> str:
        return self._conninfo(self.db_name)

    @property
    def rag_vectors_db_conninfo(self) -> str:
        return self._conninfo(self.rag_vectors_db_name)

    def _conninfo(self, dbname: str) -> str:
        return (
            f"host={self.db_host} port={self.db_port} "
            f"user={self.db_user} password={self.db_password} dbname={dbname}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
