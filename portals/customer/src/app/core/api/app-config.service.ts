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
      console.warn('AppConfigService: falling back to environment defaults', err);
    }
  }
}
