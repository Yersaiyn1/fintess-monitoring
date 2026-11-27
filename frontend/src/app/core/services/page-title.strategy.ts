import { Injectable, effect, inject } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterStateSnapshot, TitleStrategy } from '@angular/router';
import { UserPreferencesService } from './user-preferences.service';
import { translateText } from '../i18n/translations';

/** Sets the browser tab title to "<Page> · Pulse". */
@Injectable({ providedIn: 'root' })
export class PageTitleStrategy extends TitleStrategy {
  private readonly title = inject(Title);
  private readonly preferences = inject(UserPreferencesService);
  private currentPage = '';

  constructor() {
    super();
    effect(() => {
      this.preferences.preferences().language;
      this.setCurrentTitle();
    });
  }

  override updateTitle(snapshot: RouterStateSnapshot): void {
    this.currentPage = this.buildTitle(snapshot) ?? '';
    this.setCurrentTitle();
  }

  private setCurrentTitle(): void {
    const language = this.preferences.preferences().language;
    const page = translateText(this.currentPage, language);
    this.title.setTitle(page ? `${page} · Pulse` : 'Pulse');
  }
}
