"""Eval CLI — Excel Project A Task 14.

Usage:

    python -m eval.cli \\
        --triples eval/golden_triples.jsonl \\
        --cloud local \\
        --output eval_report.html

Pipes each triple through the live RAG pipeline (the same factories the
FastAPI service uses), scores the RAG triad (faithfulness, context
precision, answer relevance), and writes a self-contained HTML report.

Acceptance per the Excel:
  faithfulness ≥ 0.90, context-precision ≥ 0.75, answer-relevance ≥ 0.85
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Make the service package importable when launched as `python -m eval.cli`.
_SERVICE_DIR = Path(__file__).resolve().parent.parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

LOGGER = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m eval.cli",
        description=(
            "Run the RAG triad evaluation against a golden-triples JSONL file. "
            "Excel Project A Task 14."
        ),
    )
    p.add_argument(
        "--triples",
        type=Path,
        required=True,
        help="Path to JSONL with one triple per line.",
    )
    p.add_argument(
        "--cloud",
        choices=("aws", "local"),
        default="local",
        help="Cloud preset for backend selection (default: local).",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path("eval_report.html"),
        help="Where to write the HTML report (default: eval_report.html).",
    )
    p.add_argument(
        "--results-jsonl",
        type=Path,
        default=None,
        help="Optional: also write per-triple results as JSONL.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N triples (smoke testing).",
    )
    return p


async def _run_async(args) -> int:
    from rag_iface.cloud_presets import apply_preset
    apply_preset(args.cloud)

    from common.settings import get_settings
    from common.dtos import (
        GenerateGroundedDraftReqDTO,
        GenerateGroundedDraftRespDTO,
    )
    from common.db import build_pool, build_vectors_pool
    from common.embedding_factory import build_embedder
    from dao.retrieval_dao_factory import build_retrieval_dao
    from service.drafters.factory import build_drafter
    from service.faithfulness_service import FaithfulnessService
    from service.generation_service import GenerationService
    from service.guardrails.factory import build_guardrails_service
    from service.rerank.factory import build_reranker
    from service.retrieval_service import RetrievalService

    from eval.metrics import (
        compute_answer_relevance,
        compute_context_precision,
        compute_faithfulness,
        passes,
    )
    from eval.report import render_report
    from eval.triples import load_triples

    triples = load_triples(args.triples)
    if args.limit:
        triples = triples[: args.limit]
    LOGGER.info("Loaded %d triple(s) from %s", len(triples), args.triples)

    settings = get_settings()
    pool = await build_pool(settings)
    vectors_pool = await build_vectors_pool(settings)
    try:
        retrieval_service = RetrievalService(
            build_retrieval_dao(settings, vectors_pool),
            reranker=build_reranker(settings),
            embedder=build_embedder(settings),
        )
        guardrails_policy_path = (
            _SERVICE_DIR / "service" / "guardrails" / "policy.yaml"
        )
        gen = GenerationService(
            retrieval_service=retrieval_service,
            drafter=build_drafter(settings),
            guardrails_service=build_guardrails_service(settings, guardrails_policy_path),
            faithfulness_service=FaithfulnessService(),
            max_regenerate_attempts=settings.max_regenerate_attempts,
        )

        rows: list[dict] = []
        for t in triples:
            req = GenerateGroundedDraftReqDTO(
                topic=t.topic,
                voice_profile=t.voice_profile,
            )
            resp = GenerateGroundedDraftRespDTO()
            rc = await gen.generate_grounded_draft(req, resp)
            ctx = resp.respCtxData
            if rc != 0:
                LOGGER.warning("Triple %s: generate returned rc=%d", t.id, rc)

            faithfulness = compute_faithfulness(ctx)
            context_precision = compute_context_precision(ctx, t.expected_citations)
            answer_relevance = compute_answer_relevance(
                t.topic, ctx.get("draft_markdown") or ""
            )
            triad = {
                "faithfulness": faithfulness,
                "context_precision": context_precision,
                "answer_relevance": answer_relevance,
            }
            verdict = passes(triad)

            row = {
                "id": t.id,
                "topic": t.topic,
                "clinic_profile": t.clinic_profile,
                "expected_citations": t.expected_citations,
                "expected_corpora": t.expected_corpora,
                "corpora_present": (ctx.get("retrieval_meta") or {}).get(
                    "corpora_present"
                ),
                "draft_markdown": ctx.get("draft_markdown") or "",
                "actual_citations": [
                    {
                        "marker": c.get("marker"),
                        "dataset_name": c.get("dataset_name"),
                        "section_id": c.get("section_id"),
                        "corpus_type": c.get("corpus_type"),
                    }
                    for c in (ctx.get("citations") or [])
                ],
                **triad,
                **verdict,
            }
            rows.append(row)
            LOGGER.info(
                "%s — faith=%.3f ctx=%.3f rel=%.3f %s",
                t.id, faithfulness, context_precision, answer_relevance,
                "PASS" if verdict["all_pass"] else "FAIL",
            )

        report_html = render_report(cloud_preset=args.cloud, rows=rows)
        args.output.write_text(report_html, encoding="utf-8")
        LOGGER.info("HTML report → %s", args.output)

        if args.results_jsonl:
            with args.results_jsonl.open("w", encoding="utf-8") as fh:
                for r in rows:
                    fh.write(json.dumps(r, default=str) + "\n")
            LOGGER.info("JSONL results → %s", args.results_jsonl)

        # Exit code communicates aggregate verdict — useful for CI gating
        # an eval run as a release acceptance check.
        all_pass = all(r["all_pass"] for r in rows)
        return 0 if all_pass else 2
    finally:
        await pool.close()
        await vectors_pool.close()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    args = _build_parser().parse_args()
    return asyncio.run(_run_async(args))


if __name__ == "__main__":
    sys.exit(main())
