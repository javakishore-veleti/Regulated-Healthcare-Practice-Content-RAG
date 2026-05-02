import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiResp } from './api.types';

export type RetrievalMode = 'three_corpora' | 'single_corpus';
export type CorpusType = 'regulator' | 'clinical_evidence' | 'practice_voice';

export interface GenerateDraftRequest {
  topic: string;
  retrieval_mode?: RetrievalMode;
  // single_corpus knobs (used only when retrieval_mode === 'single_corpus'):
  dataset_name?: string | null;
  top_k?: number;
  // three_corpora knob (used only when retrieval_mode === 'three_corpora'):
  top_k_per_corpus?: number;
  voice_profile?: string | null;
}

export interface DraftCitation {
  marker: string;
  dataset_name: string | null;
  // corpus_type is populated when retrieval_mode === 'three_corpora'; null in
  // single_corpus mode (the legacy path).
  corpus_type: CorpusType | null;
  page_index: number | null;
  parent_id: string | null;
  child_id: string | null;
  char_offset_in_parent: number | null;
  snippet: string;
  rrf_score: number | null;
  rerank_score: number | null;
}

export type GuardrailSeverity = 'critical' | 'high' | 'medium' | 'low';

export interface GuardrailViolation {
  rule_id: string;
  category: string;
  severity: GuardrailSeverity;
  rationale: string;
  pattern: string;
  matched_text: string;
  char_start: number;
  char_end: number;
}

export interface GuardrailStatus {
  status: 'ok' | 'skipped' | 'error';
  policy_id?: string;
  rule_count?: number;
  passed?: boolean;
  violation_count?: number;
  max_severity?: GuardrailSeverity | null;
  violations?: GuardrailViolation[];
  reason?: string;
}

export interface FaithfulnessSentence {
  sentence: string;
  token_count: number;
  overlap_ratio: number;
  supported: boolean;
  reason?: string | null;
}

export interface FaithfulnessStatus {
  status: 'ok' | 'skipped' | 'error';
  scorer?: string;
  score?: number;
  passed?: boolean;
  overall_threshold?: number;
  per_sentence_threshold?: number;
  sentence_count?: number;
  supported_count?: number;
  evidence_free_count?: number;
  regenerate_recommended?: boolean;
  per_sentence_preview?: FaithfulnessSentence[];
  reason?: string;
}

export interface RetrievalMeta {
  // Always populated (both modes):
  mode: RetrievalMode;
  reranker?: string | null;
  embedder?: string | null;
  total_hits?: number;

  // Three-corpora mode adds these:
  corpora_present?: CorpusType[];
  corpora_missing?: CorpusType[];
  per_corpus_hit_counts?: Partial<Record<CorpusType, number>>;

  // Single-corpus mode adds these:
  dataset_name?: string | null;
  legs?: { lexical: { hit_count: number }; dense: { hit_count: number } };
  fusion?: { method: string; rrf_k: number; fused_candidate_count: number; returned: number };
}

export interface GenerateDraftResponse {
  topic: string;
  voice_profile: string;
  generator: string;
  retrieval_mode: RetrievalMode;
  draft_markdown: string;
  citations: DraftCitation[];
  retrieval_meta: RetrievalMeta;
  faithfulness: FaithfulnessStatus;
  guardrails: GuardrailStatus;
}

@Injectable({ providedIn: 'root' })
export class RagmgmtApiService {
  private readonly http = inject(HttpClient);
  // Path-based routing: in dev, proxy.conf.json sends `/api/{generate,retrieve,...}` to
  // RAGMgmt-Service:8002; in production, the ingress routes the same paths to the
  // RAGMgmt-Service backend. The SPA never hardcodes a host.
  private readonly base = '/api';

  generateDraft(req: GenerateDraftRequest): Observable<ApiResp<GenerateDraftResponse>> {
    return this.http.post<ApiResp<GenerateDraftResponse>>(`${this.base}/generate`, req);
  }
}
