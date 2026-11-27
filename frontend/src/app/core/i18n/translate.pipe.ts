import { ChangeDetectorRef, Pipe, PipeTransform, effect, inject } from '@angular/core';
import { UserPreferencesService } from '../services/user-preferences.service';
import { translateText } from './translations';

@Pipe({ name: 't', standalone: true, pure: false })
export class TranslatePipe implements PipeTransform {
  private readonly preferences = inject(UserPreferencesService);
  private readonly changeDetector = inject(ChangeDetectorRef);

  constructor() {
    effect(() => {
      this.preferences.preferences().language;
      this.changeDetector.markForCheck();
    });
  }

  transform(text: string): string {
    return translateText(text, this.preferences.preferences().language);
  }
}
