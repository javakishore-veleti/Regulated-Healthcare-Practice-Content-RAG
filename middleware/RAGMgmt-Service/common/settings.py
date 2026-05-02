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

    # Cross-encoder rerank — the third stage of Hybrid+Rerank.
    #
    # Backends:
    #   * token_overlap  — pure-stdlib RRF + Jaccard blend (default).
    #   * identity       — truncate-only (passthrough baseline).
    #   * cross_encoder  — learned reranker via sentence-transformers
    #                      (e.g. ms-marco-MiniLM-L-6-v2). Requires the
    #                      [cross-encoder-rerank] extra; ~2 GB transitive
    #                      deps + ~90 MB model download on first use. Falls
    #                      back to token_overlap when either the dep or
    #                      the model name is missing.
    rag_reranker_backend: str = "token_overlap"
    rag_reranker_alpha: float = 0.5
    rag_cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Embedder backend — query-side embedding for the dense retrieval leg.
    # `stub` is the SHA-256-derived embedder (default; deterministic, no deps,
    # but not semantically meaningful). `sentence_transformer` is a real
    # learned embedder via the [real-embedder] extra.
    #
    # NOTE: switching to sentence_transformer also requires re-embedding the
    # CORPUS — the DAG-side embedder in handlers/embed_via_pgvector.py needs
    # the same model swap. A query embedded with sentence_transformer against
    # a stub-embedded corpus produces meaningless similarity scores.
    rag_embedder_backend: str = "stub"
    rag_embedder_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Bedrock embedder — used when RAG_EMBEDDER_BACKEND=aws_bedrock. Project A
    # Excel names Amazon Titan Embed v2 OR Cohere Embed v4. The dim must match
    # the pgvector / OpenSearch column; Titan v2 supports a `dimensions`
    # parameter so the SAME column dim works on default (1024 for Cohere
    # alignment) — but if you keep the legacy 384-dim column, set this to
    # 384 and Titan will return 384-dim vectors via the `dimensions` request.
    bedrock_embedding_model_id: str = ""
    bedrock_embedding_dim: int = 384

    # Retrieval backend — where the corpus index lives.
    # `postgres` is the local-dev / single-region default (pgvector + tsvector
    # in the rag_vectors DB). `aws_opensearch_serverless` is the README's
    # AWS production target — see RAG_Mastery_Projects.xlsx Project A Task 7.
    # Falls back to postgres when the [opensearch] extra OR endpoint is missing.
    rag_retrieval_backend: str = "postgres"
    aws_opensearch_endpoint: str = ""    # https://<id>.<region>.aoss.amazonaws.com
    aws_opensearch_index: str = "rhc-child-chunks"
    aws_opensearch_region: str = "us-east-1"

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
