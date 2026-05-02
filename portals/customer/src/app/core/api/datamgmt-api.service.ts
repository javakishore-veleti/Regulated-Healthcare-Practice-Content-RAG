import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { DatasetsResp, IngestRunsResp } from './api.types';

@Injectable({ providedIn: 'root' })
export class DatamgmtApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api';

  listDatasets(): Observable<DatasetsResp> {
    return this.http.get<DatasetsResp>(`${this.base}/datasets`);
  }

  listIngestRuns(filters: { limit?: number } = {}): Observable<IngestRunsResp> {
    let params = new HttpParams();
    if (filters.limit !== undefined) params = params.set('limit', String(filters.limit));
    return this.http.get<IngestRunsResp>(`${this.base}/ingest/runs`, { params });
  }
}
