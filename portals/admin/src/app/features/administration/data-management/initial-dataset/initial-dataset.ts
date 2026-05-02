import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTabsModule } from '@angular/material/tabs';

import { DatamgmtApiService } from '../../../../core/api/datamgmt-api.service';
import {
  DatasetRow,
  EndpointRow,
  IngestRunRow,
} from '../../../../core/api/api.types';

interface DatasetUiState {
  selectedEndpointName: string | null;
  forceRefresh: boolean;
  triggering: boolean;
}

@Component({
  selector: 'app-initial-dataset',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTableModule,
    MatTabsModule,
  ],
  templateUrl: './initial-dataset.html',
  styleUrl: './initial-dataset.scss',
})
export class InitialDatasetComponent implements OnInit {
  private readonly api = inject(DatamgmtApiService);
  private readonly snack = inject(MatSnackBar);

  readonly datasets = signal<DatasetRow[]>([]);
  readonly endpoints = signal<EndpointRow[]>([]);
  readonly runs = signal<IngestRunRow[]>([]);
  readonly loading = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly uiByDataset = signal<Record<string, DatasetUiState>>({});

  readonly initialDatasetEndpoints = computed(() =>
    this.endpoints().filter((e) => e.category === 'initial_dataset' && e.is_active)
  );

  readonly historyColumns = [
    'id',
    'ingest_status',
    'endpoint_name',
    'location_type',
    'ingest_start_dt',
    'ingest_end_dt',
    'force_refresh',
    'workflow',
  ];

  // TODO: drive from env / settings endpoint once we have one. Local-dev assumption.
  readonly airflowUiBase = 'http://localhost:8080';

  airflowRunUrl(row: IngestRunRow): string | null {
    if (!row.workflow_dag_id || !row.workflow_run_id) {
      return null;
    }
    const dagId = encodeURIComponent(row.workflow_dag_id);
    const runId = encodeURIComponent(row.workflow_run_id);
    return `${this.airflowUiBase}/dags/${dagId}/grid?dag_run_id=${runId}`;
  }

  ngOnInit(): void {
    this.refreshAll();
  }

  refreshAll(): void {
    this.loading.set(true);
    this.errorMessage.set(null);

    Promise.all([
      this.api.listDatasets().toPromise(),
      this.api.listEndpoints().toPromise(),
      this.api.listIngestRuns({ limit: 200 }).toPromise(),
    ])
      .then(([d, e, r]) => {
        const ds = d?.respCtxData.datasets ?? [];
        const eps = e?.respCtxData.endpoints ?? [];
        this.datasets.set(ds);
        this.endpoints.set(eps);
        this.runs.set(r?.respCtxData.ingest_runs ?? []);
        this.seedUiState(ds, eps);
      })
      .catch((err) => {
        const msg = err?.message ?? 'failed to load data';
        this.errorMessage.set(msg);
      })
      .finally(() => this.loading.set(false));
  }

  runsForDataset(datasetName: string): IngestRunRow[] {
    return this.runs().filter((r) => r.dataset_name === datasetName);
  }

  latestRunFor(datasetName: string): IngestRunRow | null {
    const list = this.runsForDataset(datasetName);
    return list.length ? list[0] : null;
  }

  uiFor(datasetName: string): DatasetUiState {
    return (
      this.uiByDataset()[datasetName] ?? {
        selectedEndpointName: null,
        forceRefresh: false,
        triggering: false,
      }
    );
  }

  setSelectedEndpoint(datasetName: string, endpointName: string | null): void {
    this.updateUi(datasetName, { selectedEndpointName: endpointName });
  }

  setForceRefresh(datasetName: string, value: boolean): void {
    this.updateUi(datasetName, { forceRefresh: value });
  }

  triggerIngest(datasetName: string): void {
    const ui = this.uiFor(datasetName);
    if (!ui.selectedEndpointName) {
      this.snack.open('Pick an endpoint first', 'OK', { duration: 3000 });
      return;
    }
    this.updateUi(datasetName, { triggering: true });
    this.api
      .startIngest({
        dataset_name: datasetName,
        endpoint_name: ui.selectedEndpointName,
        force_refresh: ui.forceRefresh,
      })
      .subscribe({
        next: (resp) => {
          const status = resp.respCtxData['ingest_status'] as string;
          this.snack.open(`Ingest ${status}`, 'OK', { duration: 3500 });
          this.updateUi(datasetName, { triggering: false });
          this.api.listIngestRuns({ limit: 200 }).subscribe((r) => {
            this.runs.set(r.respCtxData.ingest_runs);
          });
        },
        error: (err) => {
          this.snack.open(`Ingest failed: ${err?.error?.detail ?? err?.message ?? 'error'}`, 'OK', {
            duration: 5000,
          });
          this.updateUi(datasetName, { triggering: false });
        },
      });
  }

  statusClass(status: string): string {
    switch (status) {
      case 'success':
        return 'badge badge-success';
      case 'failure':
        return 'badge badge-failure';
      case 'skipped_cache_hit':
        return 'badge badge-skipped';
      case 'in_progress':
        return 'badge badge-progress';
      default:
        return 'badge badge-pending';
    }
  }

  private seedUiState(datasets: DatasetRow[], endpoints: EndpointRow[]): void {
    const defaultEndpoint = endpoints.find(
      (e) => e.category === 'initial_dataset' && e.is_active
    );
    const seed: Record<string, DatasetUiState> = { ...this.uiByDataset() };
    for (const d of datasets) {
      if (!seed[d.dataset_name]) {
        seed[d.dataset_name] = {
          selectedEndpointName: defaultEndpoint?.endpoint_name ?? null,
          forceRefresh: false,
          triggering: false,
        };
      }
    }
    this.uiByDataset.set(seed);
  }

  private updateUi(datasetName: string, patch: Partial<DatasetUiState>): void {
    const current = this.uiFor(datasetName);
    this.uiByDataset.set({
      ...this.uiByDataset(),
      [datasetName]: { ...current, ...patch },
    });
  }
}
