"""Seed the `Practice_Voice_Sample` corpus into `rag_vectors.child_chunk_embeddings`.

The practice voice corpus is the third grounding corpus called out in the README
(alongside regulator rules and clinical evidence). Each practice would have its
own voice corpus; this script seeds a small AHPRA-safe sample so the retrieval
flow has voice content to ground from on a fresh stack.

The script:
  * embeds each child chunk with `stub_embed` (the same function the live
    retrieval leg uses),
  * upserts via `ON CONFLICT (dataset_name, page_index, child_id) DO NOTHING`,
    so re-running is a no-op,
  * connects via env-driven DSN parts (RHC_PG_HOST/PORT/USER/PASSWORD/DB).

Sample voice content is intentionally:
  * plain, factual, AU English,
  * free of testimonials, before/after framing, efficacy claims, or
    unverifiable statistics,
  * obviously fictional (a generic "Sample Allied Health Practice").
"""

from __future__ import annotations

import hashlib
import math
import os
import sys

import psycopg2

DATASET_NAME = "Practice_Voice_Sample"
EMBED_DIM = 384
PARENT_SIZE_CHARS = 1200
CHILD_SIZE_CHARS = 220


SAMPLE_VOICE_PARAGRAPHS: list[str] = [
    # Each list element becomes one parent (page_index = position in this list).
    "About our approach. Our clinicians work within evidence-informed practice "
    "guidelines and current professional standards. Each consultation begins "
    "with a structured intake so we can understand your history and the "
    "concern that brought you in. We do not promise outcomes; instead we set "
    "realistic, individualised goals at the first session and review them at "
    "agreed intervals.",

    "Booking and the initial consultation. You can book a first appointment "
    "online or by phone. The initial consultation typically lasts 45 to 60 "
    "minutes. Please bring any referral letters, prior imaging reports, and a "
    "current medication list if you have them. Fees and rebate information "
    "are listed on our fees page; we do not advertise discounts on "
    "consultations.",

    "Privacy and records. Clinical records are kept in line with the Privacy "
    "Act 1988 and our profession's code of conduct. You may request a copy of "
    "your records, or a summary letter for another practitioner, at any time. "
    "Records are retained for the period required by regulation.",

    "Working with your GP. Where appropriate, we send a brief written summary "
    "to your nominated GP after the initial assessment and at significant "
    "points in care. We invite questions and welcome shared-care arrangements, "
    "particularly for chronic or complex presentations.",

    "Telehealth. Telehealth consultations are available for follow-up "
    "appointments where clinically appropriate. The first appointment is "
    "usually in person so we can complete a structured physical assessment. "
    "Technical requirements and a short setup guide are sent ahead of your "
    "first telehealth visit.",

    "Cancellation and rescheduling. We understand plans change. Please give "
    "us 24 hours' notice where possible, so the appointment can be offered to "
    "another patient. Our full cancellation policy is set out at the time of "
    "booking and on our website.",

    "Continuing education. Our practitioners participate in ongoing "
    "professional development and clinical supervision. New treatment "
    "approaches are introduced only after a review of the current evidence "
    "base, and after considering their suitability for the patients we see.",

    "Referring to us. We accept referrals from GPs, specialists, and "
    "self-referrals. Referrals can be sent by secure messaging, fax, or via "
    "our online referral form. We aim to acknowledge new referrals within two "
    "business days, and to offer an initial appointment within the timeframe "
    "noted on the referral.",

    # ── Appended in slice s2.x (richer voice corpus) ──────────────────────
    # Append-only — page_index for the original 8 paragraphs is preserved so
    # ON CONFLICT skips already-seeded rows on rerun.

    "Scope of practice. Our team provides services within the scope of "
    "practice each clinician is registered for. If your needs are outside "
    "our scope or warrant input from a different discipline, we will say so "
    "at the assessment stage and offer a referral to a suitable practitioner.",

    "Fees, rebates, and bulk billing. Standard consultation fees are listed "
    "on our fees page and are reviewed annually. Where a Chronic Disease "
    "Management plan or DVA approval applies, Medicare or DVA rebates may "
    "reduce the out-of-pocket cost. We do not bulk bill standard "
    "consultations; specific rebated programs are described individually on "
    "our fees page.",

    "Accessibility. Our consultation rooms are accessible by lift and have "
    "step-free entry from the street. We can arrange longer appointment "
    "slots for patients who need additional time, and we accept National "
    "Auslan Booking Service interpreters at no charge to the patient. "
    "Please let us know your access needs at booking so the appropriate "
    "room and time can be reserved.",

    "Multidisciplinary care. Many presentations benefit from input across "
    "more than one discipline. Where appropriate, we coordinate with the "
    "patient's GP, other allied-health practitioners, and treating "
    "specialists, with the patient's written consent. Care plans are "
    "shared via secure clinical messaging where the receiving practitioner "
    "supports it.",

    "Mental-health referral pathway. We are not a mental-health service. "
    "If a patient discloses concerns about mood, anxiety, or distress, we "
    "ask whether they have a current treating GP or psychologist, document "
    "the disclosure, and offer information about the patient's GP and "
    "Lifeline 13 11 14. Acute risk is escalated to the GP or emergency "
    "services as clinically indicated.",
]


