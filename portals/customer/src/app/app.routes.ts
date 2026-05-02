import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    redirectTo: 'catalog',
  },
  {
    path: '',
    loadComponent: () =>
      import('./core/layout/shell').then((m) => m.ShellComponent),
    children: [
      {
        path: 'catalog',
        loadComponent: () =>
          import('./features/catalog/dataset-catalog/dataset-catalog').then(
            (m) => m.DatasetCatalogComponent
          ),
      },
      {
        path: 'generate',
        loadComponent: () =>
          import('./features/generate/generate').then((m) => m.GenerateComponent),
      },
    ],
  },
];
