import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import {
  DraftCitation,
  GenerateDraftResponse,
  GuardrailStatus,
  GuardrailViolation,
  RagmgmtApiService,
} from '../../core/api/ragmgmt-api.service';

interface DraftBlock {
  type: 'h1' | 'h2' | 'h3' | 'blockquote' | 'hr' | 'p' | 'meta';
  text: string;
}

@Component({
  selector: 'app-generate',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './generate.html',
  styleUrl: './generate.scss',
})
export class GenerateComponent {
  private readonly api = inject(RagmgmtApiService);

  readonly topic = signal<string>('How AHPRA handles complaints about practitioner advertising');
  readonly voiceProfile = signal<string>('professional, plain English');
  readonly topK = signal<number>(5);

  readonly loading = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly draft = signal<GenerateDraftResponse | null>(null);

  readonly draftBlocks = computed<DraftBlock[]>(() => {
    const md = this.draft()?.draft_markdown ?? '';
    return parseDraftMarkdown(md);
  });

  readonly citations = computed<DraftCitation[]>(() => this.draft()?.citations ?? []);

  readonly guardrails = computed<GuardrailStatus | null>(
    () => this.draft()?.guardrails ?? null
  );

  readonly guardrailViolations = computed<GuardrailViolation[]>(
    () => this.guardrails()?.violations ?? []
  );

  guardrailHeadlineClass(): string {
    const g = this.guardrails();
    if (!g) return 'pill pill-pending';
    if (g.status === 'skipped') return 'pill pill-pending';
    if (g.status === 'error') return 'pill pill-failure';
    if (g.passed) return 'pill pill-success';
    const sev = g.max_severity;
    if (sev === 'critical' || sev === 'high') return 'pill pill-failure';
    if (sev === 'medium') return 'pill pill-skipped';
    return 'pill pill-pending';
  }

  guardrailHeadlineLabel(): string {
    const g = this.guardrails();
    if (!g) return 'no draft yet';
    if (g.status === 'skipped') return 'guardrails skipped';
    if (g.status === 'error') return 'guardrails error';
    if (g.passed) return `passed · ${g.rule_count ?? 0} rules checked`;
    return `${g.violation_count ?? 0} violations · max ${g.max_severity}`;
  }

  severityClass(sev: string): string {
    if (sev === 'critical' || sev === 'high') return 'sev sev-critical';
    if (sev === 'medium') return 'sev sev-medium';
    return 'sev sev-low';
  }

  setTopic(v: string): void {
    this.topic.set(v);
  }
  setVoice(v: string): void {
    this.voiceProfile.set(v);
  }
  setTopK(v: number): void {
    this.topK.set(Math.max(1, Math.min(10, Math.floor(v) || 5)));
  }

  generate(): void {
    const t = this.topic().trim();
    if (!t) {
      this.errorMessage.set('Topic is required.');
      return;
    }
    this.loading.set(true);
    this.errorMessage.set(null);
    this.api
      .generateDraft({
        topic: t,
        top_k: this.topK(),
        voice_profile: this.voiceProfile().trim() || null,
      })
      .subscribe({
        next: (resp) => {
          this.draft.set(resp.respCtxData);
          this.loading.set(false);
        },
        error: (err) => {
          this.errorMessage.set(
            err?.error?.detail ?? err?.message ?? 'failed to generate draft'
          );
          this.loading.set(false);
        },
      });
  }
}

function parseDraftMarkdown(md: string): DraftBlock[] {
  const blocks: DraftBlock[] = [];
  for (const raw of md.split('\n')) {
    const line = raw.trimEnd();
    if (!line) continue;
    if (line.startsWith('# ')) blocks.push({ type: 'h1', text: line.slice(2) });
    else if (line.startsWith('## ')) blocks.push({ type: 'h2', text: line.slice(3) });
    else if (line.startsWith('### ')) blocks.push({ type: 'h3', text: line.slice(4) });
    else if (line.startsWith('> ')) blocks.push({ type: 'blockquote', text: line.slice(2) });
    else if (line.trim() === '---') blocks.push({ type: 'hr', text: '' });
    else if (line.startsWith('_') && line.endsWith('_'))
      blocks.push({ type: 'meta', text: line.slice(1, -1) });
    else blocks.push({ type: 'p', text: line });
  }
  return blocks;
}
