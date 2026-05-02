import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    redirectTo: 'administration/data-management/initial-dataset',
  },
  {
    path: '',
    loadComponent: () =>
      import('./core/layout/shell').then((m) => m.ShellComponent),
    children: [
      {
        path: 'administration/data-management/initial-dataset',
        loadComponent: () =>
          import(
            './features/administration/data-management/initial-dataset/initial-dataset'
          ).then((m) => m.InitialDatasetComponent),
      },
      {
        path: 'administration/data-management/source-urls',
        loadComponent: () =>
          import(
            './features/administration/data-management/source-urls/source-urls'
          ).then((m) => m.SourceUrlsComponent),
      },
      {
        path: 'rag-management',
        pathMatch: 'full',
        redirectTo: 'rag-management/patterns',
      },
      {
        path: 'rag-management/patterns',
        loadComponent: () =>
          import('./features/rag-management/patterns/patterns-list').then(
            (m) => m.RagPatternsListComponent
          ),
      },
    ],
  },
];
