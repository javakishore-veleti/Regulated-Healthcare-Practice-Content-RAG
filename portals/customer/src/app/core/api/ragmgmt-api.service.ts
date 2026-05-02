import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiResp } from './api.types';

export interface GenerateDraftRequest {
  topic: string;
  dataset_name?: string | null;
  top_k?: number;
  voice_profile?: string | null;
}

export interface DraftCitation {
  marker: string;
  dataset_name: string | null;
  page_index: number | null;
  parent_id: string | null;
  child_id: string | null;
  char_offset_in_parent: number | null;
  snippet: string;
  rrf_score: number | null;
}

export interface GenerateDraftResponse {
  topic: string;
  voice_profile: string;
  generator: string;
  draft_markdown: string;
  citations: DraftCitation[];
  retrieval_meta: {
    legs: { lexical: { hit_count: number }; dense: { hit_count: number } };
    fusion: { method: string; rrf_k: number; fused_candidate_count: number; returned: number };
  };
  faithfulness: { status: string; reason?: string };
  guardrails: { status: string; reason?: string };
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
