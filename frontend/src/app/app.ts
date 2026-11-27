import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { UserPreferencesService } from './core/services/user-preferences.service';
import { LanguageSwitcher } from './layout/language-switcher/language-switcher';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, LanguageSwitcher],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '<router-outlet /><app-language-switcher />',
})
export class App {
  constructor() { inject(UserPreferencesService); }
}
