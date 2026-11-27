import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { Icon } from '../../shared/icon/icon';
import { UserPreferencesService } from '../../core/services/user-preferences.service';
import { TranslatePipe } from '../../core/i18n/translate.pipe';

@Component({
  selector: 'app-navbar',
  imports: [Icon, RouterLink, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './navbar.html',
  styleUrl: './navbar.scss',
})
export class Navbar {
  readonly title = input('Dashboard');
  readonly menuToggle = output<void>();

  protected readonly auth = inject(AuthService);
  private readonly preferences = inject(UserPreferencesService).preferences;
  private readonly router = inject(Router);

  protected async logout(): Promise<void> {
    this.auth.logout();
    await this.router.navigateByUrl('/login');
  }

  protected readonly today = computed(() => {
    const locale = { kk: 'kk-KZ', en: 'en-US', ru: 'ru-RU' }[this.preferences().language];
    return new Intl.DateTimeFormat(locale, { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date());
  });
}
