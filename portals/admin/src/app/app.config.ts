import {
  APP_INITIALIZER,
  ApplicationConfig,
  inject,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { provideHttpClient, withFetch } from '@angular/common/http';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';

import { AppConfigService } from './core/api/app-config.service';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withFetch()),
    provideAnimationsAsync(),
    {
      // Block bootstrap on /api/config so deployment-specific values (Airflow UI URL,
      // future feature toggles) are populated before any component renders.
      provide: APP_INITIALIZER,
      useFactory: () => {
        const cfg = inject(AppConfigService);
        return () => cfg.load();
      },
      multi: true,
    },
  ],
};