def stub_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Mirror of `RAGMgmt-Service/common/embedding.py::stub_embed`. Kept inline so
    this script has zero local imports — it can run on any Python with psycopg2."""
    floats: list[float] = []
    seed = text.encode("utf-8")
    while len(floats) < dim:
        seed = hashlib.sha256(seed).digest()
        for i in range(8):
            chunk = seed[i * 4 : (i + 1) * 4]
            val = int.from_bytes(chunk, "big") / 0xFFFFFFFF - 0.5
            floats.append(val)
            if len(floats) == dim:
                break
    norm = math.sqrt(sum(f * f for f in floats))
    return [f / norm for f in floats] if norm > 0 else floats


def vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"


def split_into_children(parent_text: str, max_size: int) -> list[tuple[int, str]]:
    """Whitespace-preferred length-bounded splitter — mirrors chunking_service."""
    out: list[tuple[int, str]] = []
    pos = 0
    n = len(parent_text)
    while pos < n:
        end = pos + max_size
        if end >= n:
            tail = parent_text[pos:].strip()
            if tail:
                idx = parent_text.find(tail, pos)
                out.append((idx if idx != -1 else pos, tail))
            break
        cut = parent_text.rfind(" ", pos, end)
        if cut <= pos:
            cut = end
        piece = parent_text[pos:cut].strip()
        if piece:
            idx = parent_text.find(piece, pos)
            out.append((idx if idx != -1 else pos, piece))
        pos = cut + 1 if cut < n and parent_text[cut] == " " else cut
    return out


def main() -> int:
    dsn = (
        f"host={os.environ.get('RHC_PG_HOST', 'localhost')} "
        f"port={os.environ.get('RHC_PG_PORT', '5432')} "
        f"dbname={os.environ.get('RHC_PG_DB', 'rag_vectors')} "
        f"user={os.environ.get('RHC_PG_USER', 'rhc_admin')} "
        f"password={os.environ.get('RHC_PG_PASSWORD', 'rhc_admin_password')}"
    )

    rows_inserted = 0
    rows_skipped = 0

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            for page_index, parent_text in enumerate(SAMPLE_VOICE_PARAGRAPHS):
                # One parent per paragraph. Truncate if a paragraph somehow exceeds
                # the parent cap — sample data is well under, but stay defensive.
                parent_text = parent_text.strip()
                if len(parent_text) > PARENT_SIZE_CHARS:
                    parent_text = parent_text[:PARENT_SIZE_CHARS]
                parent_id = f"p{page_index:04d}"

                children = split_into_children(parent_text, CHILD_SIZE_CHARS)
                for c_idx, (offset, child_text) in enumerate(children):
                    child_id = f"{parent_id}_c{c_idx:04d}"
                    embedding = stub_embed(child_text)
                    vec_lit = vector_literal(embedding)

                    cur.execute(
                        """
                        INSERT INTO child_chunk_embeddings
                            (dataset_name, page_index, parent_id, child_id,
                             parent_text, child_text, char_offset_in_parent,
                             embedding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
                        ON CONFLICT (dataset_name, page_index, child_id)
                        DO NOTHING
                        """,
                        (
                            DATASET_NAME,
                            page_index,
                            parent_id,
                            child_id,
                            parent_text,
                            child_text,
                            offset,
                            vec_lit,
                        ),
                    )
                    if cur.rowcount > 0:
                        rows_inserted += 1
                    else:
                        rows_skipped += 1

        conn.commit()

    print(
        f"[seed_practice_voice] dataset={DATASET_NAME} "
        f"inserted={rows_inserted} already_present={rows_skipped}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
