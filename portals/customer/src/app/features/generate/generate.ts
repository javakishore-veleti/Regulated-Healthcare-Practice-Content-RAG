import { Component } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-generate',
  standalone: true,
  imports: [MatCardModule, MatIconModule],
  template: `
    <mat-card>
      <mat-card-header>
        <mat-card-title>
          <mat-icon class="title-icon">auto_awesome</mat-icon>
          Generate Content
        </mat-card-title>
      </mat-card-header>
      <mat-card-content>
        <p>
          The compliance-grounded content generation surface is the next major slice.
          When live, this page will let practice owners pick a clinic profile and topic,
          then produce drafts grounded in the regulator rules + practice voice + clinical
          evidence corpora — every claim cited, every banned phrase blocked.
        </p>
        <p class="muted">Until then, browse the <a routerLink="/catalog">Catalog</a> to see what data the system has indexed.</p>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    mat-card { max-width: 720px; background: var(--mat-sys-surface-container-lowest); border: 1px solid var(--mat-sys-outline-variant); border-radius: 10px; }
    mat-card-title { display: flex; align-items: center; gap: 0.5rem; font-weight: 500; }
    .title-icon { color: var(--rhc-top-nav-active); }
    .muted { color: var(--mat-sys-on-surface-variant); }
  `],
})
export class GenerateComponent {}
