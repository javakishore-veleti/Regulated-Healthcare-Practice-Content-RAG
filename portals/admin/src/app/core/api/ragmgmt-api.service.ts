import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiResp } from './api.types';

export interface RagPatternRow {
  id: number;
  pattern_key: string;
  display_name: string;
  summary: string;
  excel_source: string | null;
  is_active: boolean;
  created_dt: string | null;
  updated_dt: string | null;
}

export type RagPatternsResp = ApiResp<{ patterns: RagPatternRow[] }>;

@Injectable({ providedIn: 'root' })
export class RagmgmtApiService {
  private readonly http = inject(HttpClient);
  // Path-based routing: in dev, proxy.conf.json sends `/api/patterns` to
  // RAGMgmt-Service:8002; in production, the ingress routes the same path
  // to the RAGMgmt-Service backend. The SPA never hardcodes a host.
  private readonly base = '/api';

  listPatterns(): Observable<RagPatternsResp> {
    return this.http.get<RagPatternsResp>(`${this.base}/patterns`);
  }
}
