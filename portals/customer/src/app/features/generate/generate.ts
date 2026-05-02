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
  CorpusType,
  DraftCitation,
  FaithfulnessStatus,
  GenerateDraftResponse,
  GuardrailStatus,
  GuardrailViolation,
  RagmgmtApiService,
  RetrievalMeta,
} from '../../core/api/ragmgmt-api.service';

// Order chosen to match how the backend's three_corpora_search returns groups
// (regulator → clinical_evidence → practice_voice). Matches the README's
// listing order for the three corpora.
const CORPUS_ORDER: CorpusType[] = ['regulator', 'clinical_evidence', 'practice_voice'];

const CORPUS_LABEL: Record<CorpusType, string> = {
  regulator: 'Regulator',
  clinical_evidence: 'Clinical evidence',
  practice_voice: 'Practice voice',
};

interface CorpusCoverage {
  type: CorpusType;
  label: string;
  hitCount: number;
  present: boolean;
}

interface DraftBlock {
  type: 'h1' | 'h2' | 'h3' | 'blockquote' | 'hr' | 'p' | 'meta';
  text: string;
}

export interface DraftSegment {
  /** 'plain' = passthrough; 'banned' = guardrail violation match; */
  kind: 'plain' | 'banned';
  text: string;
}

export interface AnnotatedBlock extends DraftBlock {
  unsupported: boolean;     // sentence appears in faithfulness preview as unsupported
  segments: DraftSegment[]; // body text split on banned-phrase regex
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
  // top_k_per_corpus: in three-corpora mode the backend returns up to N hits
  // per corpus (regulator + evidence + voice). 3 = 9 max citations total —
  // a workable default for a single draft.
  readonly topKPerCorpus = signal<number>(3);

  readonly loading = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly draft = signal<GenerateDraftResponse | null>(null);

  readonly draftBlocks = computed<AnnotatedBlock[]>(() => {
    const md = this.draft()?.draft_markdown ?? '';
    const blocks = parseDraftMarkdown(md);
    const bannedRe = buildBannedRegex(this.guardrailViolations());
    const unsupportedSentences = collectUnsupportedSentences(this.faithfulness());
    return blocks.map((b) => annotateBlock(b, bannedRe, unsupportedSentences));
  });

  readonly citations = computed<DraftCitation[]>(() => this.draft()?.citations ?? []);

  readonly retrievalMeta = computed<RetrievalMeta | null>(
    () => this.draft()?.retrieval_meta ?? null
  );

  /** Three-corpora coverage chips. Returns one entry per corpus type even when
   *  a corpus contributed zero hits — the missing corpus is the load-bearing
   *  signal: it tells the operator which README-promised grounding is absent. */
  readonly corporaCoverage = computed<CorpusCoverage[]>(() => {
    const meta = this.retrievalMeta();
    if (!meta || meta.mode !== 'three_corpora') return [];
    const counts = meta.per_corpus_hit_counts ?? {};
    return CORPUS_ORDER.map((type) => {
      const hitCount = counts[type] ?? 0;
      return {
        type,
        label: CORPUS_LABEL[type],
        hitCount,
        present: hitCount > 0,
      };
    });
  });

  readonly anyCorpusMissing = computed<boolean>(
    () => this.corporaCoverage().some((c) => !c.present)
  );

  readonly guardrails = computed<GuardrailStatus | null>(
    () => this.draft()?.guardrails ?? null
  );

  readonly guardrailViolations = computed<GuardrailViolation[]>(
    () => this.guardrails()?.violations ?? []
  );

  readonly faithfulness = computed<FaithfulnessStatus | null>(
    () => this.draft()?.faithfulness ?? null
  );

  faithfulnessHeadlineClass(): string {
    const f = this.faithfulness();
    if (!f) return 'pill pill-pending';
    if (f.status === 'skipped') return 'pill pill-pending';
    if (f.status === 'error') return 'pill pill-failure';
    if (f.passed) return 'pill pill-success';
    return 'pill pill-skipped';
  }

  faithfulnessHeadlineLabel(): string {
    const f = this.faithfulness();
    if (!f) return 'no draft yet';
    if (f.status === 'skipped') return 'faithfulness skipped';
    if (f.status === 'error') return 'faithfulness error';
    const pct = f.score != null ? (f.score * 100).toFixed(0) : '?';
    if (f.passed) return `score ${pct}% · passed`;
    return `score ${pct}% · regen suggested`;
  }

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

  /** CSS class for per-corpus chips. Stays out of the SCSS as a string switch
   *  so `:host ::ng-deep` rules can target a single class per corpus type. */
  corpusChipClass(type: CorpusType | null | undefined): string {
    if (!type) return 'corpus-chip corpus-unknown';
    return `corpus-chip corpus-${type.replace('_', '-')}`;
  }

  corpusLabel(type: CorpusType | null | undefined): string {
    if (!type) return 'unknown';
    return CORPUS_LABEL[type] ?? type;
  }

  setTopic(v: string): void {
    this.topic.set(v);
  }
  setVoice(v: string): void {
    this.voiceProfile.set(v);
  }
  setTopKPerCorpus(v: number): void {
    this.topKPerCorpus.set(Math.max(1, Math.min(10, Math.floor(v) || 3)));
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
        retrieval_mode: 'three_corpora',
        top_k_per_corpus: this.topKPerCorpus(),
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

function buildBannedRegex(violations: GuardrailViolation[]): RegExp | null {
  if (!violations.length) return null;
  // Dedupe matched_text values, escape regex chars, sort longest-first so the
  // alternation prefers maximal matches.
  const unique = Array.from(new Set(violations.map((v) => v.matched_text))).sort(
    (a, b) => b.length - a.length
  );
  const pattern = unique
    .map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .join('|');
  if (!pattern) return null;
  return new RegExp(`(${pattern})`, 'gi');
}

function collectUnsupportedSentences(f: FaithfulnessStatus | null): string[] {
  if (!f?.per_sentence_preview) return [];
  return f.per_sentence_preview
    .filter((s) => !s.supported)
    .map((s) => (s.sentence ?? '').trim())
    .filter(Boolean);
}

function annotateBlock(
  block: DraftBlock,
  bannedRe: RegExp | null,
  unsupportedSentences: string[]
): AnnotatedBlock {
  const text = block.text;
  const unsupported = unsupportedSentences.some((s) => s && text.includes(s));
  const segments = splitOnBanned(text, bannedRe);
  return { ...block, unsupported, segments };
}

function splitOnBanned(text: string, bannedRe: RegExp | null): DraftSegment[] {
  if (!bannedRe || !text) {
    return [{ kind: 'plain', text }];
  }
  // Reset lastIndex on the cloned regex so successive calls don't drift.
  const re = new RegExp(bannedRe.source, bannedRe.flags);
  const out: DraftSegment[] = [];
  let cursor = 0;
  for (const m of text.matchAll(re)) {
    const idx = m.index ?? 0;
    if (idx > cursor) {
      out.push({ kind: 'plain', text: text.slice(cursor, idx) });
    }
    out.push({ kind: 'banned', text: m[0] });
    cursor = idx + m[0].length;
  }
  if (cursor < text.length) {
    out.push({ kind: 'plain', text: text.slice(cursor) });
  }
  return out;
}
