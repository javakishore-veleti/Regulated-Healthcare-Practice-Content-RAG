"""rag_iface CLI — Excel Project A Task 13: `--cloud aws|local` swap.

Thin wrapper around the factories so an operator can:

    python -m rag_iface.cli describe --cloud aws
    python -m rag_iface.cli generate --cloud aws --topic "AHPRA telehealth advertising"

`generate` runs the full retrieve → rerank → draft → faithfulness →
guardrails pipeline against the configured backends and prints the draft +
citations + verdicts. Useful for smoke testing a freshly provisioned AWS
deploy without the FastAPI server up.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Make the service package importable when the CLI is launched as a script
# (e.g. `python middleware/RAGMgmt-Service/rag_iface/cli.py`).
_SERVICE_DIR = Path(__file__).resolve().parent.parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

LOGGER = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m rag_iface.cli",
        description=(
            "Provider-agnostic RAG smoke CLI — picks the backend stack via "
            "--cloud and runs retrieval + generation locally without "
            "starting the FastAPI server. Excel Project A Task 13."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    desc = sub.add_parser("describe", help="Print a cloud preset's env-var overrides.")
    desc.add_argument("--cloud", required=True, choices=("aws", "local"))

    gen = sub.add_parser(
        "generate",
        help="Run a single grounded-draft generation against the selected cloud preset.",
    )
    gen.add_argument("--cloud", required=True, choices=("aws", "local"))
    gen.add_argument("--topic", required=True)
    gen.add_argument("--top-k-per-corpus", type=int, default=3)
    gen.add_argument("--voice-profile", default=None)
    gen.add_argument(
        "--retrieval-mode",
        default="three_corpora",
        choices=("three_corpora", "single_corpus"),
    )
    gen.add_argument(
        "--output",
        default=None,
        help="Write respCtxData JSON to this file; default: stdout pretty-print.",
    )
    return p


def _cmd_describe(args) -> int:
    from rag_iface.cloud_presets import describe_preset
    preset = describe_preset(args.cloud)
    print(json.dumps(preset, indent=2))
    return 0


async def _cmd_generate_async(args) -> int:
    from rag_iface.cloud_presets import apply_preset
    apply_preset(args.cloud)

    # Settings is read AFTER preset application so the factories see the
    # preset's vars unless the operator already exported them.
    from common.settings import get_settings
    from common.dtos import (
        GenerateGroundedDraftReqDTO,
        GenerateGroundedDraftRespDTO,
    )
    from common.db import build_pool, build_vectors_pool
    from common.embedding_factory import build_embedder
    from dao.patterns_dao import PostgresRagPatternsDao  # noqa: F401 — keeps imports honest
    from dao.retrieval_dao_factory import build_retrieval_dao
    from service.chunking_service import ChunkingService  # noqa: F401
    from service.drafters.factory import build_drafter
    from service.faithfulness_service import FaithfulnessService
    from service.generation_service import GenerationService
    from service.guardrails.factory import build_guardrails_service
    from service.rerank.factory import build_reranker
    from service.retrieval_service import RetrievalService

    settings = get_settings()
    pool = await build_pool(settings)
    vectors_pool = await build_vectors_pool(settings)
    try:
        retrieval_dao = build_retrieval_dao(settings, vectors_pool)
        retrieval_service = RetrievalService(
            retrieval_dao,
            reranker=build_reranker(settings),
            embedder=build_embedder(settings),
        )
        guardrails_policy_path = Path(__file__).resolve().parent.parent / "service" / "guardrails" / "policy.yaml"
        guardrails_service = build_guardrails_service(settings, guardrails_policy_path)
        gen = GenerationService(
            retrieval_service=retrieval_service,
            drafter=build_drafter(settings),
            guardrails_service=guardrails_service,
            faithfulness_service=FaithfulnessService(),
            max_regenerate_attempts=settings.max_regenerate_attempts,
        )

        req = GenerateGroundedDraftReqDTO(
            topic=args.topic,
            retrieval_mode=args.retrieval_mode,
            top_k_per_corpus=args.top_k_per_corpus,
            voice_profile=args.voice_profile,
        )
        resp = GenerateGroundedDraftRespDTO()
        rc = await gen.generate_grounded_draft(req, resp)
        if rc != 0:
            LOGGER.error("generate_grounded_draft returned rc=%d", rc)
            return rc

        payload = json.dumps(resp.respCtxData, indent=2, default=str)
        if args.output:
            Path(args.output).write_text(payload + "\n")
            print(f"Wrote {args.output}")
        else:
            print(payload)
        return 0
    finally:
        await pool.close()
        await vectors_pool.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    args = _build_parser().parse_args()
    if args.cmd == "describe":
        return _cmd_describe(args)
    if args.cmd == "generate":
        return asyncio.run(_cmd_generate_async(args))
    return 1


if __name__ == "__main__":
    sys.exit(main())
