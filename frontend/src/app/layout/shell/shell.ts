import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { filter, map } from 'rxjs';
import { Navbar } from '../navbar/navbar';
import { Sidebar } from '../sidebar/sidebar';

@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, Sidebar, Navbar],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './shell.html',
  styleUrl: './shell.scss',
})
export class Shell {
  private readonly router = inject(Router);

  /** Mobile drawer state */
  protected readonly menuOpen = signal(false);

  /** Page title is read from the `title` field of the active route. */
  protected readonly pageTitle = toSignal(
    this.router.events.pipe(
      filter((e): e is NavigationEnd => e instanceof NavigationEnd),
      map(() => {
        let route = this.router.routerState.snapshot.root;
        while (route.firstChild) route = route.firstChild;
        return (route.title as string | undefined) ?? 'Dashboard';
      }),
    ),
    { initialValue: 'Dashboard' },
  );

  protected openMenu(): void { this.menuOpen.set(true); }
  protected closeMenu(): void { this.menuOpen.set(false); }
}
