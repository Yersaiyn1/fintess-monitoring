export interface DailyActivity {
  /** ISO date (yyyy-mm-dd) */
  date: string;
  /** Short weekday label, e.g. "Mon" */
  label: string;
  steps: number;
  calories: number;
  distanceKm: number;
  activeMinutes: number;
}

export type WorkoutKind = 'Run' | 'Cycling' | 'Strength' | 'Yoga' | 'Walk';

export interface RecentWorkout {
  id: number;
  kind: WorkoutKind;
  durationMin: number;
  calories: number;
  /** Human-readable time, e.g. "Today, 07:30" */
  when: string;
}

export type WeeklyMetric = 'steps' | 'calories' | 'distanceKm';
