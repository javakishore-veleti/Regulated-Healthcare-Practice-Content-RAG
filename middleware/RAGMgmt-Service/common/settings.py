from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from common.secrets import resolve_secret


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
    # `stub`, `anthropic`, or `bedrock`. The README architecture calls for Bedrock
    # Claude Opus for drafting; the direct Anthropic API path is the local-dev
    # default.
    llm_drafter: str = "auto"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-7"
    anthropic_max_tokens: int = 1500

    # Bedrock drafter — used when LLM_DRAFTER=bedrock. Requires the optional
    # extra: `pip install '.[bedrock-drafter]'`. Credentials come from the
    # standard AWS chain (env, ~/.aws/credentials, IRSA, SSO). Set
    # BEDROCK_MODEL_ID to the Bedrock identifier of your Claude model
    # (e.g. an inference profile like `us.anthropic.claude-opus-4-7-…-v1:0`).
    bedrock_model_id: str = ""
    bedrock_region: str = "us-east-1"

    # Self-RAG regenerate loop: when a draft fails the faithfulness threshold AND the
    # active drafter supports regeneration, recompose with a hint up to this many
    # extra times. Capped low (1) for cost; real production tuning lives downstream.
    max_regenerate_attempts: int = 1

    # Cross-encoder rerank — the third stage of Hybrid+Rerank. `token_overlap`
    # is a pure-stdlib reranker that blends RRF with query/chunk token overlap.
    # `identity` falls back to truncate-only (the pre-slice behavior). A real
    # cross-encoder (e.g. ms-marco-MiniLM-L-6-v2) plugs in via the same
    # `IReranker` interface — see service/rerank/reranker.py.
    rag_reranker_backend: str = "token_overlap"
    rag_reranker_alpha: float = 0.5

    # Langfuse — the README's primary observability mechanism. Captures
    # prompt/completion + retrieved-chunk metadata + faithfulness scores per
    # generation request. All three fields unset → gracefully disabled (no-op).
    # The langfuse SDK is an optional extra (`pip install '.[langfuse]'`); when
    # not installed this is also disabled regardless of host.
    langfuse_host: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_environment: str | None = None

    @field_validator("langfuse_secret_key", "langfuse_public_key", mode="after")
    @classmethod
    def _resolve_langfuse_credentials(cls, v: str | None) -> str | None:
        # Same resolution as db_password / anthropic_api_key — accepts cloud
        # secret-manager refs (`aws-sm://...`, `azure-kv://...`, `gcp-sm://...`).
        return resolve_secret(v)

    @field_validator("db_password", "anthropic_api_key", mode="after")
    @classmethod
    def _resolve_credentials(cls, v: str | None) -> str | None:
        # Sensitive fields can carry secret-manager references like
        # `aws-sm://...`, `azure-kv://...`, `gcp-sm://...`. Local dev passes
        # through literal values unchanged.
        return resolve_secret(v)

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
