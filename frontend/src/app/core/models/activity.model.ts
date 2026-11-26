export interface DailyActivity {
  /** ISO date (yyyy-mm-dd) */
  date: string;
  /** Short weekday label, e.g. "Mon" */
  label: string;
  steps: number;
  calories: number;
  caloriesEstimated?: boolean;
  distanceKm: number;
  activeMinutes: number;
}

export type { WorkoutKind } from './workout.model';
import type { WorkoutKind } from './workout.model';

export interface RecentWorkout {
  id: number;
  kind: WorkoutKind;
  durationMin: number;
  calories: number;
  /** Human-readable time, e.g. "Today, 07:30" */
  when: string;
}

export type WeeklyMetric = 'steps' | 'calories' | 'distanceKm';
