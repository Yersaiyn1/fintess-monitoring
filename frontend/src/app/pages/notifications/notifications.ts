import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { NotificationsApi, Reminder } from '../../core/services/api/notifications-api.service';
import { TranslatePipe } from '../../core/i18n/translate.pipe';

@Component({
  selector: 'app-notifications',
  imports: [TranslatePipe],
  templateUrl: './notifications.html',
  styleUrl: './notifications.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Notifications {
  private readonly api = inject(NotificationsApi);
  readonly items = signal<Reminder[]>([]);
  readonly unread = computed(() => this.items().filter(item => !item.is_read).length);
  readonly busy = signal(false);
  readonly error = signal('');

  constructor() { void this.refresh(); }

  async refresh(): Promise<void> {
    this.busy.set(true);
    this.error.set('');
    try { this.items.set(await firstValueFrom(this.api.list())); }
    catch { this.error.set('Could not load notifications. Please try again.'); }
    finally { this.busy.set(false); }
  }

  async mark(item?: Reminder): Promise<void> {
    this.busy.set(true);
    try {
      await firstValueFrom(item ? this.api.markOne(item) : this.api.markAll());
      await this.refresh();
    } catch {
      this.error.set('Could not update notifications. Reload the list and try again.');
    } finally { this.busy.set(false); }
  }
}
