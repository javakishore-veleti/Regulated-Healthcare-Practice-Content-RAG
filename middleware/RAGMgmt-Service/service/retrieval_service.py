from typing import Protocol

from common.corpus_types import ALL_CORPUS_TYPES, datasets_for_corpus
from common.dtos import (
    HybridRetrieveReqDTO,
    HybridRetrieveRespDTO,
    ThreeCorporaRetrieveReqDTO,
    ThreeCorporaRetrieveRespDTO,
)
from common.embedding import IEmbedder, StubEmbedder
from common.return_codes import RC_OK
from common.tracing import traced
from dao.retrieval_dao import IRetrievalDao
from service.rerank.reranker import IdentityReranker, IReranker


class IRetrievalService(Protocol):
    async def hybrid_search(
        self, req: HybridRetrieveReqDTO, resp: HybridRetrieveRespDTO
    ) -> int: ...

    async def three_corpora_search(
        self,
        req: ThreeCorporaRetrieveReqDTO,
        resp: ThreeCorporaRetrieveRespDTO,
    ) -> int: ...


class RetrievalService:
    """Hybrid search per the Project A pattern: BM25 (lexical) + pgvector (dense),
    fused with Reciprocal Rank Fusion. The cross-encoder rerank step is a stub for
    now (just truncates fused output to top_k); a real reranker plugs in here.

    `three_corpora_search` runs the same pipeline once per corpus type so a
    downstream draft can pull a guaranteed mix of regulator + practice voice +
    clinical evidence rather than whichever corpus dominates a single ranking.
    """

    def __init__(
        self,
        retrieval_dao: IRetrievalDao,
        reranker: IReranker | None = None,
        embedder: IEmbedder | None = None,
    ) -> None:
        self._dao = retrieval_dao
        self._reranker: IReranker = reranker or IdentityReranker()
        self._embedder: IEmbedder = embedder or StubEmbedder()

    @traced("retrieval.hybrid_search")
    async def hybrid_search(
        self, req: HybridRetrieveReqDTO, resp: HybridRetrieveRespDTO
    ) -> int:
        ds_filter = [req.dataset_name] if req.dataset_name else None
        fused, lex_count, dense_count = await self._hybrid_for_datasets(
            query=req.query,
            top_k_per_leg=req.top_k_per_leg,
            rrf_k=req.rrf_k,
            dataset_names=ds_filter,
        )
        top = self._reranker.rerank(req.query, fused, req.top_k)

        resp.respCtxData["hits"] = [_hit_to_payload(h) for h in top]
        resp.respCtxData["legs"] = {
            "lexical": {"hit_count": lex_count},
            "dense":   {"hit_count": dense_count},
        }
        resp.respCtxData["fusion"] = {
            "method": "rrf",
            "rrf_k": req.rrf_k,
            "fused_candidate_count": len(fused),
            "returned": len(top),
        }
        resp.respCtxData["reranker"] = self._reranker.name
        resp.respCtxData["embedder"] = self._embedder.name
        return RC_OK

    @traced("retrieval.three_corpora_search")
    async def three_corpora_search(
        self,
        req: ThreeCorporaRetrieveReqDTO,
        resp: ThreeCorporaRetrieveRespDTO,
    ) -> int:
        per_corpus: list[dict] = []
        for corpus_type in ALL_CORPUS_TYPES:
            datasets = datasets_for_corpus(corpus_type)
            if not datasets:
                per_corpus.append(
                    {
                        "corpus_type": corpus_type,
                        "datasets": [],
                        "hits": [],
                        "legs": {"lexical": {"hit_count": 0}, "dense": {"hit_count": 0}},
                        "note": "no datasets registered for this corpus",
                    }
                )
                continue

            fused, lex_count, dense_count = await self._hybrid_for_datasets(
                query=req.query,
                top_k_per_leg=req.top_k_per_leg,
                rrf_k=req.rrf_k,
                dataset_names=datasets,
            )
            top = self._reranker.rerank(req.query, fused, req.top_k_per_corpus)
            per_corpus.append(
                {
                    "corpus_type": corpus_type,
                    "datasets": datasets,
                    "hits": [_hit_to_payload(h, corpus_type=corpus_type) for h in top],
                    "legs": {
                        "lexical": {"hit_count": lex_count},
                        "dense":   {"hit_count": dense_count},
                    },
                }
            )

        resp.respCtxData["per_corpus"] = per_corpus
        resp.respCtxData["query"] = req.query
        resp.respCtxData["embedder"] = self._embedder.name
        resp.respCtxData["reranker"] = self._reranker.name
        resp.respCtxData["corpus_count"] = len(per_corpus)
        resp.respCtxData["total_hits"] = sum(len(c["hits"]) for c in per_corpus)
        return RC_OK

    async def _hybrid_for_datasets(
        self,
        query: str,
        top_k_per_leg: int,
        rrf_k: int,
        dataset_names: list[str] | None,
    ) -> tuple[list[dict], int, int]:
        # Backend-agnostic: pass the embedder's plain list-of-floats output
        # to the DAO. Each DAO implementation formats it for its store
        # (pgvector text-form literal, OpenSearch k-NN array, etc.).
        query_vector = self._embedder.embed(query)
        lexical_hits = await self._dao.lexical_search(
            query=query, top_k=top_k_per_leg, dataset_names=dataset_names
        )
        dense_hits = await self._dao.dense_search(
            query_vector=query_vector,
            top_k=top_k_per_leg,
            dataset_names=dataset_names,
        )
        fused = _rrf_fuse(lexical_hits, dense_hits, k=rrf_k)
        return fused, len(lexical_hits), len(dense_hits)


def _hit_to_payload(h: dict, corpus_type: str | None = None) -> dict:
    payload = {
        "id": h["hit"]["id"],
        "child_id": h["hit"]["child_id"],
        "parent_id": h["hit"]["parent_id"],
        "dataset_name": h["hit"]["dataset_name"],
        "page_index": h["hit"]["page_index"],
        "char_offset_in_parent": h["hit"]["char_offset_in_parent"],
        "child_text": h["hit"]["child_text"],
        "parent_text": h["hit"]["parent_text"],
        "rrf_score": h["score"],
        "lexical_rank": h["lexical_rank"],
        "dense_rank": h["dense_rank"],
    }
    if "rerank_score" in h:
        payload["rerank_score"] = h["rerank_score"]
    if "rerank_overlap" in h:
        payload["rerank_overlap"] = h["rerank_overlap"]
    if corpus_type is not None:
        payload["corpus_type"] = corpus_type
    return payload


def _rrf_fuse(
    lexical_hits: list[dict], dense_hits: list[dict], k: int
) -> list[dict]:
    """Reciprocal Rank Fusion. For each candidate, score = sum_legs(1 / (k + rank))."""
    by_id: dict = {}
    for rank, hit in enumerate(lexical_hits, start=1):
        entry = by_id.setdefault(
            hit["id"],
            {"hit": hit, "score": 0.0, "lexical_rank": None, "dense_rank": None},
        )
        entry["score"] += 1.0 / (k + rank)
        entry["lexical_rank"] = rank
    for rank, hit in enumerate(dense_hits, start=1):
        entry = by_id.setdefault(
            hit["id"],
            {"hit": hit, "score": 0.0, "lexical_rank": None, "dense_rank": None},
        )
        entry["score"] += 1.0 / (k + rank)
        entry["dense_rank"] = rank
    return sorted(by_id.values(), key=lambda x: -x["score"])
