import { Component } from '@angular/core';
import { MatCardModule } from '@angular/material/card';

@Component({
  selector: 'app-rag-management',
  standalone: true,
  imports: [MatCardModule],
  template: `
    <mat-card>
      <mat-card-title>RAG Management</mat-card-title>
      <mat-card-content>
        Pattern dashboards (Hybrid+Rerank, Parent-Child, Self-RAG, Guardrails) land in a
        later slice. This page is a placeholder so the top-nav section toggles correctly.
      </mat-card-content>
    </mat-card>
  `,
  styles: [`mat-card { max-width: 720px; }`],
})
export class RagManagementComponent {}
