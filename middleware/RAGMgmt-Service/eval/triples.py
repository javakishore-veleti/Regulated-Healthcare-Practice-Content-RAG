"""Golden triples loader — Excel Task 14 input shape.

JSONL file, one triple per line:

    {
      "id": "...",                           // optional, defaults to line number
      "clinic_profile": "Generic AU physio practice",
      "topic": "What AHPRA says about testimonials in advertising",
      "expected_citations": [                // anchors retrieval should surface
        "Public_Regulator_Guidelines#Testimonials"
      ],
      "expected_corpora": ["regulator"],     // optional, validates corpus mix
      "voice_profile": "professional, plain English"  // optional
    }

The `expected_citations` strings are the Dataset#Section_id form the
chunker emits when section IDs are populated. For pre-section-ID corpora,
operators can use just `Dataset` (matches by dataset_name).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GoldenTriple:
    id: str
    clinic_profile: str
    topic: str
    expected_citations: list[str]
    expected_corpora: list[str] = field(default_factory=list)
    voice_profile: str | None = None


def load_triples(path: Path) -> list[GoldenTriple]:
    triples: list[GoldenTriple] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}:{line_no} — invalid JSON: {exc}"
                ) from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_no} — line is not a JSON object")
            triples.append(
                GoldenTriple(
                    id=str(obj.get("id") or f"{path.stem}:{line_no}"),
                    clinic_profile=str(obj.get("clinic_profile") or ""),
                    topic=str(obj.get("topic") or ""),
                    expected_citations=list(obj.get("expected_citations") or []),
                    expected_corpora=list(obj.get("expected_corpora") or []),
                    voice_profile=obj.get("voice_profile"),
                )
            )
    if not triples:
        raise ValueError(f"{path} contains no golden triples")
    return triples
