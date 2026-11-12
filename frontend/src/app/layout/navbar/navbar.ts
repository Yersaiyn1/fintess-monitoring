import { ChangeDetectionStrategy, Component, inject, input, output } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { Icon } from '../../shared/icon/icon';

@Component({
  selector: 'app-navbar',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './navbar.html',
  styleUrl: './navbar.scss',
})
export class Navbar {
  readonly title = input('Dashboard');
  readonly menuToggle = output<void>();

  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected async logout(): Promise<void> {
    this.auth.logout();
    await this.router.navigateByUrl('/login');
  }

  protected readonly today = new Intl.DateTimeFormat('en-US', {
    weekday: 'long', day: 'numeric', month: 'long',
  }).format(new Date());
}
