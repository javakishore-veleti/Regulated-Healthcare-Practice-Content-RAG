import { Component, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  NavigationEnd,
  Router,
  RouterLink,
  RouterLinkActive,
  RouterOutlet,
} from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { filter } from 'rxjs/operators';

interface SideNavItem {
  label: string;
  link?: string;
  children?: SideNavItem[];
}

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatToolbarModule,
    MatSidenavModule,
    MatListModule,
    MatIconModule,
  ],
  templateUrl: './shell.html',
  styleUrl: './shell.scss',
})
export class ShellComponent {
  private readonly currentUrl = signal<string>('');

  readonly section = computed<'administration' | 'rag-management'>(() =>
    this.currentUrl().startsWith('/rag-management') ? 'rag-management' : 'administration'
  );

  readonly sideNav = computed<SideNavItem[]>(() => {
    if (this.section() === 'administration') {
      return [
        {
          label: 'Data Management',
          children: [
            {
              label: 'Initial DataSet',
              link: '/administration/data-management/initial-dataset',
            },
          ],
        },
      ];
    }
    return [
      {
        label: 'Patterns',
        children: [{ label: '(coming soon)' }],
      },
    ];
  });

  constructor(router: Router) {
    this.currentUrl.set(router.url);
    router.events
      .pipe(
        filter((e): e is NavigationEnd => e instanceof NavigationEnd),
        takeUntilDestroyed()
      )
      .subscribe((e) => this.currentUrl.set(e.urlAfterRedirects));
  }
}
