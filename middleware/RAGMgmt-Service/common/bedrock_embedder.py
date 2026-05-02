"""Embedder via AWS Bedrock — Excel Project A AWS architecture row "Embedding".

The Excel names two models: Amazon Titan Embeddings v2
(`amazon.titan-embed-text-v2:0`) and Cohere Embed v4
(`cohere.embed-english-v3`). Both are reachable through the same Bedrock
`InvokeModel` API; only the request body shape differs. This embedder
auto-detects which family to format for based on the model id prefix.

Optional dep — install via `pip install '.[bedrock-drafter]'` (boto3 is
shared with the drafter; one extra installs both). Auth via the standard
AWS chain (env / IRSA / Pod Identity / SSO). The factory falls back to
StubEmbedder when boto3 is missing OR `BEDROCK_EMBEDDING_MODEL_ID` is
unset.

Dimension expectations:

  amazon.titan-embed-text-v2:0   → 1024 (configurable via `dimensions`
                                          parameter; we request 1024 by
                                          default to match the Cohere
                                          family for swap convenience)
  cohere.embed-english-v3        → 1024
  amazon.titan-embed-text-v1     → 1536 (legacy; configurable here)

Setting `RAG_EMBEDDER_BACKEND=aws_bedrock` REQUIRES updating the pgvector
column dimension (or the OpenSearch knn_vector dim) to match — see the
operator how-to. The DAG-side ingest handler also needs the same Bedrock
embedder to produce a coherent corpus index.
"""

from __future__ import annotations

import json
import logging

from common.otel_genai import (
    OP_EMBEDDING,
    SYSTEM_AWS_BEDROCK,
    set_gen_ai_request,
    set_gen_ai_response,
)

LOGGER = logging.getLogger(__name__)


class BedrockEmbedder:
    name = "aws_bedrock"

    def __init__(
        self,
        model_id: str,
        region: str,
        expected_dim: int,
        cohere_input_type: str = "search_query",
    ) -> None:
        if not model_id:
            raise ValueError(
                "BedrockEmbedder requires a model_id; set "
                "BEDROCK_EMBEDDING_MODEL_ID (e.g. amazon.titan-embed-text-v2:0)."
            )
        # Lazy boto3 import — keeps the optional-dep gate at the call site.
        import boto3  # type: ignore[import-not-found]

        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._model_id = model_id
        self._region = region
        self.dim = expected_dim
        # Cohere requires `input_type`; Titan ignores it. The embedder is
        # query-side, so default to the query-input type. The DAG-side
        # corpus-embedder counterpart should set this to "search_document".
        self._cohere_input_type = cohere_input_type

    def embed(self, text: str) -> list[float]:
        # OTel GenAI semconv — request side.
        set_gen_ai_request(
            system=SYSTEM_AWS_BEDROCK,
            operation=OP_EMBEDDING,
            model=self._model_id,
        )

        body = self._build_request_body(text)
        response = self._client.invoke_model(
            modelId=self._model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
        payload = json.loads(response["body"].read())

        vec = self._extract_embedding(payload)

        # Visible dim mismatch check — same defensive posture as the
        # SentenceTransformerEmbedder. If operator misconfigures, fail
        # visibly rather than silently scoring against the wrong space.
        if len(vec) != self.dim:
            raise RuntimeError(
                f"BedrockEmbedder: model {self._model_id} produced "
                f"dim={len(vec)} but the configured / pgvector column "
                f"expects dim={self.dim}. Adjust RAG_EMBEDDER_DIM or "
                f"pick a model whose output matches."
            )

        # OTel GenAI semconv — response side.
        usage = payload.get("inputTextTokenCount") or payload.get("usage", {}).get("input_tokens")
        set_gen_ai_response(
            model=self._model_id,
            input_tokens=usage,
        )
        return [float(x) for x in vec]

    def _build_request_body(self, text: str) -> dict:
        """Bedrock InvokeModel body shape differs per provider family."""
        if self._model_id.startswith("amazon.titan-embed"):
            return {"inputText": text, "dimensions": self.dim, "normalize": True}
        if self._model_id.startswith("cohere.embed"):
            return {
                "texts": [text],
                "input_type": self._cohere_input_type,
                "embedding_types": ["float"],
            }
        # Fall through with a generic shape — most Bedrock embedders use
        # `inputText`, but this branch surfaces unknown families clearly.
        LOGGER.warning(
            "BedrockEmbedder: unknown model family for %s; using generic "
            "{inputText: ...} request body", self._model_id,
        )
        return {"inputText": text}

    @staticmethod
    def _extract_embedding(payload: dict) -> list[float]:
        """Pull the float vector out of a Bedrock embedding response."""
        # Titan: top-level `embedding` field.
        if "embedding" in payload:
            return list(payload["embedding"])
        # Cohere: `embeddings.float[0]` (or `embeddings[0]` on older API).
        if "embeddings" in payload:
            embeddings = payload["embeddings"]
            if isinstance(embeddings, dict) and "float" in embeddings:
                return list(embeddings["float"][0])
            if isinstance(embeddings, list) and embeddings:
                return list(embeddings[0])
        raise RuntimeError(
            f"BedrockEmbedder: response payload had no recognizable embedding "
            f"field. Keys present: {sorted(payload.keys())}"
        )
