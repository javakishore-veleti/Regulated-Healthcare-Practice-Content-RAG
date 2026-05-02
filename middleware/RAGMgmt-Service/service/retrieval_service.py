from typing import Protocol

from common.dtos import HybridRetrieveReqDTO, HybridRetrieveRespDTO
from common.embedding import stub_embed, vector_literal
from common.return_codes import RC_OK
from common.tracing import traced
from dao.retrieval_dao import IRetrievalDao


class IRetrievalService(Protocol):
    async def hybrid_search(
        self, req: HybridRetrieveReqDTO, resp: HybridRetrieveRespDTO
    ) -> int: ...


class RetrievalService:
    """Hybrid search per the Project A pattern: BM25 (lexical) + pgvector (dense),
    fused with Reciprocal Rank Fusion. The cross-encoder rerank step is a stub for
    now (just truncates fused output to top_k); a real reranker plugs in here.
    """

    def __init__(self, retrieval_dao: IRetrievalDao) -> None:
        self._dao = retrieval_dao

    @traced("retrieval.hybrid_search")
    async def hybrid_search(
        self, req: HybridRetrieveReqDTO, resp: HybridRetrieveRespDTO
    ) -> int:
        query_vec = stub_embed(req.query)
        qvec_literal = vector_literal(query_vec)

        lexical_hits = await self._dao.lexical_search(
            query=req.query, top_k=req.top_k_per_leg, dataset_name=req.dataset_name
        )
        dense_hits = await self._dao.dense_search(
            query_vector_literal=qvec_literal,
            top_k=req.top_k_per_leg,
            dataset_name=req.dataset_name,
        )

        fused = _rrf_fuse(lexical_hits, dense_hits, k=req.rrf_k)
        # Rerank stub — real cross-encoder swaps in here.
        top = fused[: req.top_k]

        resp.respCtxData["hits"] = [
            {
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
            for h in top
        ]
        resp.respCtxData["legs"] = {
            "lexical": {"hit_count": len(lexical_hits)},
            "dense": {"hit_count": len(dense_hits)},
        }
        resp.respCtxData["fusion"] = {
            "method": "rrf",
            "rrf_k": req.rrf_k,
            "fused_candidate_count": len(fused),
            "returned": len(top),
        }
        resp.respCtxData["embedder"] = "stub_sha256_dim384"
        return RC_OK


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
