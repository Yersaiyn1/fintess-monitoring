import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { firstValueFrom } from 'rxjs';
import { describeHttpError } from '../../core/http/error-message';
import { WeeklyMetric } from '../../core/models/activity.model';
import { HealthConnectUploadResponse, SyncApiService } from '../../core/services/api/sync-api.service';
import { DashboardDataService } from '../../core/services/dashboard-data.service';
import { WorkoutTrackerService } from '../../core/services/workout-tracker.service';
import { BarChart, ChartBar } from '../../shared/bar-chart/bar-chart';
import { ProgressRing } from '../../shared/progress-ring/progress-ring';
import { StatCard } from '../../shared/stat-card/stat-card';

interface MetricOption {
  key: WeeklyMetric;
  label: string;
  unit: string;
  decimals: number;
}

@Component({
  selector: 'app-dashboard',
  imports: [DecimalPipe, StatCard, ProgressRing, BarChart],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
})
export class Dashboard {
  private readonly data = inject(DashboardDataService);
  private readonly syncApi = inject(SyncApiService);
  private readonly tracker = inject(WorkoutTrackerService);

  protected readonly today = this.data.today;
  protected readonly goal = this.data.dailyStepGoal;
  protected readonly progress = this.data.stepsProgress;
  protected readonly remaining = this.data.stepsRemaining;
  protected readonly stats = this.data.statCards;
  protected readonly workouts = this.data.recentWorkouts;
  protected readonly loading = this.data.loading;
  protected readonly error = this.data.error;

  protected readonly isUploading = signal(false);
  protected readonly uploadError = signal('');
  protected readonly uploadResult = signal<HealthConnectUploadResponse | null>(null);

  constructor() {
    void this.data.load();
  }

  protected readonly metrics: MetricOption[] = [
    { key: 'steps', label: 'Steps', unit: 'steps', decimals: 0 },
    { key: 'calories', label: 'Calories', unit: 'kcal', decimals: 0 },
    { key: 'distanceKm', label: 'Distance', unit: 'km', decimals: 1 },
  ];
  protected readonly metric = signal<MetricOption>(this.metrics[0]);

  protected readonly bars = computed<ChartBar[]>(() => {
    const week = this.data.week();
    const key = this.metric().key;
    return week.map((d, i) => ({
      label: d.label,
      value: d[key],
      isToday: i === week.length - 1,
    }));
  });

  protected readonly chartGoal = computed(() => (this.metric().key === 'steps' ? this.goal() : null));

  protected readonly weekTotal = computed(() =>
    this.data.week().reduce((sum, d) => sum + d[this.metric().key], 0),
  );

  protected readonly goalReached = computed(() => this.remaining() === 0);

  protected retry(): void {
    void this.data.load();
  }

  protected select(option: MetricOption): void {
    this.metric.set(option);
  }

  protected async onFileSelected(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file) return;

    const lower = file.name.toLowerCase();
    if (!lower.endsWith('.zip') && !lower.endsWith('.db')) {
      this.uploadError.set('Only .zip and .db Health Connect export files are supported.');
      this.uploadResult.set(null);
      if (input) input.value = '';
      return;
    }

    this.isUploading.set(true);
    this.uploadError.set('');
    this.uploadResult.set(null);
    try {
      const res = await firstValueFrom(this.syncApi.uploadHealthConnectArchive(file));
      this.uploadResult.set(res);
      await this.data.load();
      if (this.tracker.ready()) {
        await this.tracker.init();
      }
    } catch (e) {
      this.uploadError.set(describeHttpError(e, 'Could not import Health Connect data.'));
    } finally {
      this.isUploading.set(false);
      if (input) input.value = '';
    }
  }
}
