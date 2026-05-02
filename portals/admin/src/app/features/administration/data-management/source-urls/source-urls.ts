import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';

import { DatamgmtApiService } from '../../../../core/api/datamgmt-api.service';
import { DatasetRow, SourceUrlRow } from '../../../../core/api/api.types';

interface NewUrlForm {
  url: string;
  label: string;
  position: number;
  is_active: boolean;
  notes: string;
}

@Component({
  selector: 'app-source-urls',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatSnackBarModule,
    MatTableModule,
  ],
  templateUrl: './source-urls.html',
  styleUrl: './source-urls.scss',
})
export class SourceUrlsComponent implements OnInit {
  private readonly api = inject(DatamgmtApiService);
  private readonly snack = inject(MatSnackBar);

  readonly datasets = signal<DatasetRow[]>([]);
  readonly selectedDataset = signal<string | null>(null);
  readonly urls = signal<SourceUrlRow[]>([]);
  readonly loading = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);

  readonly newUrl = signal<NewUrlForm>({
    url: '',
    label: '',
    position: 100,
    is_active: true,
    notes: '',
  });

  readonly columns = ['position', 'label', 'url', 'is_active', 'actions'];

  readonly fetchableUrls = computed(() => this.urls().filter((u) => u.is_active));

  ngOnInit(): void {
    this.refreshDatasets();
  }

  refreshDatasets(): void {
    this.loading.set(true);
    this.api.listDatasets().subscribe({
      next: (resp) => {
        const ds = resp.respCtxData.datasets;
        this.datasets.set(ds);
        if (!this.selectedDataset() && ds.length) {
          // Default to the regulator-guidelines dataset (the one with seeded URLs).
          const regulator = ds.find((d) => d.dataset_type === 'regulator_guidelines');
          this.selectedDataset.set(regulator?.dataset_name ?? ds[0].dataset_name);
        }
        if (this.selectedDataset()) {
          this.refreshUrls();
        } else {
          this.loading.set(false);
        }
      },
      error: (err) => this.fail('failed to load datasets', err),
    });
  }

  selectDataset(name: string): void {
    this.selectedDataset.set(name);
    this.urls.set([]);
    this.refreshUrls();
  }

  refreshUrls(): void {
    const name = this.selectedDataset();
    if (!name) return;
    this.loading.set(true);
    this.errorMessage.set(null);
    this.api.listSourceUrls(name).subscribe({
      next: (resp) => {
        this.urls.set(resp.respCtxData.source_urls);
        this.loading.set(false);
      },
      error: (err) => this.fail('failed to load source urls', err),
    });
  }

  toggleActive(row: SourceUrlRow, value: boolean): void {
    this.api.updateSourceUrl(row.id, { is_active: value }).subscribe({
      next: () => {
        this.urls.update((rows) =>
          rows.map((r) => (r.id === row.id ? { ...r, is_active: value } : r))
        );
        this.snack.open(
          `URL ${value ? 'enabled' : 'disabled'}: ${row.label ?? row.url}`,
          'OK',
          { duration: 2500 }
        );
      },
      error: (err) => this.fail('toggle failed', err),
    });
  }

  deleteUrl(row: SourceUrlRow): void {
    if (!confirm(`Delete this source URL?\n\n${row.url}`)) return;
    this.api.deleteSourceUrl(row.id).subscribe({
      next: () => {
        this.urls.update((rows) => rows.filter((r) => r.id !== row.id));
        this.snack.open('URL deleted', 'OK', { duration: 2500 });
      },
      error: (err) => this.fail('delete failed', err),
    });
  }

  setNewUrlField<K extends keyof NewUrlForm>(key: K, value: NewUrlForm[K]): void {
    this.newUrl.update((f) => ({ ...f, [key]: value }));
  }

  addUrl(): void {
    const name = this.selectedDataset();
    const form = this.newUrl();
    if (!name || !form.url.trim()) {
      this.snack.open('URL is required', 'OK', { duration: 2500 });
      return;
    }
    this.api
      .addSourceUrl(name, {
        url: form.url.trim(),
        label: form.label.trim() || null,
        position: form.position,
        is_active: form.is_active,
        notes: form.notes.trim() || null,
      })
      .subscribe({
        next: (resp) => {
          const inserted = resp.respCtxData.source_url;
          if (inserted) {
            this.urls.update((rows) =>
              [...rows, inserted].sort(
                (a, b) => a.position - b.position || a.id - b.id
              )
            );
            this.newUrl.set({
              url: '',
              label: '',
              position: 100,
              is_active: true,
              notes: '',
            });
            this.snack.open(`Added: ${inserted.url}`, 'OK', { duration: 2500 });
          }
        },
        error: (err) =>
          this.fail(
            err?.error?.detail ?? 'add failed (duplicate URL or bad scheme?)',
            err
          ),
      });
  }

  private fail(label: string, err: unknown): void {
    const msg =
      (err as { error?: { detail?: string }; message?: string })?.error?.detail ??
      (err as { message?: string })?.message ??
      'unknown error';
    this.errorMessage.set(`${label}: ${msg}`);
    this.snack.open(`${label}: ${msg}`, 'OK', { duration: 4000 });
    this.loading.set(false);
  }
}
