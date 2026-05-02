"""Three-corpora taxonomy for the Project A grounding model.

The README commits to grounding every draft in three corpora:
  1. Regulator's published advertising rules
  2. The practice's own voice corpus (tone/brand reference)
  3. Open-access clinical evidence

This module is the source of truth for which seeded `dataset_name` belongs to
which corpus. It stays in sync by hand with:
  * DataMgmt-Service/migrations/rag_app/V004__seed_initial_endpoints_and_datasets.sql
    (the original 5 datasets), and
  * V009__seed_practice_voice_dataset.sql (Practice_Voice_Sample).

If/when a cross-DB lookup or a denormalized `dataset_type` column on
`child_chunk_embeddings` lands, this constant becomes a fallback rather than the
authoritative map. Until then, adding a new seeded dataset means updating both
the migration AND this module.
"""

from __future__ import annotations

REGULATOR = "regulator"
CLINICAL_EVIDENCE = "clinical_evidence"
PRACTICE_VOICE = "practice_voice"

ALL_CORPUS_TYPES: tuple[str, ...] = (REGULATOR, CLINICAL_EVIDENCE, PRACTICE_VOICE)


DATASET_NAME_TO_CORPUS_TYPE: dict[str, str] = {
    # Regulator advertising rules.
    "Public_Regulator_Guidelines":   REGULATOR,
    # Open-access clinical evidence — every dataset on the evidence side.
    "NCBI_PubMed":                   CLINICAL_EVIDENCE,
    "PMC_Open_Access_Subset":        CLINICAL_EVIDENCE,
    "Kaggle_Medical_Transcriptions": CLINICAL_EVIDENCE,
    "Common_Crawl_Allied_Health":    CLINICAL_EVIDENCE,
    # Practice voice / brand reference.
    "Practice_Voice_Sample":         PRACTICE_VOICE,
}


def datasets_for_corpus(corpus_type: str) -> list[str]:
    """Return the dataset_names that belong to a given corpus, in stable order."""
    return [d for d, c in DATASET_NAME_TO_CORPUS_TYPE.items() if c == corpus_type]


def corpus_for_dataset(dataset_name: str) -> str | None:
    return DATASET_NAME_TO_CORPUS_TYPE.get(dataset_name)
