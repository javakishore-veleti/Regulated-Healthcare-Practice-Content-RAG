from typing import Protocol

from common.dtos import ChunkTextReqDTO, ChunkTextRespDTO
from common.return_codes import RC_OK
from common.tracing import traced


class IChunkingService(Protocol):
    async def parent_child_chunk(
        self, req: ChunkTextReqDTO, resp: ChunkTextRespDTO
    ) -> int: ...


class ChunkingService:
    """Implements the parent-child chunking pattern from the Project A Excel.

    Parents are paragraph-aligned (split on `\\n\\n`); paragraphs exceeding
    `parent_size_chars` are sub-split at whitespace boundaries to stay under the cap.
    Children are length-bounded slices of their parent at whitespace boundaries, so
    the parent's text can be reconstructed verbatim from the original source (the
    Excel's >99% reconstruction acceptance bar).

    Markdown-aware section attachment (Excel Task 4 — "Markdown with section IDs"):
    when the input contains markdown heading lines (`# `, `## `, `### `), each
    subsequent parent is tagged with the most-recent preceding heading as
    `parent_heading`. Headings stick across paragraphs until the next heading,
    so all paragraphs under "## Testimonials" share parent_heading="Testimonials".
    The Section ID is derived as a slug for cite-by-section drafting (Task 11).

    Pure-compute: no DAO involved at this stage — embeddings + persistence land in
    follow-up slices.
    """

    @traced("chunking.parent_child")
    async def parent_child_chunk(
        self, req: ChunkTextReqDTO, resp: ChunkTextRespDTO
    ) -> int:
        parents = _split_into_parents(req.text, req.parent_size_chars)

        parent_records: list[dict] = []
        child_records: list[dict] = []

        for p_idx, parent in enumerate(parents):
            parent_id = f"p{p_idx:04d}"
            parent_text = parent["text"]
            heading = parent["heading"]
            section_id = _heading_to_section_id(heading)
            parent_records.append(
                {
                    "id": parent_id,
                    "text": parent_text,
                    "char_length": len(parent_text),
                    "parent_heading": heading,
                    "section_id": section_id,
                }
            )
            for c_idx, (offset, child_text) in enumerate(
                _split_into_children(parent_text, req.child_size_chars)
            ):
                child_records.append(
                    {
                        "id": f"{parent_id}_c{c_idx:04d}",
                        "parent_id": parent_id,
                        "parent_heading": heading,
                        "section_id": section_id,
                        "text": child_text,
                        "char_offset_in_parent": offset,
                        "char_length": len(child_text),
                    }
                )

        ctx = resp.respCtxData
        ctx["parents"] = parent_records
        ctx["children"] = child_records
        ctx["parent_count"] = len(parent_records)
        ctx["child_count"] = len(child_records)
        ctx["parent_size_chars"] = req.parent_size_chars
        ctx["child_size_chars"] = req.child_size_chars
        # Surfaced for downstream visibility — operators inspecting chunked
        # output can confirm section attachment is working.
        ctx["sections_detected"] = sorted({
            p["section_id"] for p in parent_records if p["section_id"]
        })
        return RC_OK


def _split_at_whitespace(text: str, max_size: int) -> list[str]:
    """Greedy length-bounded split with whitespace-preferred break points."""
    chunks: list[str] = []
    pos = 0
    while pos < len(text):
        end = pos + max_size
        if end >= len(text):
            tail = text[pos:].strip()
            if tail:
                chunks.append(tail)
            break
        cut = text.rfind(" ", pos, end)
        if cut <= pos:
            cut = end  # hard cut when no whitespace exists in the window
        piece = text[pos:cut].strip()
        if piece:
            chunks.append(piece)
        pos = cut + 1 if cut < len(text) and text[cut] == " " else cut
    return chunks


_HEADING_RE = __import__("re").compile(r"^(#{1,6})\s+(.+?)\s*$")


def _split_into_parents(text: str, max_size: int) -> list[dict]:
    """Split into parent dicts: `{"text": <body>, "heading": <str|None>}`.

    Markdown headings (lines starting with `#`/`##`/`###`) become section
    anchors that attach to subsequent parents. Headings themselves are NOT
    emitted as parents — they're metadata. A parent without a preceding
    heading gets `heading=None`.

    Same size-cap semantics as before: paragraphs over `max_size` are
    sub-split at whitespace, with all sub-parents inheriting the heading.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    parents: list[dict] = []
    pending_heading: str | None = None
    for p in paragraphs:
        m = _HEADING_RE.match(p)
        if m:
            # Whole paragraph is a heading line — remember and skip emission.
            pending_heading = m.group(2).strip()
            continue
        if len(p) <= max_size:
            parents.append({"text": p, "heading": pending_heading})
        else:
            for sub in _split_at_whitespace(p, max_size):
                parents.append({"text": sub, "heading": pending_heading})
    return parents


def _heading_to_section_id(heading: str | None) -> str | None:
    """Slugify a heading into a citation-friendly anchor:

        "Section 133 of the National Law" → "Section_133_of_the_National_Law"

    Used for `[Public_Regulator_Guidelines#Section_133_of_the_National_Law]`-
    style citations in the drafter prompt. Returns None when no heading.
    """
    if not heading:
        return None
    slug = "".join(c if c.isalnum() else "_" for c in heading).strip("_")
    return slug[:120] or None


def _split_into_children(text: str, max_size: int) -> list[tuple[int, str]]:
    """Return list of (char_offset_in_parent, child_text) so callers can map a child
    back to its position in the parent text."""
    pieces = _split_at_whitespace(text, max_size)
    out: list[tuple[int, str]] = []
    cursor = 0
    for piece in pieces:
        idx = text.find(piece, cursor)
        if idx == -1:
            idx = cursor
        out.append((idx, piece))
        cursor = idx + len(piece)
    return out
