/**
 * Three-corpora taxonomy — mirrors RAGMgmt-Service/common/corpus_types.py.
 *
 * Kept frontend-local rather than fetched from the API so admin screens can
 * surface the corpus a dataset belongs to without an extra round-trip on every
 * page load. The customer portal has the same module under its own core/.
 *
 * When a new dataset_name is added by a migration on the backend, both this
 * module AND the Python equivalent need an entry. The CI test
 * `test_seeded_datasets_present` enforces alignment on the Python side.
 */

export type CorpusType = 'regulator' | 'clinical_evidence' | 'practice_voice';

export const CORPUS_LABEL: Record<CorpusType, string> = {
  regulator: 'Regulator',
  clinical_evidence: 'Clinical evidence',
  practice_voice: 'Practice voice',
};

const DATASET_NAME_TO_CORPUS_TYPE: Record<string, CorpusType> = {
  // Regulator advertising rules.
  Public_Regulator_Guidelines: 'regulator',
  // Open-access clinical evidence.
  NCBI_PubMed: 'clinical_evidence',
  NCBI_PubMed_Abstracts: 'clinical_evidence',
  PMC_Open_Access_Subset: 'clinical_evidence',
  PMC_Open_Access_FullText: 'clinical_evidence',
  Kaggle_Medical_Transcriptions: 'clinical_evidence',
  Common_Crawl_Allied_Health: 'clinical_evidence',
  // Practice voice / brand reference.
  Practice_Voice_Sample: 'practice_voice',
};

export function corpusForDataset(datasetName: string | null | undefined): CorpusType | null {
  if (!datasetName) return null;
  return DATASET_NAME_TO_CORPUS_TYPE[datasetName] ?? null;
}

/** CSS class for chips. Use with the per-corpus styles in styles.scss. */
export function corpusChipClass(corpus: CorpusType | null | undefined): string {
  if (!corpus) return 'corpus-chip corpus-unknown';
  return `corpus-chip corpus-${corpus.replace('_', '-')}`;
}

export function corpusLabel(corpus: CorpusType | null | undefined): string {
  if (!corpus) return 'unmapped';
  return CORPUS_LABEL[corpus];
}
