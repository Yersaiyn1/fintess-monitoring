import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { describeHttpError } from '../../../core/http/error-message';
import { AdviceApiService, AdviceItem, AdviceSource } from '../../../core/services/api/advice-api.service';

@Component({
  selector: 'app-advice-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './advice-panel.html',
  styleUrl: './advice-panel.scss',
})
export class AdvicePanel {
  private readonly api = inject(AdviceApiService);

  protected readonly items = signal<AdviceItem[]>([]);
  protected readonly source = signal<AdviceSource>('rules');
  protected readonly disclaimer = signal('This is not medical advice.');
  protected readonly aiAvailable = signal(false);
  protected readonly aiConsent = signal(false);
  protected readonly loading = signal(true);
  protected readonly updatingConsent = signal(false);
  protected readonly error = signal('');

  constructor() {
    void this.load();
  }

  public async load(refresh = false): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const res = await firstValueFrom(this.api.getAdvice(refresh));
      this.items.set(res.items);
      this.source.set(res.source);
      this.disclaimer.set(res.disclaimer);
      this.aiAvailable.set(res.ai_available);
      this.aiConsent.set(res.ai_consent);
    } catch (err) {
      this.error.set(describeHttpError(err, 'Could not load personalized advice.'));
    } finally {
      this.loading.set(false);
    }
  }

  protected async onConsentToggle(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement | null;
    const enabled = Boolean(input?.checked);
    this.updatingConsent.set(true);
    this.error.set('');
    try {
      const res = await firstValueFrom(this.api.setConsent(enabled));
      this.aiConsent.set(res.enabled);
      await this.load(false);
    } catch (err) {
      if (input) {
        input.checked = this.aiConsent();
      }
      this.error.set(describeHttpError(err, 'Could not update AI preference.'));
    } finally {
      this.updatingConsent.set(false);
    }
  }
}
