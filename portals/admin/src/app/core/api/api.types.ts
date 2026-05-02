export interface ApiResp<T> {
  respCtxData: T;
}

export interface EndpointRow {
  id: number;
  endpoint_name: string;
  category: string;
  location_type: string;
  location_config_json: Record<string, unknown>;
  is_active: boolean;
  created_dt: string | null;
  updated_dt: string | null;
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
  system_dataset_id: number;
  dataset_name: string;
  dataset_type: string;
  endpoint_id: number;
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
  error_text: string | null;
  configs_json: Record<string, unknown>;
  workflow_dag_id: string | null;
  workflow_run_id: string | null;
}

export type EndpointsResp = ApiResp<{ endpoints: EndpointRow[] }>;
export type DatasetsResp = ApiResp<{ datasets: DatasetRow[] }>;
export type IngestRunsResp = ApiResp<{
  ingest_runs: IngestRunRow[];
  count: number;
  limit: number;
  offset: number;
  filters: { dataset_name: string | null; endpoint_name: string | null };
}>;
export type StartIngestResp = ApiResp<Record<string, unknown>>;
