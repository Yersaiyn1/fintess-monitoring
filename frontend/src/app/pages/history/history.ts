import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { describeHttpError } from '../../core/http/error-message';
import { Workout, WorkoutKind } from '../../core/models/workout.model';
import { WorkoutsApiService } from '../../core/services/api/workouts-api.service';
import { DeviceReading, SyncApiService } from '../../core/services/api/sync-api.service';
import { formatDuration, formatWhen } from '../../core/utils/format';
import { AnalyticsPanel } from './analytics-panel/analytics-panel';
import { UserPreferencesService } from '../../core/services/user-preferences.service';
import { TranslatePipe } from '../../core/i18n/translate.pipe';

const PAGE_SIZE = 10;

/** Workout history (Phase 3): analytics on top, then a filterable list. A row opens the details page. */
@Component({
  selector: 'app-history',
  imports: [RouterLink, DatePipe, DecimalPipe, AnalyticsPanel, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './history.html',
  styleUrl: './history.scss',
})
export class History {
  private readonly api = inject(WorkoutsApiService);
  private readonly syncApi = inject(SyncApiService);
  protected readonly preferences = inject(UserPreferencesService);
  private requestId = 0;

  protected readonly kinds: WorkoutKind[] = ['Run', 'Walk', 'Cycling', 'Strength', 'Yoga'];
  protected readonly formatDuration = formatDuration;
  protected readonly formatWhen = (iso: string) => formatWhen(iso);

  protected readonly from = signal('');
  protected readonly to = signal('');
  protected readonly kind = signal<WorkoutKind | ''>('');

  protected readonly items = signal<Workout[]>([]);
  protected readonly total = signal(0);
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly readings = signal<DeviceReading[]>([]);
  protected readonly moreReadings = signal(false);
  protected readonly readingsLoading = signal(false);
  protected readonly readingsError = signal('');
  protected readonly readingsStatus = signal('');
  protected readonly confirmingReading = signal<number | null>(null);
  protected readonly deletingReading = signal(false);

  protected readonly hasMore = computed(() => this.items().length < this.total());
  protected readonly hasFilters = computed(() => !!(this.from() || this.to() || this.kind()));
  protected readonly rangeError = computed(() =>
    this.from() && this.to() && this.from() > this.to() ? '“From” must not be after “To”.' : '',
  );

  constructor() {
    void this.reload();
    void this.loadReadings();
  }

  protected async loadReadings(append = false): Promise<void> {
    if (this.readingsLoading()) return;
    this.readingsLoading.set(true);
    this.readingsError.set('');
    try {
      const page = await firstValueFrom(this.syncApi.readings(append ? this.readings().length : 0));
      this.readings.update((items) => append ? [...items, ...page.items] : page.items);
      this.moreReadings.set(page.has_more);
    } catch (e) {
      this.readingsError.set(describeHttpError(e, 'Could not load your device readings.'));
    } finally {
      this.readingsLoading.set(false);
    }
  }

  protected async deleteReading(id: number): Promise<void> {
    if (this.readingsLoading() || this.deletingReading()) return;
    this.deletingReading.set(true);
    this.readingsStatus.set('');
    this.readingsError.set('');
    try {
      await firstValueFrom(this.syncApi.deleteReading(id));
      this.confirmingReading.set(null);
      this.readings.update((items) => items.filter((item) => item.reading_id !== id));
      this.readingsStatus.set('Reading deleted.');
    } catch (e) {
      this.readingsError.set(describeHttpError(e, 'Could not delete the reading.'));
    } finally {
      this.deletingReading.set(false);
    }
  }

  protected setFrom(e: Event): void {
    this.from.set((e.target as HTMLInputElement).value);
    void this.reload();
  }

  protected setTo(e: Event): void {
    this.to.set((e.target as HTMLInputElement).value);
    void this.reload();
  }

  protected setKind(e: Event): void {
    this.kind.set((e.target as HTMLSelectElement).value as WorkoutKind | '');
    void this.reload();
  }

  protected resetFilters(): void {
    this.from.set('');
    this.to.set('');
    this.kind.set('');
    void this.reload();
  }

  /** First page with the current filters. */
  protected async reload(): Promise<void> {
    if (this.rangeError()) return;
    await this.fetch(0, false);
  }

  protected async loadMore(): Promise<void> {
    await this.fetch(this.items().length, true);
  }

  private async fetch(offset: number, append: boolean): Promise<void> {
    const id = ++this.requestId; // ignore answers that arrive after a newer request
    this.loading.set(true);
    this.error.set('');
    try {
      const page = await firstValueFrom(
        this.api.list({ from: this.from(), to: this.to(), kind: this.kind(), limit: PAGE_SIZE, offset }),
      );
      if (id !== this.requestId) return;
      this.items.update((old) => (append ? [...old, ...page.items] : page.items));
      this.total.set(page.total);
    } catch (e) {
      if (id === this.requestId) this.error.set(describeHttpError(e, 'Could not load your workouts. Please try again.'));
    } finally {
      if (id === this.requestId) this.loading.set(false);
    }
  }
}
