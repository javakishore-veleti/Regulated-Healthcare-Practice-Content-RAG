"""Real embedder via sentence-transformers.

Default model is `sentence-transformers/all-MiniLM-L6-v2` — 384-dim output
that matches the stub embedder's dimension AND the existing pgvector column,
so flipping the backend doesn't require a schema migration. (Quality is the
swap reason, not dimension.)

Optional dep — install via `pip install '.[real-embedder]'`. The factory
falls back to StubEmbedder when sentence-transformers is missing OR the
model name is empty, so a fresh local checkout works without a 2 GB pull.

Lazy model load: the SentenceTransformer constructor downloads the model on
first instantiation, which can be ~80 MB plus a few seconds of HTTP. We
delay it until the first `embed()` call under a thread lock so service
startup is fast and a burst of concurrent requests doesn't trigger N
parallel downloads.
"""

from __future__ import annotations

import logging
import threading

from common.otel_genai import (
    OP_EMBEDDING,
    SYSTEM_HUGGINGFACE_ST,
    set_gen_ai_request,
    set_gen_ai_response,
)

LOGGER = logging.getLogger(__name__)


class SentenceTransformerEmbedder:
    name = "sentence_transformer"

    def __init__(self, model_name: str, expected_dim: int) -> None:
        if not model_name:
            raise ValueError(
                "SentenceTransformerEmbedder requires a model_name; set "
                "RAG_EMBEDDER_MODEL (default sentence-transformers/all-MiniLM-L6-v2)."
            )
        self._model_name = model_name
        self.dim = expected_dim
        self._model = None
        self._load_lock = threading.Lock()

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

            LOGGER.info(
                "SentenceTransformerEmbedder: loading model=%s (cold load — "
                "first embed call will pay the latency cost)",
                self._model_name,
            )
            self._model = SentenceTransformer(self._model_name)
            # Validate dimension matches the pgvector column. A mismatch means
            # operator picked a model whose output dim differs from the
            # existing index — fail visibly rather than silently producing
            # bad similarity scores.
            actual_dim = self._model.get_sentence_embedding_dimension()
            if actual_dim != self.dim:
                raise RuntimeError(
                    f"SentenceTransformerEmbedder: model {self._model_name} "
                    f"produces dim={actual_dim} but the configured / pgvector "
                    f"column expects dim={self.dim}. Pick a model whose "
                    f"output dim matches, or run a schema migration to change "
                    f"the column dim and re-embed the corpus."
                )
            return self._model

    def embed(self, text: str) -> list[float]:
        # OTel GenAI semconv — request side.
        set_gen_ai_request(
            system=SYSTEM_HUGGINGFACE_ST,
            operation=OP_EMBEDDING,
            model=self._model_name,
        )
        model = self._ensure_model()
        # encode() returns a numpy array; convert to plain floats for pgvector
        # text-form literal compatibility. normalize_embeddings=True puts the
        # output on the unit sphere — same property as StubEmbedder, so cosine
        # distance from pgvector behaves consistently across backends.
        vec = model.encode(text, normalize_embeddings=True, convert_to_numpy=True)
        out = [float(x) for x in vec.tolist()]
        # OTel GenAI semconv — response side. sentence-transformers doesn't
        # report token counts directly; we approximate via word count.
        set_gen_ai_response(
            model=self._model_name,
            input_tokens=len(text.split()),
        )
        return out
