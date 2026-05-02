import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { DatamgmtApiService } from '../../../core/api/datamgmt-api.service';
import { DatasetRow, IngestRunRow } from '../../../core/api/api.types';

interface DatasetCard {
  dataset: DatasetRow;
  latestSuccess: IngestRunRow | null;
  latestAny: IngestRunRow | null;
  totalRuns: number;
}

@Component({
  selector: 'app-dataset-catalog',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatIconModule, MatProgressSpinnerModule],
  templateUrl: './dataset-catalog.html',
  styleUrl: './dataset-catalog.scss',
})
export class DatasetCatalogComponent implements OnInit {
  private readonly api = inject(DatamgmtApiService);

  readonly datasets = signal<DatasetRow[]>([]);
  readonly runs = signal<IngestRunRow[]>([]);
  readonly loading = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);

  readonly cards = computed<DatasetCard[]>(() => {
    const allRuns = this.runs();
    return this.datasets().map((d) => {
      const forDataset = allRuns.filter((r) => r.dataset_name === d.dataset_name);
      const latestSuccess = forDataset.find((r) => r.ingest_status === 'success') ?? null;
      const latestAny = forDataset[0] ?? null;
      return {
        dataset: d,
        latestSuccess,
        latestAny,
        totalRuns: forDataset.length,
      };
    });
  });

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading.set(true);
    this.errorMessage.set(null);
    Promise.all([
      this.api.listDatasets().toPromise(),
      this.api.listIngestRuns({ limit: 200 }).toPromise(),
    ])
      .then(([d, r]) => {
        this.datasets.set(d?.respCtxData.datasets ?? []);
        this.runs.set(r?.respCtxData.ingest_runs ?? []);
      })
      .catch((err) => this.errorMessage.set(err?.message ?? 'failed to load catalog'))
      .finally(() => this.loading.set(false));
  }

  readinessLabel(card: DatasetCard): string {
    if (card.latestSuccess) return 'Ready';
    if (card.latestAny?.ingest_status === 'in_progress') return 'In progress';
    if (card.latestAny?.ingest_status === 'failure') return 'Last attempt failed';
    return 'Not ingested yet';
  }

  readinessClass(card: DatasetCard): string {
    if (card.latestSuccess) return 'badge badge-success';
    if (card.latestAny?.ingest_status === 'in_progress') return 'badge badge-progress';
    if (card.latestAny?.ingest_status === 'failure') return 'badge badge-failure';
    return 'badge badge-pending';
  }
}
