import { Injectable, computed, inject, signal } from '@angular/core';
import { catchError, finalize } from 'rxjs/operators';
import { of } from 'rxjs';
import { DailyActivity, RecentWorkout } from '../models/activity.model';
import { StatCardData } from '../models/stat.model';
import { DashboardApiService } from './api/dashboard-api.service';

@Injectable({ providedIn: 'root' })
export class DashboardDataService {
  private readonly api = inject(DashboardApiService);

  /** Daily step goal (becomes user-editable in Phase 4). */
  readonly dailyStepGoal = signal(10_000);

  /** Loading / error handling for API fetch */
  readonly loading = signal<boolean>(true);
  readonly error = signal<string | null>(null);

  /** Last 7 days, oldest first; the last item is "today". Fallback to mock week on initial or empty. */
  readonly week = signal<DailyActivity[]>(this.buildMockWeek());

  readonly recentWorkouts = signal<RecentWorkout[]>([
    { id: 1, kind: 'Run', durationMin: 32, calories: 318, when: 'Today, 07:30' },
    { id: 2, kind: 'Strength', durationMin: 45, calories: 264, when: 'Yesterday, 18:10' },
    { id: 3, kind: 'Cycling', durationMin: 58, calories: 402, when: 'Tue, 17:45' },
    { id: 4, kind: 'Yoga', durationMin: 30, calories: 96, when: 'Mon, 08:00' },
  ]);

  readonly today = computed(() => {
    const w = this.week();
    return w.length > 0 ? w[w.length - 1] : this.fallbackToday();
  });

  private readonly yesterday = computed(() => {
    const w = this.week();
    return w.length > 1 ? w[w.length - 2] : this.today();
  });

  readonly stepsProgress = computed(() =>
    Math.min(this.today().steps / this.dailyStepGoal(), 1),
  );
  readonly stepsRemaining = computed(() =>
    Math.max(this.dailyStepGoal() - this.today().steps, 0),
  );

  readonly workoutsToday = computed(
    () => this.recentWorkouts().filter((w) => w.when.startsWith('Today')).length,
  );

  readonly statCards = computed<StatCardData[]>(() => {
    const t = this.today();
    const y = this.yesterday();
    return [
      { id: 'calories', label: 'Calories burned', value: t.calories, unit: 'kcal', icon: 'flame', tone: 'coral', change: this.delta(t.calories, y.calories), decimals: 0 },
      { id: 'distance', label: 'Distance', value: t.distanceKm, unit: 'km', icon: 'route', tone: 'cobalt', change: this.delta(t.distanceKm, y.distanceKm), decimals: 1 },
      { id: 'active', label: 'Active time', value: t.activeMinutes, unit: 'min', icon: 'clock', tone: 'mint', change: this.delta(t.activeMinutes, y.activeMinutes), decimals: 0 },
      { id: 'workouts', label: 'Workouts today', value: this.workoutsToday(), unit: '', icon: 'bolt', tone: 'amber', change: 0, decimals: 0 },
    ];
  });

  constructor() {
    this.fetchData();
  }

  fetchData(userId = 1): void {
    this.loading.set(true);
    this.error.set(null);

    this.api
      .getDashboard(userId)
      .pipe(
        catchError((err) => {
          this.error.set('Не удалось загрузить данные с сервера');
          console.error(err);
          return of(null);
        }),
        finalize(() => this.loading.set(false))
      )
      .subscribe((resp) => {
        if (resp && resp.week && resp.week.length > 0) {
          this.week.set(resp.week);
        }
      });
  }

  private delta(now: number, before: number): number {
    return before === 0 ? 0 : Math.round(((now - before) / before) * 100);
  }

  private fallbackToday(): DailyActivity {
    return {
      date: new Date().toISOString().slice(0, 10),
      label: 'Today',
      steps: 0,
      calories: 0,
      distanceKm: 0,
      activeMinutes: 0,
    };
  }

  private buildMockWeek(): DailyActivity[] {
    const steps = [8420, 11260, 6930, 9810, 12480, 5390, 7482];
    const minutes = [41, 63, 34, 52, 71, 26, 48];
    const labels = new Intl.DateTimeFormat('en-US', { weekday: 'short' });
    const now = new Date();

    return steps.map((s, i) => {
      const d = new Date(now);
      d.setDate(now.getDate() - (steps.length - 1 - i));
      return {
        date: d.toISOString().slice(0, 10),
        label: labels.format(d),
        steps: s,
        calories: Math.round(s * 0.055),
        distanceKm: Math.round(s * 0.00075 * 10) / 10,
        activeMinutes: minutes[i],
      };
    });
  }
}
