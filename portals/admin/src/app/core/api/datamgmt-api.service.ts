import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  DatasetsResp,
  EndpointsResp,
  IngestRunsResp,
  StartIngestResp,
} from './api.types';

@Injectable({ providedIn: 'root' })
export class DatamgmtApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api';

  listDatasets(): Observable<DatasetsResp> {
    return this.http.get<DatasetsResp>(`${this.base}/datasets`);
  }

  listEndpoints(): Observable<EndpointsResp> {
    return this.http.get<EndpointsResp>(`${this.base}/endpoints`);
  }

  listIngestRuns(filters: {
    dataset_name?: string;
    endpoint_name?: string;
    limit?: number;
  } = {}): Observable<IngestRunsResp> {
    let params = new HttpParams();
    if (filters.dataset_name) params = params.set('dataset_name', filters.dataset_name);
    if (filters.endpoint_name) params = params.set('endpoint_name', filters.endpoint_name);
    if (filters.limit !== undefined) params = params.set('limit', String(filters.limit));
    return this.http.get<IngestRunsResp>(`${this.base}/ingest/runs`, { params });
  }

  startIngest(payload: {
    dataset_name: string;
    endpoint_name: string;
    force_refresh?: boolean;
  }): Observable<StartIngestResp> {
    return this.http.post<StartIngestResp>(`${this.base}/ingest`, payload);
  }
}
