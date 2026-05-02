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
        path: 'rag-management',
        loadComponent: () =>
          import('./features/rag-management/rag-management').then(
            (m) => m.RagManagementComponent
          ),
      },
    ],
  },
];
