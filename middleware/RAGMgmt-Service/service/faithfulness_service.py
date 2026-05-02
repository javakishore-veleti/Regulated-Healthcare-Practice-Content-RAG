"""Self-RAG faithfulness scorer per the Project A pattern.

Today's implementation is a deterministic *stub*: token-overlap between each draft
sentence and the union of citation snippets, thresholded per-sentence and aggregated.
The architecture — sentence-by-sentence scoring, threshold + regenerate decision —
is the durable shape; swapping in a Bedrock Claude Haiku critic (per the Excel
architecture) replaces `_score_against_evidence` only. The Excel acceptance bar is
≥0.9 on a holdout set; the stub's lenient defaults (per-sentence 0.25, overall 0.7)
make sense for the verbatim-quoting stub composer and tighten as the generator gets
smarter.
"""

from __future__ import annotations

import re
from typing import Protocol

from common.dtos import (
    CheckFaithfulnessReqDTO,
    CheckFaithfulnessRespDTO,
    CitationSnippet,
)
from common.return_codes import RC_OK
from common.tracing import traced

# Lines that are draft *structure*, not claims about the topic — skip during scoring.
_SKIPPABLE_LINE_PREFIXES = ("#", "_")
_SKIPPABLE_LINE_EXACT = {"---"}
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _split_into_claims(text: str) -> list[str]:
    """Strip structural markdown lines, then split into sentences. Returns
    non-empty claim strings."""
    kept: list[str] = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line in _SKIPPABLE_LINE_EXACT:
            continue
        if any(line.startswith(p) for p in _SKIPPABLE_LINE_PREFIXES):
            continue
        if line.startswith(">"):
            line = line.lstrip("> ").strip()
        kept.append(line)

    sentences: list[str] = []
    for chunk in kept:
        for s in _SENTENCE_SPLIT_RE.split(chunk):
            s = s.strip()
            if s:
                sentences.append(s)
    return sentences


class IFaithfulnessService(Protocol):
    async def check_text(
        self, req: CheckFaithfulnessReqDTO, resp: CheckFaithfulnessRespDTO
    ) -> int: ...


class FaithfulnessService:
    @traced("faithfulness.check_text")
    async def check_text(
        self, req: CheckFaithfulnessReqDTO, resp: CheckFaithfulnessRespDTO
    ) -> int:
        evidence_tokens: set[str] = set()
        for c in req.citations:
            evidence_tokens.update(_tokenize(c.snippet))

        sentences = _split_into_claims(req.text)
        per_sentence: list[dict] = []
        supported_count = 0
        evidence_free_count = 0

        for sent in sentences:
            tokens = _tokenize(sent)
            entry = {
                "sentence": sent,
                "token_count": len(tokens),
                "overlap_ratio": 0.0,
                "supported": False,
                "reason": None,
            }
            if not req.citations:
                entry["reason"] = "no_citations_provided"
                evidence_free_count += 1
            elif len(tokens) < 4:
                entry["supported"] = True
                entry["reason"] = "too_short_to_check"
                supported_count += 1
            else:
                token_set = set(tokens)
                common = token_set & evidence_tokens
                overlap = len(common) / max(len(token_set), 1)
                entry["overlap_ratio"] = round(overlap, 4)
                entry["supported"] = overlap >= req.per_sentence_threshold
                if entry["supported"]:
                    supported_count += 1
            per_sentence.append(entry)

        total = len(per_sentence)
        score = (supported_count / total) if total > 0 else 1.0
        passed = score >= req.overall_threshold

        ctx = resp.respCtxData
        ctx["scorer"] = "stub_token_overlap_v1"
        ctx["per_sentence_threshold"] = req.per_sentence_threshold
        ctx["overall_threshold"] = req.overall_threshold
        ctx["sentence_count"] = total
        ctx["supported_count"] = supported_count
        ctx["evidence_free_count"] = evidence_free_count
        ctx["score"] = round(score, 4)
        ctx["passed"] = passed
        ctx["regenerate_recommended"] = not passed
        ctx["per_sentence"] = per_sentence
        ctx["citation_count"] = len(req.citations)
        return RC_OK
