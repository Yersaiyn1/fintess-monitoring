import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { UserPreferencesService } from '../../core/services/user-preferences.service';
import { TranslatePipe } from '../../core/i18n/translate.pipe';

@Component({
  selector: 'app-language-switcher',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <label class="language-switcher">
      <span>{{ 'Language' | t }}</span>
      <select [value]="preferences().language" (change)="changeLanguage($event)" [attr.aria-label]="'Language' | t">
        <option value="kk">{{ 'Kazakh' | t }}</option>
        <option value="en">{{ 'English' | t }}</option>
        <option value="ru">{{ 'Russian' | t }}</option>
      </select>
    </label>
  `,
  styles: `
    :host { position: fixed; right: 20px; bottom: 20px; z-index: 100; }
    .language-switcher {
      display: flex; align-items: center; gap: 8px; padding: 8px 10px 8px 14px;
      border: 1px solid var(--line); border-radius: 999px;
      background: var(--surface); color: var(--ink); box-shadow: 0 4px 18px #101a1c24;
      font-size: 13px; font-weight: 600;
    }
    select {
      border: 0; border-radius: 999px; padding: 5px 24px 5px 9px;
      background: var(--chalk); color: var(--ink); font: inherit; cursor: pointer;
    }
    @media (max-width: 600px) {
      :host { right: 10px; bottom: calc(76px + env(safe-area-inset-bottom)); }
      .language-switcher > span { display: none; }
    }
  `,
})
export class LanguageSwitcher {
  private readonly preferenceService = inject(UserPreferencesService);
  protected readonly preferences = this.preferenceService.preferences;

  protected changeLanguage(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    if (value === 'kk' || value === 'en' || value === 'ru') {
      this.preferenceService.update({ language: value });
    }
  }
}
