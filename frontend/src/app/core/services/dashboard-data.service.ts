import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { DailyActivity, RecentWorkout } from '../models/activity.model';
import { describeHttpError } from '../http/error-message';
import { Workout } from '../models/workout.model';
import { formatWhen } from '../utils/format';
import { StatCardData } from '../models/stat.model';
import { DashboardApiService } from './api/dashboard-api.service';
import { WorkoutsApiService } from './api/workouts-api.service';
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
  private readonly workoutsApi = inject(WorkoutsApiService);
  private readonly auth = inject(AuthService);
  private loadedForUser: number | null = null;

  /** Daily step goal (becomes user-editable in Phase 4). */
  readonly dailyStepGoal = signal(10_000);

  /** Last 7 days, oldest first; the last item is "today". */
  readonly week = signal<DailyActivity[]>(emptyWeek());

  /** The 4 latest finished workouts (Phase 2). */
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

  /** Today's steps / calories / distance / active time: used by the Activity page (Phase 2). */
  readonly activityCards = computed<StatCardData[]>(() => {
    const t = this.today();
    const y = this.yesterday();
    return [
      { id: 'steps', label: 'Steps', value: t.steps, unit: '', icon: 'footsteps', tone: 'cobalt', change: this.delta(t.steps, y.steps), decimals: 0 },
      { id: 'calories', label: 'Calories burned', value: t.calories, unit: 'kcal', icon: 'flame', tone: 'coral', change: this.delta(t.calories, y.calories), decimals: 0 },
      { id: 'distance', label: 'Distance', value: t.distanceKm, unit: 'km', icon: 'route', tone: 'mint', change: this.delta(t.distanceKm, y.distanceKm), decimals: 1 },
      { id: 'active', label: 'Active time', value: t.activeMinutes, unit: 'min', icon: 'clock', tone: 'amber', change: this.delta(t.activeMinutes, y.activeMinutes), decimals: 0 },
    ];
  });

  /** Loads the last 7 days and the latest workouts. Safe to call again (e.g. "Retry", or after a workout). */
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
    // The week is required; the latest workouts are "nice to have" and must not break the page.
    const [week, recent] = await Promise.allSettled([
      firstValueFrom(this.api.getDashboard()),
      firstValueFrom(this.workoutsApi.list({ limit: 4 })),
    ]);
    if (week.status === 'fulfilled') {
      if (week.value.week.length > 0) this.week.set(week.value.week);
    } else {
      this.error.set(describeHttpError(week.reason, 'Could not load your activity. Please try again.'));
    }
    if (recent.status === 'fulfilled') {
      this.recentWorkouts.set(recent.value.items.map(toRecent));
    }
    this.loading.set(false);
  }

  private delta(now: number, before: number): number {
    return before === 0 ? 0 : Math.round(((now - before) / before) * 100);
  }
}

function toRecent(w: Workout): RecentWorkout {
  return {
    id: w.id,
    kind: w.kind,
    // at least 1 min, so a very short workout does not show "0 min"
    durationMin: w.durationSec ? Math.max(1, Math.round(w.durationSec / 60)) : 0,
    calories: Math.round(w.caloriesKcal),
    when: formatWhen(w.startedAt),
  };
}
