export type WorkoutKind = 'Run' | 'Walk' | 'Cycling' | 'Strength' | 'Yoga';

/** GET /api/v1/workouts/types — also used to estimate live numbers while the timer runs. */
export interface ActivityType {
  kind: WorkoutKind;
  label: string;
  stepsPerMin: number;
  kmPerMin: number;
  kcalPerMin: number;
}

/** GET/POST /api/v1/workouts... (backend/app/schemas/workout.py) */
export interface Workout {
  id: number;
  kind: WorkoutKind;
  startedAt: string; // ISO date-time
  endedAt: string | null;
  durationSec: number | null; // null while in progress
  steps: number;
  distanceKm: number;
  caloriesKcal: number;
  inProgress: boolean;
}

export interface WorkoutPage {
  items: Workout[];
  total: number;
  limit: number;
  offset: number;
}

export interface WorkoutFilters {
  from?: string; // yyyy-mm-dd
  to?: string;   // yyyy-mm-dd
  kind?: WorkoutKind | '';
  limit?: number;
  offset?: number;
}

/** GET /api/v1/analytics/workouts (backend/app/schemas/analytics.py) */
export type Period = 'week' | 'month';

export interface AnalyticsDay {
  date: string;
  label: string;
  workouts: number;
  durationMin: number;
  caloriesKcal: number;
  distanceKm: number;
  steps: number;
}

export interface AnalyticsTotals {
  workouts: number;
  durationMin: number;
  caloriesKcal: number;
  distanceKm: number;
  steps: number;
}

export interface KindBreakdown {
  kind: WorkoutKind;
  workouts: number;
  durationMin: number;
  caloriesKcal: number;
}

export interface Analytics {
  period: Period;
  startDate: string;
  endDate: string;
  days: AnalyticsDay[];
  totals: AnalyticsTotals;
  byKind: KindBreakdown[];
}
