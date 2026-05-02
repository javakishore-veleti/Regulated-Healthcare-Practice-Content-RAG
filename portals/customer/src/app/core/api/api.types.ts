// Subset of DataMgmt-Service response shapes the customer portal consumes.
// Customer portal is read-only; it only needs catalog + ingest-readiness data.

export interface ApiResp<T> {
  respCtxData: T;
}

export interface DatasetRow {
  id: number;
  dataset_name: string;
  dataset_type: string;
  created_dt: string | null;
  updated_dt: string | null;
}

export interface IngestRunRow {
  id: number;
  dataset_name: string;
  dataset_type: string;
  endpoint_name: string;
  location_type: string;
  ingest_status:
    | 'pending'
    | 'in_progress'
    | 'success'
    | 'failure'
    | 'skipped_cache_hit';
  ingest_start_dt: string | null;
  ingest_end_dt: string | null;
  last_ingest_dt: string | null;
}

export type DatasetsResp = ApiResp<{ datasets: DatasetRow[] }>;
export type IngestRunsResp = ApiResp<{ ingest_runs: IngestRunRow[]; count: number }>;
