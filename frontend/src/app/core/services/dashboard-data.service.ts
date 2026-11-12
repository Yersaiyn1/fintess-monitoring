import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { DailyActivity, RecentWorkout } from '../models/activity.model';
import { StatCardData } from '../models/stat.model';
import { DashboardApiService } from './api/dashboard-api.service';
import { AuthService } from './auth.service';

const WEEKDAYS = new Intl.DateTimeFormat('en-US', { weekday: 'short' });

/** 7 empty days ending today: shown until the real data arrives, so the page never has "no data" holes. */
function emptyWeek(): DailyActivity[] {
  const now = new Date();
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(now);
    d.setDate(now.getDate() - (6 - i));
    return { date: d.toISOString().slice(0, 10), label: WEEKDAYS.format(d), steps: 0, calories: 0, distanceKm: 0, activeMinutes: 0 };
  });
}

/**
 * State of the Dashboard page. Data comes from the backend (GET /api/v1/dashboard).
 * Components read the signals below and never talk HTTP themselves.
 */
@Injectable({ providedIn: 'root' })
export class DashboardDataService {
  private readonly api = inject(DashboardApiService);
  private readonly auth = inject(AuthService);
  private loadedForUser: number | null = null;

  /** Daily step goal (becomes user-editable in Phase 4). */
  readonly dailyStepGoal = signal(10_000);

  /** Last 7 days, oldest first; the last item is "today". */
  readonly week = signal<DailyActivity[]>(emptyWeek());

  /** Filled by Phase 2 (workout tracking). Empty until then: no fake data next to real data. */
  readonly recentWorkouts = signal<RecentWorkout[]>([]);

  readonly loading = signal(false);
  readonly error = signal('');

  readonly today = computed(() => this.week()[this.week().length - 1]);
  private readonly yesterday = computed(() => this.week()[this.week().length - 2]);

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

  /** Loads the last 7 days from the backend. Safe to call again (e.g. "Retry"). */
  async load(): Promise<void> {
    const userId = this.auth.user()?.id ?? null;
    if (userId !== this.loadedForUser) {
      // A different user logged in: never show the previous user's numbers.
      this.week.set(emptyWeek());
      this.recentWorkouts.set([]);
      this.loadedForUser = userId;
    }
    this.loading.set(true);
    this.error.set('');
    try {
      const res = await firstValueFrom(this.api.getDashboard());
      if (res.week.length > 0) this.week.set(res.week);
    } catch (e) {
      this.error.set(this.messageFrom(e));
    } finally {
      this.loading.set(false);
    }
  }

  private messageFrom(e: unknown): string {
    if (e instanceof HttpErrorResponse && e.status === 0) {
      return 'Cannot reach the server. Make sure the backend is running.';
    }
    return 'Could not load your activity. Please try again.';
  }

  private delta(now: number, before: number): number {
    return before === 0 ? 0 : Math.round(((now - before) / before) * 100);
  }
}
