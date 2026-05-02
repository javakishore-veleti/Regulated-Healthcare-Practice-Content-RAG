import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import {
  RagPatternRow,
  RagmgmtApiService,
} from '../../../core/api/ragmgmt-api.service';

@Component({
  selector: 'app-rag-patterns-list',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './patterns-list.html',
  styleUrl: './patterns-list.scss',
})
export class RagPatternsListComponent implements OnInit {
  private readonly api = inject(RagmgmtApiService);

  readonly patterns = signal<RagPatternRow[]>([]);
  readonly loading = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading.set(true);
    this.errorMessage.set(null);
    this.api.listPatterns().subscribe({
      next: (resp) => {
        this.patterns.set(resp.respCtxData.patterns);
        this.loading.set(false);
      },
      error: (err) => {
        this.errorMessage.set(
          err?.message ?? 'failed to load patterns from RAGMgmt-Service'
        );
        this.loading.set(false);
      },
    });
  }
}
