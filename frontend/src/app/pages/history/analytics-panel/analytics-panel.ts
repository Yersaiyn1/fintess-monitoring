import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { firstValueFrom } from 'rxjs';
import { describeHttpError } from '../../../core/http/error-message';
import { Analytics, AnalyticsDay, Period } from '../../../core/models/workout.model';
import { AnalyticsApiService } from '../../../core/services/api/analytics-api.service';
import { BarChart, ChartBar } from '../../../shared/bar-chart/bar-chart';
import { UserPreferencesService } from '../../../core/services/user-preferences.service';

type MetricKey = keyof Pick<AnalyticsDay, 'durationMin' | 'caloriesKcal' | 'distanceKm' | 'steps'>;
interface Metric { key: MetricKey; label: string; unit: string; decimals: number }

/** Weekly / monthly analytics (Phase 3): totals, a bar chart per day and a split by activity type. */
@Component({
  selector: 'app-analytics-panel',
  imports: [DecimalPipe, BarChart],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './analytics-panel.html',
  styleUrl: './analytics-panel.scss',
})
export class AnalyticsPanel {
  private readonly api = inject(AnalyticsApiService);
  private readonly preferences = inject(UserPreferencesService);
  protected readonly userPreferences = this.preferences;
  private requestId = 0;

  protected readonly periods: { key: Period; label: string }[] = [
    { key: 'week', label: 'Week' },
    { key: 'month', label: 'Month' },
  ];
  protected readonly metrics: Metric[] = [
    { key: 'durationMin', label: 'Minutes', unit: 'min', decimals: 0 },
    { key: 'caloriesKcal', label: 'Calories', unit: 'kcal', decimals: 0 },
    { key: 'distanceKm', label: 'Distance', unit: this.preferences.distanceUnitLabel(), decimals: 1 },
    { key: 'steps', label: 'Steps', unit: 'steps', decimals: 0 },
  ];

  protected readonly period = signal<Period>('week');
  protected readonly metric = signal<Metric>(this.metrics[0]);
  protected readonly data = signal<Analytics | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal('');

  protected readonly bars = computed<ChartBar[]>(() => {
    const days = this.data()?.days ?? [];
    const key = this.metric().key;
    return days.map((d, i) => ({ label: d.label, value: key === 'distanceKm' ? this.preferences.distanceFromKm(d.distanceKm) : d[key], isToday: i === days.length - 1 }));
  });

  protected readonly longestKind = computed(() =>
    Math.max(1, ...(this.data()?.byKind ?? []).map((k) => k.durationMin)),
  );

  constructor() {
    void this.load();
  }

  protected setPeriod(p: Period): void {
    if (p === this.period()) return;
    this.period.set(p);
    void this.load();
  }

  protected setMetric(m: Metric): void {
    this.metric.set(m);
  }

  protected async load(): Promise<void> {
    const id = ++this.requestId; // ignore answers that arrive after a newer request
    this.loading.set(true);
    this.error.set('');
    try {
      const result = await firstValueFrom(this.api.workouts(this.period()));
      if (id === this.requestId) this.data.set(result);
    } catch (e) {
      if (id === this.requestId) this.error.set(describeHttpError(e, 'Could not load the analytics. Please try again.'));
    } finally {
      if (id === this.requestId) this.loading.set(false);
    }
  }
}
