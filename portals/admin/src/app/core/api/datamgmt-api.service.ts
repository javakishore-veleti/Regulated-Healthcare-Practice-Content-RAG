import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  DatasetsResp,
  EndpointsResp,
  IngestRunsResp,
  SourceUrlMutationResp,
  SourceUrlsResp,
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

  listSourceUrls(
    datasetName: string,
    onlyActive = false
  ): Observable<SourceUrlsResp> {
    let params = new HttpParams();
    if (onlyActive) params = params.set('only_active', 'true');
    return this.http.get<SourceUrlsResp>(
      `${this.base}/datasets/${encodeURIComponent(datasetName)}/source-urls`,
      { params }
    );
  }

  addSourceUrl(
    datasetName: string,
    body: {
      url: string;
      label?: string | null;
      is_active?: boolean;
      position?: number;
      notes?: string | null;
    }
  ): Observable<SourceUrlMutationResp> {
    return this.http.post<SourceUrlMutationResp>(
      `${this.base}/datasets/${encodeURIComponent(datasetName)}/source-urls`,
      body
    );
  }

  updateSourceUrl(
    id: number,
    body: {
      is_active?: boolean | null;
      position?: number | null;
      label?: string | null;
      notes?: string | null;
    }
  ): Observable<SourceUrlMutationResp> {
    return this.http.patch<SourceUrlMutationResp>(
      `${this.base}/source-urls/${id}`,
      body
    );
  }

  deleteSourceUrl(id: number): Observable<SourceUrlMutationResp> {
    return this.http.delete<SourceUrlMutationResp>(
      `${this.base}/source-urls/${id}`
    );
  }
}
