import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { WeeklyMetric } from '../../core/models/activity.model';
import { DashboardDataService } from '../../core/services/dashboard-data.service';
import { BarChart, ChartBar } from '../../shared/bar-chart/bar-chart';
import { ProgressRing } from '../../shared/progress-ring/progress-ring';
import { StatCard } from '../../shared/stat-card/stat-card';
import { UserPreferencesService } from '../../core/services/user-preferences.service';

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
  private readonly preferences = inject(UserPreferencesService);

  protected readonly today = this.data.today;
  protected readonly goal = this.data.dailyStepGoal;
  protected readonly progress = this.data.stepsProgress;
  protected readonly remaining = this.data.stepsRemaining;
  protected readonly stats = this.data.statCards;
  protected readonly workouts = this.data.recentWorkouts;
  protected readonly loading = this.data.loading;
  protected readonly error = this.data.error;

  constructor() {
    void this.data.load();
  }

  protected readonly metrics: MetricOption[] = [
    { key: 'steps', label: 'Steps', unit: 'steps', decimals: 0 },
    { key: 'calories', label: 'Calories', unit: 'kcal', decimals: 0 },
    { key: 'distanceKm', label: 'Distance', unit: this.preferences.distanceUnitLabel(), decimals: 1 },
  ];
  protected readonly metric = signal<MetricOption>(this.metrics[0]);

  protected readonly bars = computed<ChartBar[]>(() => {
    const week = this.data.week();
    const key = this.metric().key;
    return week.map((d, i) => ({
      label: d.label,
      value: key === 'distanceKm' ? this.preferences.distanceFromKm(d.distanceKm) : d[key],
      isToday: i === week.length - 1,
    }));
  });

  protected readonly chartGoal = computed(() => (this.metric().key === 'steps' ? this.goal() : null));

  protected readonly weekTotal = computed(() =>
    this.data.week().reduce((sum, d) => sum + (this.metric().key === 'distanceKm' ? this.preferences.distanceFromKm(d.distanceKm) : d[this.metric().key]), 0),
  );

  protected readonly goalReached = computed(() => this.remaining() === 0);

  protected retry(): void {
    void this.data.load();
  }

  protected select(option: MetricOption): void {
    this.metric.set(option);
  }
}
