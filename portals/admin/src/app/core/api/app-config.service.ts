import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../../environments/environment';
import { ApiResp } from './api.types';

export interface AppRuntimeConfig {
  airflowUiBase: string;
}

const FALLBACK_CONFIG: AppRuntimeConfig = {
  airflowUiBase: environment.airflowUiBase ?? '',
};

/**
 * Loads deployment-specific runtime config from the FastAPI `/config` endpoint at app
 * bootstrap. The same SPA artifact runs in any environment because anything that
 * varies by deployment (Airflow ingress URL, future feature toggles) lives behind
 * this service rather than baked into the bundle.
 *
 * If `/config` is unreachable or fails, falls back to `environment.ts` defaults so
 * the app still loads instead of blocking on a non-essential dependency.
 */
@Injectable({ providedIn: 'root' })
export class AppConfigService {
  private readonly http = inject(HttpClient);
  private readonly _config = signal<AppRuntimeConfig>(FALLBACK_CONFIG);

  readonly config = this._config.asReadonly();
  readonly airflowUiBase = computed(() => this._config().airflowUiBase);

  async load(): Promise<void> {
    try {
      const resp = await firstValueFrom(
        this.http.get<ApiResp<AppRuntimeConfig>>('/api/config')
      );
      const ctx = resp?.respCtxData;
      if (ctx) {
        this._config.set({
          airflowUiBase: ctx.airflowUiBase ?? FALLBACK_CONFIG.airflowUiBase,
        });
      }
    } catch (err) {
      // Non-fatal: keep the FALLBACK_CONFIG and let the app render. The portal works
      // without the Airflow link; the link cell just shows "—" until config loads.
      console.warn('AppConfigService: falling back to environment defaults', err);
    }
  }
}
